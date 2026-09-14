#!/usr/bin/env python3
"""Product temperature sequence with a separate DMM7510 worker at each point."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import thermal_stream_temperature_sequence as thermal
from thermal_stream_temperature_run import positive, ROOT, utc_now
from offset_drift_handshake import atomic_json, read_request, SCHEMA_VERSION, DEFAULT_TASK_ID, task_id_value

WORKER = Path(__file__).with_name("dmm_offset_worker.py")


def readings_value(value):
    value = int(value)
    if value < 2:
        import argparse
        raise argparse.ArgumentTypeError("At least two DMM readings are required")
    return value


def nonnegative(value):
    import argparse
    import math
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("Value must be nonnegative and finite")
    return value


def parse_args(argv=None):
    parser = thermal.build_parser(__doc__)
    parser.add_argument("--task-id", type=task_id_value, default=DEFAULT_TASK_ID,
                        help="Task/DUT label saved in every DMM file and result (default: offset)")
    count = parser.add_mutually_exclusive_group()
    count.add_argument("--readings", type=readings_value, default=1000)
    count.add_argument("--readings-per-stage", type=readings_value, nargs=3, metavar=("COLD", "AMBIENT", "HOT"))
    parser.add_argument("--gain", type=positive, default=1001.0)
    parser.add_argument("--dmm-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--dmm-resource")
    parser.add_argument("--terminals", choices=("FRONT", "REAR"), default="FRONT")
    parser.add_argument("--dmm-range", type=positive, default=0.1)
    parser.add_argument("--nplc", type=positive, default=10.0)
    parser.add_argument("--dmm-timeout", type=positive, default=60.0)
    parser.add_argument("--dmm-max-seconds", type=positive, default=3600.0,
                        help="Maximum worker time per stage, including acquisition and analysis")
    parser.add_argument("--dmm-cancel-grace", type=positive, default=5.0)
    parser.add_argument("--inter-reading-delay", type=nonnegative, default=0.0)
    args = thermal.validate_args(parser, parser.parse_args(argv))
    if args.output_dir is None:
        args.output_dir = ROOT / "results" / "offset_drift" / ("run_" + uuid.uuid4().hex)
    return args


class DmmMeasurement:
    """Non-blocking file handshake; only this child process may access the DMM."""
    def __init__(self, args, *, worker=WORKER, clock=time):
        self.args, self.worker, self.clock = args, Path(worker), clock
        self.run_id = uuid.uuid4().hex
        self.process = self.log = self.folder = None
        self.result = None
        self.configuration = None

    def preflight(self):
        completed = subprocess.run([str(self.args.dmm_python), str(self.worker), "--check"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode:
            raise RuntimeError("DMM dependency preflight failed: " + completed.stdout + completed.stderr)

    def snapshot_sources(self):
        return [Path(__file__), WORKER, Path(__file__).with_name("offset_drift_handshake.py"),
                Path(__file__).with_name("analyze_offset_drift.py"),
                ROOT / "Unicorn_CSA_RevB-COB" / "capture_dmm7510_offset.py",
                ROOT / "Unicorn_CSA_RevB-COB" / "analyze_dmm7510_offset.py"]

    def start(self, folder, stop_file, stage):
        if self.process is not None:
            raise RuntimeError("Previous DMM worker has not been collected")
        self.folder = Path(folder) / "dmm" / f"stage_{stage['index']:02d}"
        self.folder.mkdir(parents=True, exist_ok=False)
        counts = self.args.readings_per_stage or [self.args.readings] * 3
        request = {"schema_version": SCHEMA_VERSION, "task_id": self.args.task_id, "run_id": self.run_id,
                   "job_id": uuid.uuid4().hex, "stage_index": stage["index"],
                   "target_c": stage["target_c"], "issued_at_utc": utc_now(),
                   "stop_file": str(Path(stop_file).resolve()), "dmm": {
                       "readings": counts[stage["index"] - 1], "gain": self.args.gain,
                       "range_v": self.args.dmm_range, "nplc": self.args.nplc,
                       "terminals": self.args.terminals, "input_impedance": "AUTO",
                       "resource": self.args.dmm_resource, "timeout": self.args.dmm_timeout,
                       "settling_delay": 2.0, "discard_readings": 3,
                       "inter_reading_delay": self.args.inter_reading_delay,
                   }}
        path = self.folder / "dmm_request.json"
        atomic_json(path, request)
        _, digest = read_request(path)
        self.result = {key: request[key] for key in ("task_id", "run_id", "job_id", "stage_index", "target_c")}
        self.result.update(schema_version=SCHEMA_VERSION, request_sha256=digest, status="running",
                           requested_readings=request["dmm"]["readings"], gain=self.args.gain,
                           directory=str(self.folder), worker_log=str(self.folder / "worker.log"))
        self.log = (self.folder / "worker.log").open("x", encoding="utf-8")
        self.started = self.clock.monotonic()
        try:
            self.process = subprocess.Popen([str(self.args.dmm_python), str(self.worker), "--request", str(path)],
                                            stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            self.log.close()
            self.log = None
            raise
        return self.result

    def poll(self):
        if self.process is None:
            raise RuntimeError("No DMM job is active")
        flag = self.folder / "dmm_done.json"
        code = self.process.poll()
        result = None
        if flag.exists():
            result = json.loads(flag.read_text(encoding="utf-8"))
            for key in ("schema_version", "task_id", "run_id", "job_id", "stage_index", "target_c",
                        "request_sha256", "requested_readings", "gain"):
                if result.get(key) != self.result[key]:
                    raise RuntimeError(f"DMM completion flag mismatch: {key}")
            if result.get("status") != "completed":
                self.result.update(result)
                raise RuntimeError("DMM job failed: " + str(result.get("error", result.get("status"))))
        if code is not None:
            if code != 0 or result is None:
                self.result.update(status="failed", worker_exit_code=code)
                raise RuntimeError(f"DMM worker exited {code} without a successful completion flag")
            if result.get("completed_readings") != self.result["requested_readings"]:
                raise RuntimeError("DMM completion count mismatch")
            artifacts = result.get("artifacts", {})
            if set(artifacts) != {"summary", "tdms", "plot", "readings_csv"}:
                raise RuntimeError("DMM completion artifacts are incomplete")
            for value in artifacts.values():
                artifact = (self.folder / value).resolve()
                if not artifact.is_relative_to(self.folder.resolve()) or not artifact.is_file():
                    raise RuntimeError("DMM artifact is missing or outside this job")
            summary = json.loads((self.folder / artifacts["summary"]).read_text(encoding="utf-8"))
            if (summary.get("task_id") != self.args.task_id
                    or summary["total_reading_count"] != self.result["requested_readings"] or summary["run_count"] != 1
                    or summary["configuration"]["closed_loop_gain_v_per_v"] != self.args.gain):
                raise RuntimeError("DMM summary does not match the request")
            if self.configuration is not None and summary["configuration"] != self.configuration:
                raise RuntimeError("DMM configuration changed between temperature points")
            self.configuration = summary["configuration"]
            self.result.update(result, worker_exit_code=code)
            self.log.close()
            self.log = None
            self.process = None
            return self.result
        if self.clock.monotonic() - self.started >= self.args.dmm_max_seconds:
            raise TimeoutError("DMM completion flag wait exceeded --dmm-max-seconds")
        return None

    def request_cancel(self):
        # Non-blocking: the temperature controller must attempt STOP before waiting for a worker.
        if self.process is not None and self.process.poll() is None:
            (self.folder / "CANCEL").touch(exist_ok=True)

    def close(self):
        try:
            if self.process is not None:
                try:
                    code = self.process.wait(timeout=self.args.dmm_cancel_grace)
                except subprocess.TimeoutExpired:
                    self.result["worker_forced_termination"] = True
                    self.process.terminate()
                    code = self.process.wait(timeout=3)
                self.result["worker_exit_code"] = code
                if self.result.get("status") == "running":
                    self.result["status"] = "cancelled_by_controller"
                self.process = None
        finally:
            if self.log is not None:
                self.log.close()
                self.log = None


def main(argv=None):
    args = parse_args(argv)
    print(f"TASK_ID={args.task_id}", flush=True)
    code = thermal.run(args, measurement=DmmMeasurement(args))
    # Device and worker cleanup is complete before cross-temperature analysis.
    try:
        from analyze_offset_drift import analyze_run
        analyze_run(args.output_dir, args.plot_dependency_dir)
    except Exception as exc:
        print(f"OFFSET SUMMARY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Offset sequence could not finish: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
