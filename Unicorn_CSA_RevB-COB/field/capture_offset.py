#!/usr/bin/env python3
"""Capture standalone DMM7510 DCV offset into tasks/<task-id>/data."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from _common import (BOARD_DIR, acquisition_record, add_task_options, atomic_json, cli,
                     check_resume_conditions, nonnegative_float, nonnegative_int, positive_float, positive_int,
                     print_plan, read_manifest, readings_value, require_windows,
                     run_logged, task_path)

CONFIGURATION_KEYS = ("runs", "readings", "terminals", "range_v", "input_impedance", "nplc",
                      "settling_delay", "discard_readings", "inter_reading_delay", "gain", "timeout", "resource")
CONDITION_KEYS = tuple(key for key in CONFIGURATION_KEYS if key not in ("runs", "timeout"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_task_options(parser)
    parser.add_argument("--runs", type=positive_int, default=1)
    parser.add_argument("--readings", type=readings_value, default=100)
    parser.add_argument("--resource", help="Default: auto-select exactly one USB DMM7510")
    parser.add_argument("--terminals", choices=("FRONT", "REAR"), default="FRONT")
    parser.add_argument("--range", dest="range_v", type=positive_float, default=0.1)
    parser.add_argument("--input-impedance", choices=("AUTO", "10M"), default="AUTO")
    parser.add_argument("--nplc", type=positive_float, default=10.0)
    parser.add_argument("--settling-delay", type=nonnegative_float, default=2.0)
    parser.add_argument("--discard-readings", type=nonnegative_int, default=3)
    parser.add_argument("--inter-reading-delay", type=nonnegative_float, default=0.0)
    parser.add_argument("--gain", type=positive_float, default=1001.0)
    parser.add_argument("--timeout", type=positive_float, default=60.0)
    return parser


def capture_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-u", str(BOARD_DIR / "capture_dmm7510_offset.py"),
               "--task-id", args.task_id, "--task-dir", str(task_path(args))]
    for name in ("runs", "readings", "terminals", "input_impedance", "nplc", "settling_delay",
                 "discard_readings", "inter_reading_delay", "gain", "timeout"):
        command.extend(("--" + name.replace("_", "-"), str(getattr(args, name))))
    command.extend(("--range", str(args.range_v)))
    if args.resource:
        command.extend(("--resource", args.resource))
    return command


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    task = task_path(args)
    command = capture_command(args)
    configuration = {name: getattr(args, name) for name in CONFIGURATION_KEYS}
    check_resume_conditions(task, configuration, CONDITION_KEYS)
    if args.dry_run:
        print_plan(task, [command])
        return 0
    require_windows()
    sources = [Path(__file__), Path(__file__).with_name("_common.py"), BOARD_DIR / "capture_dmm7510_offset.py"]
    with acquisition_record(task, measurement_type="dcv_offset", chip=args.chip,
                            commands=[command], sources=sources) as (record, _, log):
        manifest = read_manifest(task)
        manifest["acquisition_configuration"] = configuration
        atomic_json(task / "task.json", manifest)
        print_plan(task, [command])
        print(f"Acquisition log: {log}", flush=True)
        record["exit_code"] = run_logged(command, log)
        return record["exit_code"]


if __name__ == "__main__":
    cli(main)
