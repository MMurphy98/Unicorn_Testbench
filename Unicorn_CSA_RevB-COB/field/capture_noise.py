#!/usr/bin/env python3
"""Capture NI-SCOPE noise into tasks/<task-id>/data on the Windows field PC."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from _common import (BOARD_DIR, acquisition_record, add_task_options, atomic_json, cli,
                     check_resume_conditions, positive_float, positive_int, print_plan, read_manifest,
                     require_windows, run_logged, task_path)

CONFIGURATION_KEYS = ("runs", "resource", "channel", "sample_rate", "samples", "input_impedance",
                      "vertical_range", "gain", "gbw", "timeout")
CONDITION_KEYS = tuple(key for key in CONFIGURATION_KEYS if key not in ("runs", "timeout"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_task_options(parser)
    parser.add_argument("--runs", type=positive_int, default=100)
    parser.add_argument("--resource", default="PXI1Slot2")
    parser.add_argument("--channel", default="0")
    parser.add_argument("--sample-rate", type=positive_float, default=50_000.0)
    parser.add_argument("--samples", type=positive_int, default=1_100_000)
    parser.add_argument("--input-impedance", type=positive_float, default=1_000_000.0)
    parser.add_argument("--vertical-range", type=positive_float, default=2.0)
    parser.add_argument("--gain", type=positive_float, default=1001.0)
    parser.add_argument("--gbw", type=positive_float, default=15_000_000.0)
    parser.add_argument("--timeout", type=positive_float, default=40.0)
    return parser


def capture_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-u", str(BOARD_DIR / "capture_dut_revb_pmu_noise.py"),
               "--task-id", args.task_id, "--task-dir", str(task_path(args))]
    for name in ("runs", "resource", "channel", "sample_rate", "samples", "input_impedance",
                 "vertical_range", "gain", "gbw", "timeout"):
        command.extend(("--" + name.replace("_", "-"), str(getattr(args, name))))
    return command


def completed_count(task: Path, task_id: str) -> int:
    pattern = re.compile(rf"{re.escape(task_id)}_\d+\.tdms", re.I)
    return sum(1 for path in (task / "data").glob("*.tdms") if pattern.fullmatch(path.name))


def capture(args: argparse.Namespace) -> int:
    task = task_path(args)
    command = capture_command(args)
    configuration = {name: getattr(args, name) for name in CONFIGURATION_KEYS}
    check_resume_conditions(task, configuration, CONDITION_KEYS)
    if args.dry_run:
        print_plan(task, [command])
        return 0
    require_windows()
    sources = [Path(__file__), Path(__file__).with_name("_common.py"),
               BOARD_DIR / "capture_dut_revb_pmu_noise.py"]
    before_count = completed_count(task, args.task_id)
    with acquisition_record(task, measurement_type="noise", chip=args.chip,
                            commands=[command], sources=sources) as (record, _, log):
        manifest = read_manifest(task)
        manifest["expected_run_count"] = before_count + args.runs
        manifest["acquisition_configuration"] = configuration
        atomic_json(task / "task.json", manifest)
        print_plan(task, [command])
        print(f"Acquisition log: {log}", flush=True)
        record["exit_code"] = run_logged(command, log)
        if record["exit_code"] == 0 and completed_count(task, args.task_id) - before_count != args.runs:
            raise RuntimeError("Capture returned success but the requested TDMS count is missing from task/data")
        return record["exit_code"]


def main(argv=None) -> int:
    return capture(build_parser().parse_args(argv))


if __name__ == "__main__":
    cli(main)
