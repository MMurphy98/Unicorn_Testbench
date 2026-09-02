"""Continuously orchestrate DUT noise capture, analysis, and plotting.

The capture process owns NI-SCOPE.  While it is acquiring, this supervisor scans
for newly finalized TDMS files, analyzes them, and periodically refreshes the
aggregate plot.  Files ending in ``.partial.tdms`` are never considered here or
by the analysis script.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TASK_ID = "RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def task_id_value(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError(
            "task ID must start with a letter or digit and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run capture continuously while automatically analyzing newly "
            "completed TDMS files and refreshing the averaged noise plot."
        )
    )
    parser.add_argument("--task-id", type=task_id_value, default=DEFAULT_TASK_ID)
    parser.add_argument("--runs", type=positive_int, default=100)
    parser.add_argument("--resource", default="PXI1Slot2")
    parser.add_argument("--channel", default="0")
    parser.add_argument("--sample-rate", type=positive_float, default=50_000.0)
    parser.add_argument("--samples", type=positive_int, default=1_100_000)
    parser.add_argument(
        "--input-impedance", type=positive_float, default=1_000_000.0
    )
    parser.add_argument("--vertical-range", type=positive_float, default=2.0)
    parser.add_argument("--gain", type=positive_float, default=1001.0)
    parser.add_argument("--gbw", type=positive_float, default=15_000_000.0)
    parser.add_argument("--timeout", type=positive_float, default=40.0)
    parser.add_argument("--nperseg", type=positive_int, default=262_144)
    parser.add_argument(
        "--poll-interval",
        type=positive_float,
        default=5.0,
        help="Seconds between checks for newly completed TDMS files (default: 5).",
    )
    parser.add_argument(
        "--plot-every",
        type=positive_int,
        default=10,
        help=(
            "Refresh the aggregate plot after this many new spectrum files; "
            "the first and final spectra are always plotted (default: 10)."
        ),
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--spectra-dir", type=Path, default=Path("spectra"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--show-final",
        action="store_true",
        help="Open the final plot interactively after all processing completes.",
    )
    parser.add_argument(
        "--process-existing-only",
        action="store_true",
        help="Do not start NI-SCOPE capture; analyze and plot existing files once.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the subprocess commands without executing them.",
    )
    return parser


def resolved_from_script_dir(path: Path) -> Path:
    return path if path.is_absolute() else SCRIPT_DIR / path


def numbered_file_count(directory: Path, task_id: str, suffix: str) -> int:
    if not directory.is_dir():
        return 0
    pattern = re.compile(rf"^{re.escape(task_id)}_\d{{4,}}{re.escape(suffix)}$")
    return sum(
        path.is_file() and pattern.fullmatch(path.name) is not None
        for path in directory.iterdir()
    )


def completed_tdms_count(data_dir: Path, task_id: str) -> int:
    return numbered_file_count(data_dir / task_id, task_id, ".tdms")


def spectrum_count(spectra_dir: Path, task_id: str) -> int:
    return numbered_file_count(
        spectra_dir / task_id, task_id, "_spectrum.npz"
    )


def display_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    import shlex

    return shlex.join(command)


def run_step(label: str, command: list[str]) -> bool:
    print(f"\n[executor] {label}", flush=True)
    print(f"[executor] > {display_command(command)}", flush=True)
    result = subprocess.run(command, cwd=SCRIPT_DIR, check=False)
    if result.returncode != 0:
        print(
            f"[executor] WARNING: {label} exited with code {result.returncode}.",
            flush=True,
        )
        return False
    return True


def stop_capture_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    print("[executor] Asking the capture process to stop...", flush=True)
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=15)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    print("[executor] Capture did not stop in 15 s; terminating it.", flush=True)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    capture_script = SCRIPT_DIR / "capture_dut_revb_pmu_noise.py"
    analysis_script = SCRIPT_DIR / "analyze_dut_revb_pmu_noise.py"
    plot_script = SCRIPT_DIR / "plot_dut_revb_pmu_noise.py"
    missing = [
        str(path) for path in (capture_script, analysis_script, plot_script) if not path.is_file()
    ]
    if missing:
        print("ERROR: Missing required script(s):", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 2

    data_dir = resolved_from_script_dir(args.data_dir)
    spectra_dir = resolved_from_script_dir(args.spectra_dir)
    results_dir = resolved_from_script_dir(args.results_dir)

    python = sys.executable
    capture_command = [
        python,
        "-u",
        str(capture_script),
        "--task-id",
        args.task_id,
        "--runs",
        str(args.runs),
        "--resource",
        args.resource,
        "--channel",
        args.channel,
        "--sample-rate",
        str(args.sample_rate),
        "--samples",
        str(args.samples),
        "--input-impedance",
        str(args.input_impedance),
        "--vertical-range",
        str(args.vertical_range),
        "--gain",
        str(args.gain),
        "--gbw",
        str(args.gbw),
        "--timeout",
        str(args.timeout),
        "--output-dir",
        str(data_dir),
    ]
    analysis_command = [
        python,
        "-u",
        str(analysis_script),
        "--task-id",
        args.task_id,
        "--data-dir",
        str(data_dir),
        "--output-dir",
        str(spectra_dir),
        "--nperseg",
        str(args.nperseg),
    ]
    plot_command = [
        python,
        "-u",
        str(plot_script),
        "--task-id",
        args.task_id,
        "--spectra-dir",
        str(spectra_dir),
        "--output-dir",
        str(results_dir),
    ]

    print("[executor] DUT noise pipeline", flush=True)
    print(f"[executor] Python:   {python}", flush=True)
    print(f"[executor] task_id: {args.task_id}", flush=True)
    print(f"[executor] data:     {data_dir}", flush=True)
    print(f"[executor] spectra:  {spectra_dir}", flush=True)
    print(f"[executor] results:  {results_dir}", flush=True)
    print(f"[executor] plot every {args.plot_every} new spectrum file(s)", flush=True)

    if args.dry_run:
        if not args.process_existing_only:
            print(f"[executor] > {display_command(capture_command)}", flush=True)
        print(f"[executor] > {display_command(analysis_command)}", flush=True)
        final_plot_command = plot_command + (["--show"] if args.show_final else [])
        print(f"[executor] > {display_command(final_plot_command)}", flush=True)
        return 0

    last_analyzed_tdms_count = -1
    last_plotted_spectrum_count = -1

    def process_available_files(*, final: bool) -> bool:
        nonlocal last_analyzed_tdms_count, last_plotted_spectrum_count

        tdms_count = completed_tdms_count(data_dir, args.task_id)
        if tdms_count == 0:
            if final:
                print("[executor] No completed TDMS files are available.", flush=True)
            return True

        if final or tdms_count != last_analyzed_tdms_count:
            print(
                f"[executor] Detected {tdms_count} completed TDMS file(s).",
                flush=True,
            )
            analysis_ok = run_step("Analyze completed TDMS files", analysis_command)
            # Avoid retrying a persistent error every poll; a new file or the final
            # pass will trigger another attempt.
            last_analyzed_tdms_count = tdms_count
            if not analysis_ok:
                return False

        spectra_found = spectrum_count(spectra_dir, args.task_id)
        if spectra_found == 0:
            return True

        should_plot = (
            final
            or last_plotted_spectrum_count < 0
            or spectra_found >= last_plotted_spectrum_count + args.plot_every
        )
        if not should_plot:
            return True

        command = plot_command.copy()
        if final and args.show_final:
            command.append("--show")
        plot_ok = run_step(
            f"Plot aggregate spectrum from {spectra_found} file(s)", command
        )
        if plot_ok:
            last_plotted_spectrum_count = spectra_found
        return plot_ok

    if args.process_existing_only:
        return 0 if process_available_files(final=True) else 1

    print("\n[executor] Starting NI-SCOPE capture process...", flush=True)
    print(f"[executor] > {display_command(capture_command)}", flush=True)
    popen_kwargs: dict[str, object] = {"cwd": SCRIPT_DIR}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    capture_process = subprocess.Popen(capture_command, **popen_kwargs)
    interrupted = False
    pipeline_exception = False
    live_processing_ok = True
    try:
        while capture_process.poll() is None:
            if not process_available_files(final=False):
                live_processing_ok = False
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        interrupted = True
        print("\n[executor] Ctrl+C received.", flush=True)
        stop_capture_process(capture_process)
    except Exception as error:
        pipeline_exception = True
        print(f"\n[executor] ERROR: {error}", file=sys.stderr, flush=True)
        stop_capture_process(capture_process)

    capture_return_code = capture_process.wait()
    print(
        f"\n[executor] Capture process exited with code {capture_return_code}.",
        flush=True,
    )
    final_processing_ok = process_available_files(final=True)

    if interrupted:
        print(
            "[executor] Stopped by user; completed files were analyzed and plotted.",
            flush=True,
        )
        return 130
    if pipeline_exception:
        return 1
    if capture_return_code != 0:
        return capture_return_code
    if not live_processing_ok and final_processing_ok:
        print(
            "[executor] A live update failed, but the final processing pass succeeded.",
            flush=True,
        )
    if not final_processing_ok:
        return 1

    print("[executor] Capture, analysis, and final plot completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
