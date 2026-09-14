"""Offline orchestration and independent-process handshake tests; never use hardware."""
import argparse
import contextlib
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import thermal_stream_offset_drift as offset
import thermal_stream_temperature_sequence as sequence
import thermal_stream_temperature_run as base
from test_thermal_stream_temperature_sequence import VirtualClock, SimulatedDevice, client_factory
from offset_drift_handshake import atomic_json, read_request, dmm_artifacts
from analyze_offset_drift import analyze_run

FIXTURE = Path(__file__).parent / "test_support/simulated_dmm_worker.py"


class Measurement:
    def __init__(self, device, clock, args, case=None):
        self.device, self.clock, self.args, self.case = device, clock, args, case
        self.starts, self.closed, self.cancelled = [], False, False
    def preflight(self): pass
    def snapshot_sources(self): return []
    def start(self, folder, stop_file, stage):
        assert self.device.coils[10] and stage["hold_elapsed_s"] >= self.args.hold_seconds
        self.starts.append((stage["index"], self.clock.now))
        self.stop_file = stop_file
        self.since = self.clock.now
        count = (self.args.readings_per_stage or [self.args.readings]*3)[stage["index"]-1]
        self.result = {"job_id": str(stage["index"]), "requested_readings": count, "status": "running"}
        if self.case in ("communication", "configuration", "device_stopped", "defrost", "tuning", "stop_failure"):
            self.device.fault = self.case
        return self.result
    def poll(self):
        assert self.device.starts == len(self.starts), "Temperature advanced before DMM completion"
        if self.case in ("dmm_failure", "stop_failure"): raise RuntimeError("Simulated DMM failure")
        if self.case == "interrupt": raise KeyboardInterrupt()
        if self.case == "stop": self.stop_file.touch()
        if self.clock.now - self.since >= 4:
            self.result.update(status="completed", completed_readings=self.result["requested_readings"])
            return self.result
    def request_cancel(self): self.cancelled = True
    def close(self):
        assert self.case == 'stop_failure' or not self.device.coils[10], "Worker cleanup blocked thermal STOP"
        self.closed = True


def simulate(folder, case=None):
    args = offset.parse_args(["--output-dir", str(folder), "--readings-per-stage", "2", "7", "1000"])
    clock = VirtualClock()
    device = SimulatedDevice(clock)
    measurement = Measurement(device, clock, args, case)
    with (patch.object(base, "time", clock),
          patch.object(base.socket, "create_connection", side_effect=AssertionError("REAL NETWORK FORBIDDEN")),
          contextlib.redirect_stdout(io.StringIO())):
        code = sequence.run(args, client_factory=client_factory(device), clock=clock,
                            measurement=measurement, plot_preflight=lambda _: None,
                            plotter=lambda folder, _: folder / "unused_plot.png")
    data = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    with (folder / "temperature.csv").open(encoding="utf-8", newline="") as f: rows=list(csv.DictReader(f))
    return code, data, rows, device, measurement


class TemperatureTests(unittest.TestCase):
    def test_defaults_and_variable_counts(self):
        args = offset.parse_args([])
        self.assertEqual((args.readings, args.gain, args.hold_seconds), (1000,1001,300))
        self.assertEqual(args.task_id, 'offset')
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            offset.parse_args(["--readings", "1"])

    def test_each_stage_waits_300_seconds_then_waits_for_its_own_dmm(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,s,rows,device,measurement = simulate(Path(tmp)/"run")
        self.assertEqual(code,0)
        self.assertEqual(device.starts,3)
        self.assertTrue(measurement.closed)
        self.assertEqual([v['dmm']['completed_readings'] for v in s['stages']],[2,7,1000])
        for stage in s['stages']:
            self.assertGreaterEqual(stage['hold_elapsed_s'],300)
            self.assertGreater(stage['completed_at_elapsed_s'],stage['hold_completed_at_elapsed_s']+3)
            active=[r for r in rows if r['stage_index']==str(stage['index']) and r['phase']=='measuring']
            self.assertGreaterEqual(len(active),4)
            self.assertTrue(all(r['running']=='True' for r in active))
            self.assertEqual(len({r['hold_elapsed_s'] for r in active}),1)
            self.assertTrue(all(float(r['hold_remaining_s'])==0 for r in active))
            self.assertGreater(stage['dmm_out_of_band_samples'],0)
        self.assertTrue(s['stop_confirmed'])

    def test_fault_during_measurement_cancels_dmm_stops_and_never_advances(self):
        for case in ('dmm_failure','communication','configuration','device_stopped','defrost','tuning','stop','interrupt'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                code,s,rows,device,measurement=simulate(Path(tmp)/'run',case)
                self.assertEqual(code,1)
                self.assertEqual(device.starts,1)
                self.assertTrue(s['stop_confirmed'])
                self.assertTrue(measurement.cancelled and measurement.closed)

    def test_dependency_failure_precedes_thermal_connection(self):
        args=offset.parse_args([])
        class Bad(Measurement):
            def preflight(self): raise RuntimeError('Missing DMM dependencies')
        with patch.object(base.socket,'create_connection',side_effect=AssertionError('REAL NETWORK FORBIDDEN')):
            with self.assertRaisesRegex(RuntimeError,'Missing DMM'):
                sequence.run(args,measurement=Bad(None,None,args),plot_preflight=lambda _:None)

    def test_stop_confirmation_failure_still_cleans_up_dmm(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,s,_,device,measurement=simulate(Path(tmp)/'run','stop_failure')
            self.assertEqual(code,1)
            self.assertFalse(s['stop_confirmed'])
            self.assertEqual(device.starts,1)
            self.assertTrue(measurement.cancelled and measurement.closed)


class TaskIdTests(unittest.TestCase):
    def test_task_id_cli_rejects_unsafe_directory_names(self):
        self.assertEqual(offset.parse_args(['--task-id','T-20260913_Chip1.v2']).task_id,
                         'T-20260913_Chip1.v2')
        for value in ('', '..', '../outside', 'a/b', 'a\\b', 'a b', 'a:b', 'NUL', 'con.txt', 'a.'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    offset.parse_args(['--task-id',value])

    def test_schema_one_legacy_request_defaults_without_rewriting_and_validates_task_id(self):
        request={'schema_version':1,'run_id':'a'*32,'job_id':'b'*32,
                 'stage_index':1,'target_c':-40,'dmm':{'readings':2}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'request.json'
            atomic_json(path,request)
            original=path.read_bytes()
            data,digest=read_request(path)
            self.assertEqual(data['task_id'],'offset')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(len(digest),64)
            for value in ('../outside',None):
                atomic_json(path,{**request,'task_id':value})
                with self.assertRaisesRegex(argparse.ArgumentTypeError,'Task ID'):read_request(path)

    def test_summary_uses_task_artifact_paths_and_reads_legacy_records(self):
        for task_id in ('offset','RevB_Chip1'):
            with self.subTest(task_id=task_id),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                artifacts=dmm_artifacts(task_id)
                data_path=folder/'dmm/stage_01'/artifacts['summary']
                data_path.parent.mkdir(parents=True)
                atomic_json(data_path,{'task_id':task_id,'total_reading_count':2,
                    'configuration':{'closed_loop_gain_v_per_v':1001},
                    'output_voltage_v':{'mean':.001001},
                    'equivalent_input_offset_v':{'mean':1e-6,'sample_std':1e-9}})
                stamp='2026-09-13T00:00:00+00:00'
                job={'status':'completed','artifacts':artifacts,'directory':'C:/old/location',
                     'first_reading_at_utc':stamp,'last_reading_at_utc':stamp}
                settings={}
                if task_id!='offset':
                    job['task_id']=settings['task_id']=task_id
                atomic_json(folder/'summary.json',{'settings':settings,'sequence_completed':False,
                    'stop_confirmed':True,'stages':[{'index':1,'target_c':-40,'status':'completed','dmm':job}]})
                (folder/'temperature.csv').write_text(
                    'stage_index,timestamp_utc,product_temperature_c,in_band\n'
                    f'1,{stamp},-40,True\n',encoding='utf-8')
                report=analyze_run(folder)
                self.assertEqual(report['task_id'],task_id)
                self.assertEqual(report['points'][0]['task_id'],task_id)
                self.assertEqual(report['points'][0]['product_temperature_mean_c'],-40)
                self.assertIsNone(report['nominal_temperature_linear_slope_v_per_c'])
                self.assertTrue((folder/'offset_vs_temperature.png').is_file())
                data=json.loads(data_path.read_text(encoding='utf-8'))
                atomic_json(data_path,{**data,'task_id':'DifferentTask'})
                with self.assertRaisesRegex(ValueError,'task ID'):analyze_run(folder)


class ProcessTests(unittest.TestCase):
    def run_job(self, folder, case='success', count=8, task_id='offset'):
        args=offset.parse_args(['--readings',str(count),'--dmm-cancel-grace','0.1','--task-id',task_id])
        job=offset.DmmMeasurement(args,worker=FIXTURE)
        original=offset.atomic_json
        def tagged(path,data):
            if Path(path).name=='dmm_request.json':
                data.update(simulation_case=case,execution_environment='offline_simulation')
            original(path,data)
        with patch.object(offset,'atomic_json',tagged):
            job.start(folder,Path(folder)/'STOP',{'index':1,'target_c':-40})
        return job

    def wait_job(self,job):
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            result=job.poll()
            if result is not None:return result
            time.sleep(.02)
        self.fail('Offline DMM worker did not finish')

    def test_actual_worker_writes_1000_verified_readings_before_done_flag(self):
        from nptdms import TdmsFile
        task_id='Offset_RevB_Chip1_20260913'
        with tempfile.TemporaryDirectory() as tmp:
            job=self.run_job(Path(tmp),count=1000,task_id=task_id)
            try:
                result=self.wait_job(job)
                self.assertEqual(result['completed_readings'],1000)
                self.assertEqual(result['worker_exit_code'],0)
                self.assertEqual(result['task_id'],task_id)
                folder=Path(result['directory'])
                for name in ('dmm_request.json','dmm_progress.json','dmm_done.json'):
                    self.assertEqual(json.loads((folder/name).read_text(encoding='utf-8'))['task_id'],task_id)
                tdms=TdmsFile.read(folder/result['artifacts']['tdms'])
                self.assertEqual(tdms.properties['task_id'],task_id)
                self.assertEqual((folder/result['artifacts']['tdms']).name,f'{task_id}_dcv_0001.tdms')
                with (folder/result['artifacts']['readings_csv']).open(encoding='utf-8',newline='') as f:
                    rows=list(csv.DictReader(f))
                self.assertEqual(len(rows),1000)
                self.assertTrue(all(row['task_id']==task_id for row in rows))
                with (folder/'partial_readings.csv').open(encoding='utf-8',newline='') as f:
                    self.assertEqual(len(list(csv.DictReader(f))),1000)
                evidence=json.loads((folder/'simulation.json').read_text())
                self.assertTrue(evidence['visa_closed'])
                self.assertEqual(evidence['real_instrument_connections'],0)
            finally:job.request_cancel();job.close()

    def test_bad_or_missing_flags_and_crash_cannot_advance(self):
        for case in ('bad_job','bad_count','bad_task','no_flag','crash','wrong_gain','wrong_task','fail','cancel'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                job=self.run_job(Path(tmp),case)
                try:
                    with self.assertRaises(RuntimeError):self.wait_job(job)
                    if case in ('fail','cancel'):
                        with (job.folder/'partial_readings.csv').open(encoding='utf-8',newline='') as f:
                            self.assertGreater(len(list(csv.DictReader(f))),0)
                        self.assertTrue(json.loads((job.folder/'simulation.json').read_text())['visa_closed'])
                finally:job.request_cancel();job.close()

    def test_timeout_and_hung_worker_cancellation_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=self.run_job(Path(tmp),'hang')
            try:
                # A successful-looking file alone cannot advance a still-running worker.
                atomic_json(job.folder/'dmm_done.json',{**job.result,'status':'completed',
                            'completed_readings':job.result['requested_readings']})
                self.assertIsNone(job.poll())
                job.args.dmm_max_seconds=.01
                time.sleep(.02)
                with self.assertRaises(TimeoutError):job.poll()
                job.request_cancel()
                self.assertTrue((job.folder/'CANCEL').exists())
                job.close()
                self.assertTrue(job.result['worker_forced_termination'])
                self.assertIsNone(job.process)
            finally:
                job.request_cancel();job.close()


if __name__=='__main__':unittest.main()
