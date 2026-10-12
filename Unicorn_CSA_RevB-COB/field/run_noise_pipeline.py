#!/usr/bin/env python3
"""Capture a task, optionally run offline analysis after acquisition completes."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from _common import BOARD_DIR, check_resume_conditions, cli, display_command, positive_int, print_plan, task_path
import capture_noise


def build_parser():
    parser = capture_noise.build_parser()
    parser.description = __doc__
    parser.add_argument("--postprocess", action="store_true",
                        help="Analyze after successful acquisition; requires offline analysis dependencies")
    parser.add_argument("--process-existing-only", action="store_true",
                        help="Only run analysis on an existing task; no acquisition or Windows requirement")
    parser.add_argument("--postprocess-python", type=Path, default=Path(sys.executable),
                        help="Python interpreter for the optional analysis step")
    parser.add_argument("--nperseg", type=positive_int, default=262_144)
    return parser


def processing_command(args):
    return [str(args.postprocess_python), "-u", str(BOARD_DIR / "postprocess" / "process_tasks.py"),
            "--task-id", args.task_id, "--tasks-root", str(args.tasks_root.expanduser().resolve()),
            "--nperseg", str(args.nperseg)]


def main(argv=None):
    args = build_parser().parse_args(argv)
    process = args.postprocess or args.process_existing_only
    commands = ([] if args.process_existing_only else [capture_noise.capture_command(args)])
    if process:
        commands.append(processing_command(args))
    if args.dry_run:
        if not args.process_existing_only:
            check_resume_conditions(task_path(args), {name: getattr(args, name) for name in capture_noise.CONFIGURATION_KEYS},
                                    capture_noise.CONDITION_KEYS)
        print_plan(task_path(args), commands)
        return 0
    if not args.process_existing_only:
        code = capture_noise.capture(args)
        if code:
            return code
    if process:
        command = processing_command(args)
        print(display_command(command), flush=True)
        return subprocess.call(command)
    print(f"Capture complete. Copy {task_path(args)} to the analysis computer, then run:")
    print(display_command(processing_command(args)))
    return 0


if __name__ == "__main__":
    cli(main)
