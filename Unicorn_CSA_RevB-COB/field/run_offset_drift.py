#!/usr/bin/env python3
"""Run the preserved three-temperature offset controller on the Windows field PC."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from _common import (BOARD_DIR, REPO_DIR, acquisition_id, acquisition_record, add_task_options,
                     atomic_json, cli, nonnegative_float, positive_float, print_plan,
                     read_manifest, readings_value, require_windows, run_logged, task_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_task_options(parser)
    parser.add_argument("--host", default="192.168.1.50")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--unit-id", type=int, default=0)
    parser.add_argument("--interval", type=positive_float, default=1.0)
    parser.add_argument("--tolerance", type=positive_float, default=1.0)
    parser.add_argument("--hold-seconds", type=positive_float, default=300.0)
    parser.add_argument("--timeout", type=positive_float, default=3.0)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--plot-dependency-dir", type=Path)
    count = parser.add_mutually_exclusive_group()
    count.add_argument("--readings", type=readings_value, default=1000)
    count.add_argument("--readings-per-stage", type=readings_value, nargs=3, metavar=("COLD", "AMBIENT", "HOT"))
    parser.add_argument("--gain", type=positive_float, default=1001.0)
    parser.add_argument("--dmm-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--dmm-resource")
    parser.add_argument("--terminals", choices=("FRONT", "REAR"), default="FRONT")
    parser.add_argument("--dmm-range", type=positive_float, default=0.1)
    parser.add_argument("--nplc", type=positive_float, default=10.0)
    parser.add_argument("--dmm-timeout", type=positive_float, default=60.0)
    parser.add_argument("--dmm-max-seconds", type=positive_float, default=3600.0)
    parser.add_argument("--dmm-cancel-grace", type=positive_float, default=5.0)
    parser.add_argument("--inter-reading-delay", type=nonnegative_float, default=0.0)
    return parser


def controller_command(args: argparse.Namespace, legacy_run: Path) -> list[str]:
    command = [sys.executable, "-u", str(REPO_DIR / "scripts" / "thermal_stream_offset_drift.py"),
               "--task-id", args.task_id, "--output-dir", str(legacy_run)]
    for name in ("host", "port", "unit_id", "interval", "tolerance", "hold_seconds", "timeout",
                 "gain", "dmm_python", "terminals", "dmm_range", "nplc", "dmm_timeout",
                 "dmm_max_seconds", "dmm_cancel_grace", "inter_reading_delay"):
        command.extend(("--" + name.replace("_", "-"), str(getattr(args, name))))
    if args.readings_per_stage:
        command.extend(("--readings-per-stage", *(str(count) for count in args.readings_per_stage)))
    else:
        command.extend(("--readings", str(args.readings)))
    for name in ("dmm_resource", "stop_file", "plot_dependency_dir"):
        value = getattr(args, name)
        if value is not None:
            command.extend(("--" + name.replace("_", "-"), str(value)))
    return command


def copy_artifact(source: Path, destination: Path, index: list[dict], task: Path) -> None:
    if not source.is_file():
        return
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite a task artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    index.append({"source": source.relative_to(task).as_posix(),
                  "destination": destination.relative_to(task).as_posix()})


def publish_thermal_run(task: Path, legacy_run: Path) -> list[dict]:
    """Keep file-handshake provenance intact, expose data and results by task."""
    index: list[dict] = []
    copy_artifact(legacy_run / "temperature.csv", task / "data" / "temperature.csv", index, task)
    for name in ("wire.jsonl", "events.jsonl"):
        copy_artifact(legacy_run / name, task / "logs" / name, index, task)
    copy_artifact(legacy_run / "summary.json", task / "results" / "thermal_sequence_summary.json", index, task)
    for name in ("offset_drift_summary.json", "offset_vs_temperature.csv", "offset_vs_temperature.png", "temperature_curve.png"):
        copy_artifact(legacy_run / name, task / "results" / name, index, task)
    for stage in sorted((legacy_run / "dmm").glob("stage_*")):
        for source in sorted((stage / "data" / task.name).glob("*.tdms")):
            copy_artifact(source, task / "data" / stage.name / source.name, index, task)
        copy_artifact(stage / "partial_readings.csv", task / "data" / stage.name / "partial_readings.csv", index, task)
        for name in ("dmm_request.json", "dmm_done.json", "dmm_progress.json", "worker.log", "worker.claim", "CANCEL"):
            copy_artifact(stage / name, task / "logs" / stage.name / name, index, task)
        for source in sorted((stage / "results" / task.name).glob("*")):
            if source.is_file():
                copy_artifact(source, task / "results" / stage.name / source.name, index, task)
    return index


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 0 <= args.unit_id <= 255:
        parser.error("invalid port or unit ID")
    task = task_path(args)
    run_id = acquisition_id()
    legacy_run = task / "provenance" / run_id / "legacy_run"
    command = controller_command(args, legacy_run)
    if args.dry_run:
        print_plan(task, [command])
        print(f"Full acquisition and file handshakes: {legacy_run}")
        return 0
    require_windows()
    if (task / "data").exists() and any((task / "data").rglob("*")):
        raise FileExistsError("A temperature sequence requires a fresh task ID; existing task data will not be mixed")
    sources = [Path(__file__), Path(__file__).with_name("_common.py"),
               *(REPO_DIR / "scripts" / name for name in (
                   "thermal_stream_offset_drift.py", "thermal_stream_temperature_sequence.py",
                   "thermal_stream_temperature_run.py", "dmm_offset_worker.py", "offset_drift_handshake.py",
                   "analyze_offset_drift.py", "plot_thermal_stream_temperature.py")),
               BOARD_DIR / "capture_dmm7510_offset.py", BOARD_DIR / "analyze_dmm7510_offset.py"]
    with acquisition_record(task, measurement_type="offset_drift", chip=args.chip,
                            commands=[command], sources=sources, run_id=run_id) as (record, run_dir, log):
        manifest = read_manifest(task)
        manifest.setdefault("provenance", {})["legacy_run"] = legacy_run.relative_to(task).as_posix()
        manifest["legacy_run_path"] = legacy_run.relative_to(task).as_posix()
        manifest["expected_temperature_points_c"] = [-40, 27, 125]
        manifest["expected_readings_per_stage"] = args.readings_per_stage or [args.readings] * 3
        atomic_json(task / "task.json", manifest)
        print_plan(task, [command])
        print(f"Acquisition log: {log}\nCancellation file: {args.stop_file or legacy_run / 'STOP'}", flush=True)
        try:
            record["exit_code"] = run_logged(command, log)
        finally:
            # Includes partial/failure evidence; it must not imply completion.
            copied = publish_thermal_run(task, legacy_run)
            atomic_json(run_dir / "published_artifacts.json", {"task_id": task.name, "artifacts": copied})
        return record["exit_code"]


if __name__ == "__main__":
    cli(main)
