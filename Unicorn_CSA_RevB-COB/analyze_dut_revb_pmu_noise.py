#!/usr/bin/env python3
"""Convert numbered DUT noise TDMS captures into per-run Welch spectra."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

import numpy as np
from nptdms import TdmsFile
from scipy.signal import welch


DEFAULT_TASK_ID = "DUT_RevB_with_PMU"
DEFAULT_NPERSEG = 262_144
SPECTRUM_FORMAT_VERSION = 1


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
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
            "Read each numbered TDMS capture for a task, calculate a one-sided "
            "Welch input-referred PSD, and save one compressed NPZ spectrum per run."
        )
    )
    parser.add_argument("--task-id", type=task_id_value, default=DEFAULT_TASK_ID)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=project_dir / "data",
        help="Base data directory containing the task-ID subdirectory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "spectra",
        help="Base spectrum directory; a task-ID subdirectory is created",
    )
    parser.add_argument("--nperseg", type=positive_int, default=DEFAULT_NPERSEG)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recalculate spectra that already exist",
    )
    return parser.parse_args(argv)


def numbered_tdms_files(task_dir: Path, task_id: str) -> list[tuple[int, Path]]:
    pattern = re.compile(rf"^{re.escape(task_id)}_(\d+)\.tdms$", re.IGNORECASE)
    matches: list[tuple[int, Path]] = []
    for path in task_dir.glob(f"{task_id}_*.tdms"):
        match = pattern.fullmatch(path.name)
        if match:
            matches.append((int(match.group(1)), path))
    return sorted(matches)


def required_property(properties: dict, name: str, location: str) -> object:
    if name not in properties:
        raise ValueError(f"Missing required property {name!r} in {location}.")
    return properties[name]


def required_positive_float(properties: dict, name: str, location: str) -> float:
    value = float(required_property(properties, name, location))
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(
            f"Property {name!r} in {location} must be positive and finite; "
            f"got {value!r}."
        )
    return value


def read_capture(
    tdms_path: Path, expected_task_id: str
) -> tuple[np.ndarray, float, float, float, int, str]:
    tdms = TdmsFile.read(tdms_path)
    root_properties = dict(tdms.properties)
    task_id = str(required_property(root_properties, "task_id", "TDMS root"))
    if task_id != expected_task_id:
        raise ValueError(
            f"TDMS task ID {task_id!r} does not match {expected_task_id!r}: "
            f"{tdms_path}"
        )
    group_name = str(
        required_property(root_properties, "tdms_group_name", "TDMS root")
    )
    channel_name = str(
        required_property(root_properties, "tdms_channel_name", "TDMS root")
    )
    run_number = int(required_property(root_properties, "run_number", "TDMS root"))
    closed_loop_gain = required_positive_float(
        root_properties, "closed_loop_gain_v_per_v", "TDMS root"
    )
    closed_loop_bandwidth_hz = required_positive_float(
        root_properties, "estimated_closed_loop_bandwidth_hz", "TDMS root"
    )

    try:
        channel = tdms[group_name][channel_name]
    except KeyError as exc:
        raise ValueError(
            f"TDMS channel {group_name!r}/{channel_name!r} does not exist in "
            f"{tdms_path}."
        ) from exc

    samples_v = channel[:]
    if samples_v.dtype != np.dtype(np.float64):
        raise TypeError(f"Expected float64 samples in {tdms_path}; got {samples_v.dtype}.")
    if samples_v.ndim != 1 or not np.all(np.isfinite(samples_v)):
        raise ValueError(f"TDMS waveform is not a finite one-dimensional array: {tdms_path}")
    sample_interval_s = required_positive_float(
        dict(channel.properties), "wf_increment", f"{group_name}/{channel_name}"
    )
    return (
        np.asarray(samples_v, dtype=np.float64),
        1.0 / sample_interval_s,
        closed_loop_gain,
        closed_loop_bandwidth_hz,
        run_number,
        channel_name,
    )


def calculate_input_psd(
    samples_v: np.ndarray,
    sample_rate_hz: float,
    closed_loop_gain: float,
    nperseg: int,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    if samples_v.size < nperseg:
        raise ValueError(
            f"Capture has {samples_v.size:,} samples, fewer than "
            f"nperseg={nperseg:,}."
        )
    noverlap = nperseg // 2
    hop = nperseg - noverlap
    segment_count = 1 + (samples_v.size - nperseg) // hop
    frequency_hz, output_psd_v2_per_hz = welch(
        samples_v,
        fs=sample_rate_hz,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend="constant",
        return_onesided=True,
        scaling="density",
        average="mean",
    )
    input_psd_v2_per_hz = output_psd_v2_per_hz / closed_loop_gain**2
    return frequency_hz, input_psd_v2_per_hz, segment_count, sample_rate_hz / nperseg


def nearest_asd(
    frequency_hz: np.ndarray, input_psd_v2_per_hz: np.ndarray, target_hz: float
) -> tuple[float, float]:
    positive = np.flatnonzero(frequency_hz > 0.0)
    index = positive[np.argmin(np.abs(frequency_hz[positive] - target_hz))]
    return (
        float(frequency_hz[index]),
        float(np.sqrt(input_psd_v2_per_hz[index]) * 1.0e9),
    )


def save_spectrum(
    output_path: Path,
    *,
    overwrite: bool,
    frequency_hz: np.ndarray,
    input_psd_v2_per_hz: np.ndarray,
    source_tdms: Path,
    task_id: str,
    run_number: int,
    channel_name: str,
    sample_rate_hz: float,
    closed_loop_gain: float,
    closed_loop_bandwidth_hz: float,
    sample_count: int,
    nperseg: int,
    segment_count: int,
    frequency_resolution_hz: float,
) -> None:
    partial_path = output_path.with_suffix(".partial.npz")
    if partial_path.exists():
        raise FileExistsError(
            f"Partial spectrum already exists; inspect or remove it: {partial_path}"
        )
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite spectrum: {output_path}")
    with partial_path.open("wb") as stream:
        np.savez_compressed(
            stream,
            format_version=np.int64(SPECTRUM_FORMAT_VERSION),
            frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
            input_psd_v2_per_hz=np.asarray(input_psd_v2_per_hz, dtype=np.float64),
            source_tdms=np.str_(str(source_tdms.resolve())),
            task_id=np.str_(task_id),
            run_number=np.int64(run_number),
            channel_name=np.str_(channel_name),
            sample_rate_hz=np.float64(sample_rate_hz),
            closed_loop_gain_v_per_v=np.float64(closed_loop_gain),
            estimated_closed_loop_bandwidth_hz=np.float64(
                closed_loop_bandwidth_hz
            ),
            source_sample_count=np.int64(sample_count),
            welch_window=np.str_("hann"),
            welch_nperseg=np.int64(nperseg),
            welch_noverlap=np.int64(nperseg // 2),
            welch_detrend=np.str_("constant"),
            welch_average=np.str_("mean"),
            welch_segment_count=np.int64(segment_count),
            frequency_resolution_hz=np.float64(frequency_resolution_hz),
        )
    partial_path.replace(output_path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    task_data_dir = args.data_dir.expanduser().resolve() / args.task_id
    task_output_dir = args.output_dir.expanduser().resolve() / args.task_id
    captures = numbered_tdms_files(task_data_dir, args.task_id)
    if not captures:
        raise FileNotFoundError(
            f"No numbered TDMS files found for task {args.task_id!r} in "
            f"{task_data_dir}."
        )
    task_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Task: {args.task_id}")
    print(f"TDMS input: {task_data_dir}")
    print(f"Spectrum output: {task_output_dir}")
    print(f"Found {len(captures)} TDMS file(s); Welch nperseg={args.nperseg:,}.")

    processed = 0
    skipped = 0
    for position, (filename_run_number, tdms_path) in enumerate(captures, start=1):
        output_path = task_output_dir / f"{tdms_path.stem}_spectrum.npz"
        if output_path.exists() and not args.overwrite:
            skipped += 1
            print(
                f"[{position:03d}/{len(captures):03d}] Skip existing "
                f"{output_path.name}"
            )
            continue
        (
            samples_v,
            sample_rate_hz,
            closed_loop_gain,
            closed_loop_bandwidth_hz,
            metadata_run_number,
            channel_name,
        ) = read_capture(tdms_path, args.task_id)
        if metadata_run_number != filename_run_number:
            raise ValueError(
                f"Run number mismatch in {tdms_path}: filename="
                f"{filename_run_number}, metadata={metadata_run_number}."
            )
        frequency_hz, input_psd_v2_per_hz, segment_count, df_hz = (
            calculate_input_psd(
                samples_v,
                sample_rate_hz,
                closed_loop_gain,
                args.nperseg,
            )
        )
        save_spectrum(
            output_path,
            overwrite=args.overwrite,
            frequency_hz=frequency_hz,
            input_psd_v2_per_hz=input_psd_v2_per_hz,
            source_tdms=tdms_path,
            task_id=args.task_id,
            run_number=metadata_run_number,
            channel_name=channel_name,
            sample_rate_hz=sample_rate_hz,
            closed_loop_gain=closed_loop_gain,
            closed_loop_bandwidth_hz=closed_loop_bandwidth_hz,
            sample_count=samples_v.size,
            nperseg=args.nperseg,
            segment_count=segment_count,
            frequency_resolution_hz=df_hz,
        )
        one_hz = nearest_asd(frequency_hz, input_psd_v2_per_hz, 1.0)
        one_khz = nearest_asd(frequency_hz, input_psd_v2_per_hz, 1_000.0)
        processed += 1
        print(
            f"[{position:03d}/{len(captures):03d}] Saved {output_path.name} | "
            f"1 Hz target: {one_hz[0]:.6f} Hz, {one_hz[1]:.6g} nV/sqrt(Hz); "
            f"1 kHz target: {one_khz[0]:.6f} Hz, "
            f"{one_khz[1]:.6g} nV/sqrt(Hz)"
        )

    print(f"Completed: {processed} processed, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
