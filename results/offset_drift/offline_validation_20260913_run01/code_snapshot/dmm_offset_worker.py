#!/usr/bin/env python3
"""Run one DMM7510 offset acquisition and publish an atomic completion flag.

Owns only the DMM. Never opens a thermal-stream connection.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

from offset_drift_handshake import atomic_json, capture_arguments, read_request, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Cancelled(RuntimeError):
    pass


def load_modules():
    sys.path.insert(0, str(ROOT / "Unicorn_CSA_RevB-COB"))
    import capture_dmm7510_offset as capture
    import analyze_dmm7510_offset as analyze
    capture.check_runtime()
    return capture, analyze


def run_request(path, *, modules=None):
    path = Path(path).resolve()
    folder = path.parent
    request, digest = read_request(path)
    # Exclusive, persistent claim prevents accidentally acquiring the same request twice.
    with (folder / "worker.claim").open("x", encoding="utf-8") as claim:
        claim.write(f"{os.getpid()}\n")
    if (folder / "dmm_done.json").exists():
        raise FileExistsError("A completion flag already exists for this job")
    result = {key: request[key] for key in ("run_id", "job_id", "stage_index", "target_c")}
    result.update(schema_version=SCHEMA_VERSION, request_sha256=digest,
                  status="running", started_at_utc=stamp(), requested_readings=request["dmm"]["readings"],
                  completed_readings=0, gain=request["dmm"]["gain"],
                  execution_environment=request.get("execution_environment", "real_hardware"))

    def check_cancel():
        if (folder / "CANCEL").exists() or Path(request["stop_file"]).exists():
            raise Cancelled("Temperature controller requested DMM cancellation")

    try:
        check_cancel()
        capture, analyze = modules or load_modules()
        capture_args = capture_arguments(request, folder)
        # Validate options before opening VISA; no driver operation in argument parsing.
        capture.parse_args(capture_args)
        for name in ("data", "results"):
            if (folder / name).exists():
                raise FileExistsError(f"Refusing to mix existing {name} with a new job")
        with (folder / "partial_readings.csv").open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("reading_index", "acquisition_time_utc", "elapsed_s",
                             "output_voltage_v", "equivalent_input_offset_v"))
            stream.flush()

            def on_reading(index, value, elapsed, start):
                measured_at = (start + timedelta(seconds=elapsed)).isoformat()
                writer.writerow((index, measured_at, elapsed, value, value / request["dmm"]["gain"]))
                stream.flush()
                os.fsync(stream.fileno())
                result["completed_readings"] = index
                result.setdefault("first_reading_at_utc", measured_at)
                result["last_reading_at_utc"] = measured_at
                atomic_json(folder / "dmm_progress.json", {**result, "updated_at_utc": stamp()})

            code = capture.main(capture_args, check_cancel=check_cancel, on_reading=on_reading)
            if code != 0:
                raise RuntimeError(f"DMM capture exit code {code}")
        check_cancel()
        if result["completed_readings"] != result["requested_readings"]:
            raise RuntimeError("DMM did not capture the requested number of readings")
        code = analyze.main(["--task-id", "offset", "--data-dir", str(folder / "data"),
                             "--output-dir", str(folder / "results")])
        if code != 0:
            raise RuntimeError(f"DMM analysis exit code {code}")
        check_cancel()
        summary_path = folder / "results" / "offset" / "offset_dcv_offset_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary["total_reading_count"] != result["requested_readings"] or summary["run_count"] != 1:
            raise RuntimeError("Analyzed reading count does not match the request")
        if summary["configuration"]["closed_loop_gain_v_per_v"] != result["gain"]:
            raise RuntimeError("Analyzed gain does not match the request")
        result.update(status="completed", artifacts={
            "summary": "results/offset/offset_dcv_offset_summary.json",
            "readings_csv": "results/offset/offset_dcv_readings.csv",
            "plot": "results/offset/offset_dcv_offset.png",
            "tdms": "data/offset/offset_dcv_0001.tdms",
        })
        if not all((folder / value).is_file() for value in result["artifacts"].values()):
            raise RuntimeError("DMM result artifacts are missing")
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status="cancelled" if isinstance(exc, (Cancelled, KeyboardInterrupt)) else "failed",
                      error=f"{type(exc).__name__}: {exc}")
    finally:
        result["finished_at_utc"] = stamp()
        atomic_json(folder / "dmm_done.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request", type=Path)
    mode.add_argument("--check", action="store_true", help="Import and check dependencies only; no VISA connection")
    args = parser.parse_args(argv)
    if args.check:
        load_modules()
        print("DMM dependencies OK; no instrument connection opened")
        return 0
    return run_request(args.request)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
