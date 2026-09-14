#!/usr/bin/env python3
"""Run the whole temperature/DMM handshake with simulated instruments only.

Virtual temperature time and simulated DMM readings are not timing or accuracy benchmarks.
Requires the same Python analysis dependencies as the DMM worker; opens no instrument.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
import uuid
from unittest.mock import patch

import thermal_stream_offset_drift as offset
import thermal_stream_temperature_sequence as thermal
import thermal_stream_temperature_run as base
from test_thermal_stream_temperature_sequence import VirtualClock, SimulatedDevice, client_factory
from analyze_offset_drift import analyze_run


class PacedClock(VirtualClock):
    def sleep(self, seconds):
        super().sleep(seconds)
        time.sleep(.002)  # Let the separate, offline DMM process perform real file I/O.


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--readings',type=offset.readings_value,default=1000)
    options=parser.parse_args(argv)
    folder=(options.output_dir or base.ROOT/'results/offset_drift'/('offline_'+uuid.uuid4().hex)).resolve()
    args=offset.parse_args(['--output-dir',str(folder),'--readings',str(options.readings)])
    clock=PacedClock()
    device=SimulatedDevice(clock,profile=lambda d,age: d.target+(3 if age<2 else .2))
    fixture=Path(__file__).parent/'test_support/simulated_dmm_worker.py'

    class OfflineMeasurement(offset.DmmMeasurement):
        def snapshot_sources(self):
            return super().snapshot_sources()+[Path(__file__),fixture,
                Path(__file__).with_name('test_thermal_stream_temperature_sequence.py')]

    job=OfflineMeasurement(args,worker=fixture,clock=clock)
    epoch=datetime(2026,9,13,tzinfo=timezone.utc)
    stamp=lambda:(epoch+timedelta(seconds=clock.now)).isoformat()
    save=thermal.write_summary_file
    atomic=offset.atomic_json
    def simulation_summary(path,data):
        data.update(execution_environment='offline_simulation',real_instrument_connections=0,
                    virtual_temperature_clock=True)
        save(path,data)
    def simulation_request(path,data):
        if Path(path).name=='dmm_request.json': data['execution_environment']='offline_simulation'
        atomic(path,data)
    with (patch.object(base,'time',clock),patch.object(base,'utc_now',stamp),
          patch.object(thermal,'utc_now',stamp),patch.object(offset,'utc_now',stamp),
          patch.object(thermal,'write_summary_file',simulation_summary),
          patch.object(offset,'atomic_json',simulation_request),
          patch('socket.create_connection',side_effect=AssertionError('REAL NETWORK FORBIDDEN'))):
        code=thermal.run(args,client_factory=client_factory(device),clock=clock,measurement=job)
    report=analyze_run(folder,args.plot_dependency_dir)
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    assert code==0 and summary['sequence_completed'] and summary['stop_confirmed']
    assert [s['dmm']['completed_readings'] for s in summary['stages']]==[options.readings]*3
    assert len(report['points'])==3
    assert not device.coils[10]
    (folder/'OFFLINE_SIMULATION.txt').write_text(
        'SIMULATED TEMPERATURE AND DMM DATA. No real instrument connections.\n'
        'Virtual timing is not a benchmark for real acquisition speed or thermal response.\n',encoding='utf-8')
    print('OFFLINE VALIDATION PASSED: '+str(folder))
    return 0


if __name__=='__main__':raise SystemExit(main())
