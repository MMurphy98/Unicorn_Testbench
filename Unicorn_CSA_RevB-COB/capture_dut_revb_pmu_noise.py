#!/usr/bin/env python3
"""Acquire numbered NI-SCOPE TDMS records for DUT noise measurements."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import re
import subprocess
import sys
import time

import niscope
import numpy as np
from nptdms import ChannelObject, GroupObject, RootObject, TdmsFile, TdmsWriter


DEFAULT_TASK_ID = "DUT_RevB_with_PMU"
TDMS_GROUP_NAME = "DUT RevB with PMU"
NPTDMS_VERSION = "1.11.0"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def task_id_value(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError(
            "task ID must start with a letter or digit and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Acquire consecutive NI-SCOPE records and write verified, numbered "
            "float64 TDMS files without overwriting earlier runs."
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "data",
        help="Base data directory; a task-ID subdirectory is created",
    )
    return parser.parse_args(argv)


def check_runtime() -> None:
    installed = version("nptdms")
    if installed != NPTDMS_VERSION:
        raise RuntimeError(
            f"nptdms=={NPTDMS_VERSION} is required; found {installed}. "
            f"Run: {sys.executable} -m pip install nptdms=={NPTDMS_VERSION}"
        )

    tasklist = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq InstrumentStudio.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "instrumentstudio.exe" in tasklist.stdout.lower():
        raise RuntimeError("Close InstrumentStudio before starting acquisition.")


def tdms_channel_name(physical_channel: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", physical_channel).strip("_")
    if not cleaned:
        raise ValueError(f"Cannot form a TDMS channel name from {physical_channel!r}.")
    return f"CH{cleaned}"


def existing_run_numbers(task_dir: Path, task_id: str) -> list[int]:
    pattern = re.compile(
        rf"^{re.escape(task_id)}_(\d+)\.(?:partial\.)?tdms$", re.IGNORECASE
    )
    numbers: list[int] = []
    for path in task_dir.glob(f"{task_id}_*.tdms"):
        match = pattern.fullmatch(path.name)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def next_run_number(task_dir: Path, task_id: str) -> int:
    numbers = existing_run_numbers(task_dir, task_id)
    return max(numbers, default=0) + 1


def require_close(actual: float, requested: float, description: str) -> None:
    if not np.isclose(actual, requested, rtol=1e-9, atol=1e-6):
        raise RuntimeError(
            f"Actual {description} is {actual!r}, not requested {requested!r}; "
            "no acquisition files were written."
        )


def write_verified_tdms(
    *,
    partial_path: Path,
    final_path: Path,
    samples_v: np.ndarray,
    acquisition_start_utc: datetime,
    waveform_info: object,
    args: argparse.Namespace,
    run_number: int,
    actual_sample_rate_hz: float,
    actual_record_length: int,
    actual_vertical_range_vpp: float,
    actual_input_impedance_ohm: float,
    instrument_metadata: dict[str, str],
    channel_name: str,
) -> tuple[float, float, float, bool]:
    if partial_path.exists() or final_path.exists():
        raise FileExistsError(f"Refusing to overwrite {partial_path} or {final_path}.")
    if samples_v.dtype != np.dtype(np.float64) or samples_v.size != args.samples:
        raise RuntimeError(
            f"Unexpected waveform array: shape={samples_v.shape}, dtype={samples_v.dtype}."
        )
    if not np.all(np.isfinite(samples_v)):
        raise RuntimeError("Waveform contains NaN or infinite samples.")

    sample_interval_s = float(waveform_info.x_increment)
    require_close(
        1.0 / sample_interval_s,
        actual_sample_rate_hz,
        "waveform sample rate",
    )

    dc_mean_v = float(np.mean(samples_v))
    ac_rms_v = float(np.sqrt(np.mean((samples_v - dc_mean_v) ** 2)))
    peak_to_peak_v = float(np.ptp(samples_v))
    peak_from_center_v = float(np.max(np.abs(samples_v)))
    near_clipping = peak_from_center_v >= 0.98 * (actual_vertical_range_vpp / 2.0)

    root_properties = {
        "format_version": 1,
        "task_id": args.task_id,
        "run_number": run_number,
        "test_target": "DUT RevB (with PMU)",
        "dut_revision": "RevB",
        "pmu_enabled": True,
        "closed_loop_gain_v_per_v": args.gain,
        "op_amp_gbw_hz": args.gbw,
        "estimated_closed_loop_bandwidth_hz": args.gbw / args.gain,
        "resource_name": args.resource,
        "tdms_group_name": TDMS_GROUP_NAME,
        "tdms_channel_name": channel_name,
        "acquisition_start_utc": acquisition_start_utc.replace(tzinfo=None),
        **instrument_metadata,
    }
    channel_properties = {
        "unit_string": "V",
        "wf_xname": "Time",
        "wf_xunit_string": "s",
        "wf_increment": sample_interval_s,
        "wf_start_offset": float(waveform_info.relative_initial_x),
        "wf_start_time": acquisition_start_utc.replace(tzinfo=None),
        "wf_samples": args.samples,
        "requested_sample_rate_hz": args.sample_rate,
        "actual_sample_rate_hz": actual_sample_rate_hz,
        "requested_sample_count": args.samples,
        "actual_record_length": actual_record_length,
        "actual_duration_s": args.samples / actual_sample_rate_hz,
        "vertical_range_vpp": actual_vertical_range_vpp,
        "vertical_offset_v": 0.0,
        "input_impedance_ohm": actual_input_impedance_ohm,
        "coupling": "DC",
        "max_input_frequency_hz": -1.0,
        "trigger_type": "Immediate",
        "physical_channel": args.channel,
        "fetch_dtype": str(samples_v.dtype),
        "dc_mean_v": dc_mean_v,
        "ac_rms_v": ac_rms_v,
        "peak_to_peak_v": peak_to_peak_v,
        "near_clipping": near_clipping,
    }

    with TdmsWriter(partial_path, index_file=False) as writer:
        writer.write_segment(
            [
                RootObject(properties=root_properties),
                GroupObject(
                    TDMS_GROUP_NAME,
                    properties={
                        "description": (
                            "DUT RevB with PMU, closed-loop gain noise capture"
                        )
                    },
                ),
                ChannelObject(
                    TDMS_GROUP_NAME,
                    channel_name,
                    samples_v,
                    properties=channel_properties,
                ),
            ]
        )

    verification = TdmsFile.read(partial_path)
    verification_channel = verification[TDMS_GROUP_NAME][channel_name]
    stored_samples_v = verification_channel[:]
    stored_interval_s = float(verification_channel.properties["wf_increment"])
    if stored_samples_v.dtype != np.dtype(np.float64):
        raise RuntimeError(f"TDMS dtype verification failed: {stored_samples_v.dtype}.")
    if stored_samples_v.size != args.samples:
        raise RuntimeError(
            f"TDMS sample-count verification failed: {stored_samples_v.size:,}."
        )
    if stored_interval_s != sample_interval_s:
        raise RuntimeError(
            f"TDMS interval verification failed: {stored_interval_s!r}."
        )
    if not np.array_equal(stored_samples_v, samples_v):
        raise RuntimeError("TDMS round-trip sample comparison failed.")

    partial_path.rename(final_path)
    return dc_mean_v, ac_rms_v, peak_to_peak_v, near_clipping


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    check_runtime()

    output_base = args.output_dir.expanduser().resolve()
    task_dir = output_base / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    channel_name = tdms_channel_name(args.channel)
    duration_s = args.samples / args.sample_rate
    samples_v = np.empty(args.samples, dtype=np.float64)

    first_number = next_run_number(task_dir, args.task_id)
    print(f"Task: {args.task_id}")
    print(f"Output: {task_dir}")
    print(f"Runs requested: {args.runs}; first run number: {first_number:04d}")
    print(
        f"Resource/channel: {args.resource}/{args.channel}; "
        f"{args.sample_rate:,.9f} Sa/s; {args.samples:,} samples; "
        f"{duration_s:.9f} s/record"
    )
    print(
        f"Input: {args.input_impedance:g} ohm, {args.vertical_range:g} Vpp, "
        "DC coupling, full instrument bandwidth"
    )

    batch_start = time.monotonic()
    with niscope.Session(args.resource, reset_device=False) as scope:
        channel = scope.channels[args.channel]
        channel.configure_vertical(
            range=args.vertical_range,
            coupling=niscope.VerticalCoupling.DC,
            offset=0.0,
            probe_attenuation=1.0,
            enabled=True,
        )
        channel.configure_chan_characteristics(
            input_impedance=args.input_impedance,
            max_input_frequency=-1.0,
        )
        scope.configure_horizontal_timing(
            min_sample_rate=args.sample_rate,
            min_num_pts=args.samples,
            ref_position=0.0,
            num_records=1,
            enforce_realtime=True,
        )
        scope.configure_trigger_immediate()

        actual_sample_rate_hz = float(scope.horz_sample_rate)
        actual_record_length = int(scope.horz_record_length)
        actual_vertical_range_vpp = float(channel.vertical_range)
        actual_input_impedance_ohm = float(channel.input_impedance)
        require_close(actual_sample_rate_hz, args.sample_rate, "sample rate")
        if actual_record_length < args.samples:
            raise RuntimeError(
                f"Actual record length {actual_record_length:,} is less than "
                f"requested {args.samples:,}; no acquisition files were written."
            )
        require_close(
            actual_vertical_range_vpp, args.vertical_range, "vertical range"
        )
        require_close(
            actual_input_impedance_ohm,
            args.input_impedance,
            "input impedance",
        )

        instrument_metadata = {
            "instrument_manufacturer": str(scope.instrument_manufacturer),
            "instrument_model": str(scope.instrument_model),
            "instrument_serial_number": str(scope.serial_number),
            "instrument_firmware_revision": str(scope.instrument_firmware_revision),
            "ni_scope_driver_version": str(scope.specific_driver_revision),
        }
        print(
            f"Instrument: {instrument_metadata['instrument_manufacturer']} "
            f"{instrument_metadata['instrument_model']}, serial "
            f"{instrument_metadata['instrument_serial_number']}"
        )
        print(
            f"Verified actual configuration: {actual_sample_rate_hz:,.9f} Sa/s, "
            f"record length {actual_record_length:,}, "
            f"{actual_input_impedance_ohm:g} ohm, "
            f"{actual_vertical_range_vpp:g} Vpp"
        )

        for completed in range(args.runs):
            run_number = next_run_number(task_dir, args.task_id)
            stem = f"{args.task_id}_{run_number:04d}"
            final_path = task_dir / f"{stem}.tdms"
            partial_path = task_dir / f"{stem}.partial.tdms"
            acquisition_start_utc = datetime.now(timezone.utc)
            run_start = time.monotonic()
            print(
                f"[{completed + 1:03d}/{args.runs:03d}] Acquiring run "
                f"{run_number:04d}...",
                flush=True,
            )
            with scope.initiate():
                waveform_info = channel.fetch_into(
                    samples_v, timeout=args.timeout
                )[0]

            dc_mean_v, ac_rms_v, peak_to_peak_v, near_clipping = (
                write_verified_tdms(
                    partial_path=partial_path,
                    final_path=final_path,
                    samples_v=samples_v,
                    acquisition_start_utc=acquisition_start_utc,
                    waveform_info=waveform_info,
                    args=args,
                    run_number=run_number,
                    actual_sample_rate_hz=actual_sample_rate_hz,
                    actual_record_length=actual_record_length,
                    actual_vertical_range_vpp=actual_vertical_range_vpp,
                    actual_input_impedance_ohm=actual_input_impedance_ohm,
                    instrument_metadata=instrument_metadata,
                    channel_name=channel_name,
                )
            )
            elapsed = time.monotonic() - batch_start
            mean_run_time = elapsed / (completed + 1)
            eta_s = mean_run_time * (args.runs - completed - 1)
            print(
                f"[{completed + 1:03d}/{args.runs:03d}] Saved {final_path.name} | "
                f"mean={dc_mean_v:.6g} V, AC RMS={ac_rms_v:.6g} V, "
                f"Vpp={peak_to_peak_v:.6g} V, near clipping={near_clipping} | "
                f"run time={time.monotonic() - run_start:.1f} s, "
                f"ETA={eta_s / 60.0:.1f} min",
                flush=True,
            )

    print(
        f"Completed {args.runs} run(s) in "
        f"{(time.monotonic() - batch_start) / 60.0:.2f} min."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAcquisition interrupted by user; existing verified TDMS files remain valid.")
        raise SystemExit(130)
