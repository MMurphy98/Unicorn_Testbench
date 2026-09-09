#!/usr/bin/env python3
"""Analyze numbered DMM7510 DCV TDMS records and plot equivalent offset."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

import matplotlib
import numpy as np
from nptdms import TdmsFile
from scipy.stats import t as student_t


DEFAULT_TASK_ID = "DUT_RevB_with_PMU"
MEASUREMENT_TYPE = "dcv_offset"
SUMMARY_FORMAT_VERSION = 1


@dataclass(frozen=True)
class DcvRecord:
    path: Path
    run_number: int
    acquisition_start_utc: datetime
    elapsed_s: np.ndarray
    readings_v: np.ndarray
    gain: float
    configuration: dict[str, object]


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
            "Read all numbered DMM7510 DCV TDMS files for one task, calculate "
            "output and input-equivalent offset statistics, and save plots, "
            "per-reading CSV data, and a JSON summary."
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
        default=project_dir / "results",
        help="Base results directory; a task-ID subdirectory is created",
    )
    parser.add_argument("--show", action="store_true")
    return parser.parse_args(argv)


def numbered_tdms_files(task_dir: Path, task_id: str) -> list[tuple[int, Path]]:
    pattern = re.compile(
        rf"^{re.escape(task_id)}_dcv_(\d+)\.tdms$", re.IGNORECASE
    )
    files: list[tuple[int, Path]] = []
    for path in task_dir.glob(f"{task_id}_dcv_*.tdms"):
        match = pattern.fullmatch(path.name)
        if match:
            files.append((int(match.group(1)), path))
    return sorted(files)


def required_property(properties: dict, name: str, location: str) -> object:
    if name not in properties:
        raise ValueError(f"Missing required property {name!r} in {location}.")
    return properties[name]


def required_string(properties: dict, name: str, location: str) -> str:
    value = str(required_property(properties, name, location))
    if not value:
        raise ValueError(f"Property {name!r} in {location} must not be empty.")
    return value


def required_positive_float(properties: dict, name: str, location: str) -> float:
    value = float(required_property(properties, name, location))
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(
            f"Property {name!r} in {location} must be positive and finite; "
            f"got {value!r}."
        )
    return value


def required_bool(properties: dict, name: str, location: str) -> bool:
    value = required_property(properties, name, location)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
        return bool(value)
    raise ValueError(f"Property {name!r} in {location} must be Boolean; got {value!r}.")


def tdms_timestamp_to_utc(value: object, location: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            raise ValueError(f"Timestamp in {location} is NaT.")
        microseconds = int(value.astype("datetime64[us]").astype(np.int64))
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return epoch + timedelta(microseconds=microseconds)
    raise ValueError(f"Unsupported timestamp {value!r} in {location}.")


def read_record(
    path: Path, expected_task_id: str, filename_run_number: int
) -> DcvRecord:
    tdms = TdmsFile.read(path)
    root = dict(tdms.properties)
    location = f"TDMS root of {path.name}"
    if int(required_property(root, "format_version", location)) != 1:
        raise ValueError(f"Unsupported TDMS format version in {path}.")
    if required_string(root, "measurement_type", location) != MEASUREMENT_TYPE:
        raise ValueError(f"Unexpected measurement type in {path}.")
    task_id = required_string(root, "task_id", location)
    if task_id != expected_task_id:
        raise ValueError(
            f"TDMS task ID {task_id!r} does not match {expected_task_id!r}: {path}"
        )
    run_number = int(required_property(root, "run_number", location))
    if run_number != filename_run_number:
        raise ValueError(
            f"TDMS run {run_number} does not match filename run "
            f"{filename_run_number}: {path}"
        )

    group_name = required_string(root, "tdms_group_name", location)
    dcv_name = required_string(root, "dcv_channel_name", location)
    elapsed_name = required_string(root, "elapsed_time_channel_name", location)
    try:
        dcv_channel = tdms[group_name][dcv_name]
        elapsed_channel = tdms[group_name][elapsed_name]
    except KeyError as exc:
        raise ValueError(f"Required DMM channels are missing in {path}.") from exc

    readings_v = dcv_channel[:]
    elapsed_s = elapsed_channel[:]
    for name, values in ((dcv_name, readings_v), (elapsed_name, elapsed_s)):
        if values.dtype != np.dtype(np.float64):
            raise TypeError(f"Expected float64 {name} in {path}; got {values.dtype}.")
        if values.ndim != 1 or not np.all(np.isfinite(values)):
            raise ValueError(f"Channel {name} is not finite and one-dimensional: {path}")
    if readings_v.size < 2 or readings_v.size != elapsed_s.size:
        raise ValueError(f"DMM channel lengths are invalid or unequal in {path}.")
    if int(required_property(root, "reading_count", location)) != readings_v.size:
        raise ValueError(f"TDMS reading_count does not match channel length in {path}.")
    if not np.all(np.diff(elapsed_s) > 0.0):
        raise ValueError(f"ElapsedTime is not strictly increasing in {path}.")

    gain = required_positive_float(root, "closed_loop_gain_v_per_v", location)
    configuration: dict[str, object] = {
        "instrument_manufacturer": required_string(
            root, "instrument_manufacturer", location
        ),
        "instrument_model": required_string(root, "instrument_model", location),
        "instrument_serial_number": required_string(
            root, "instrument_serial_number", location
        ),
        "instrument_firmware_revision": required_string(
            root, "instrument_firmware_revision", location
        ),
        "terminals": required_string(root, "terminals", location),
        "measurement_function": required_string(
            root, "measurement_function", location
        ),
        "range_v": required_positive_float(root, "actual_range_v", location),
        "autorange_enabled": required_bool(root, "autorange_enabled", location),
        "input_impedance_mode": required_string(
            root, "actual_input_impedance_mode", location
        ),
        "nplc": required_positive_float(root, "actual_nplc", location),
        "autozero_enabled": required_bool(root, "autozero_enabled", location),
        "dmm_averaging_enabled": required_bool(
            root, "dmm_averaging_enabled", location
        ),
        "relative_enabled": required_bool(root, "relative_enabled", location),
        "line_sync_enabled": required_bool(root, "line_sync_enabled", location),
        "line_frequency_hz": required_positive_float(
            root, "line_frequency_hz", location
        ),
        "closed_loop_gain_v_per_v": gain,
    }
    if not configuration["autozero_enabled"]:
        raise ValueError(f"Auto Zero was not enabled in {path}.")
    if configuration["dmm_averaging_enabled"]:
        raise ValueError(f"DMM internal averaging was enabled in {path}.")
    if configuration["autorange_enabled"]:
        raise ValueError(f"DCV autorange was enabled in {path}.")
    if configuration["relative_enabled"]:
        raise ValueError(f"REL/null was enabled in {path}.")
    if not configuration["line_sync_enabled"]:
        raise ValueError(f"Line synchronization was not enabled in {path}.")

    acquisition_start_utc = tdms_timestamp_to_utc(
        required_property(root, "acquisition_start_utc", location), location
    )
    return DcvRecord(
        path=path,
        run_number=run_number,
        acquisition_start_utc=acquisition_start_utc,
        elapsed_s=np.asarray(elapsed_s, dtype=np.float64),
        readings_v=np.asarray(readings_v, dtype=np.float64),
        gain=gain,
        configuration=configuration,
    )


def require_matching_configuration(
    reference: dict[str, object], candidate: dict[str, object], path: Path
) -> None:
    float_keys = {
        "range_v",
        "nplc",
        "line_frequency_hz",
        "closed_loop_gain_v_per_v",
    }
    for key, expected in reference.items():
        actual = candidate[key]
        if key in float_keys:
            matches = np.isclose(float(actual), float(expected), rtol=1e-12, atol=1e-15)
        else:
            matches = actual == expected
        if not matches:
            raise ValueError(
                f"Configuration mismatch in {path.name}: {key}={actual!r}, "
                f"expected {expected!r}. Use a different task ID for different settings."
            )


def descriptive_statistics(values: np.ndarray) -> dict[str, float | int]:
    if values.ndim != 1 or values.size < 2 or not np.all(np.isfinite(values)):
        raise ValueError("At least two finite values are required for statistics.")
    count = int(values.size)
    mean = float(np.mean(values))
    sample_std = float(np.std(values, ddof=1))
    standard_error = sample_std / np.sqrt(count)
    t_critical = float(student_t.ppf(0.975, count - 1))
    half_width = t_critical * standard_error
    return {
        "count": count,
        "mean": mean,
        "median": float(np.median(values)),
        "sample_std": sample_std,
        "standard_error": standard_error,
        "confidence_95_lower": mean - half_width,
        "confidence_95_upper": mean + half_width,
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def scale_statistics(
    statistics: dict[str, float | int], scale: float
) -> dict[str, float | int]:
    result: dict[str, float | int] = {"count": int(statistics["count"])}
    for key, value in statistics.items():
        if key != "count":
            result[key] = float(value) * scale
    return result


def cumulative_statistics(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    counts = np.arange(1, values.size + 1, dtype=np.float64)
    sums = np.cumsum(values, dtype=np.float64)
    squared_sums = np.cumsum(values * values, dtype=np.float64)
    means = sums / counts
    variance = np.full(values.size, np.nan, dtype=np.float64)
    variance[1:] = (
        squared_sums[1:] - sums[1:] * sums[1:] / counts[1:]
    ) / (counts[1:] - 1.0)
    variance[1:] = np.maximum(variance[1:], 0.0)
    standard_errors = np.sqrt(variance) / np.sqrt(counts)
    critical = np.full(values.size, np.nan, dtype=np.float64)
    critical[1:] = student_t.ppf(0.975, counts[1:] - 1.0)
    half_width = critical * standard_errors
    return means, means - half_width, means + half_width


def partial_path(path: Path) -> Path:
    return path.with_name(path.stem + ".partial" + path.suffix)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    task_data_dir = args.data_dir.expanduser().resolve() / args.task_id
    task_output_dir = args.output_dir.expanduser().resolve() / args.task_id
    files = numbered_tdms_files(task_data_dir, args.task_id)
    if not files:
        raise FileNotFoundError(
            f"No DMM TDMS files matching {args.task_id}_dcv_NNNN.tdms in "
            f"{task_data_dir}."
        )

    records = [read_record(path, args.task_id, run) for run, path in files]
    reference_configuration = records[0].configuration
    for record in records[1:]:
        require_matching_configuration(
            reference_configuration, record.configuration, record.path
        )

    gain = records[0].gain
    all_readings_v = np.concatenate([record.readings_v for record in records])
    all_input_v = all_readings_v / gain
    output_statistics_v = descriptive_statistics(all_readings_v)
    input_statistics_v = descriptive_statistics(all_input_v)

    timestamps: list[datetime] = []
    run_numbers: list[int] = []
    reading_indices: list[int] = []
    elapsed_values: list[float] = []
    per_run: list[dict[str, object]] = []
    run_means_v = np.empty(len(records), dtype=np.float64)
    for record_index, record in enumerate(records):
        run_statistics = descriptive_statistics(record.readings_v)
        run_means_v[record_index] = float(run_statistics["mean"])
        per_run.append(
            {
                "run_number": record.run_number,
                "source_file": str(record.path),
                "acquisition_start_utc": record.acquisition_start_utc.isoformat(),
                "output_voltage_v": run_statistics,
                "equivalent_input_offset_v": scale_statistics(
                    run_statistics, 1.0 / gain
                ),
            }
        )
        for index, elapsed in enumerate(record.elapsed_s, start=1):
            timestamps.append(
                record.acquisition_start_utc + timedelta(seconds=float(elapsed))
            )
            run_numbers.append(record.run_number)
            reading_indices.append(index)
            elapsed_values.append(float(elapsed))

    between_run_statistics_v: dict[str, float | int] | None = None
    if run_means_v.size >= 2:
        between_run_statistics_v = descriptive_statistics(run_means_v)

    task_output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.task_id
    plot_path = task_output_dir / f"{stem}_dcv_offset.png"
    csv_path = task_output_dir / f"{stem}_dcv_readings.csv"
    summary_path = task_output_dir / f"{stem}_dcv_offset_summary.json"

    csv_partial = partial_path(csv_path)
    with csv_partial.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(
            [
                "task_id",
                "run_number",
                "reading_index",
                "acquisition_time_utc",
                "elapsed_s",
                "output_voltage_v",
                "equivalent_input_offset_v",
            ]
        )
        for index, output_v in enumerate(all_readings_v):
            writer.writerow(
                [
                    args.task_id,
                    run_numbers[index],
                    reading_indices[index],
                    timestamps[index].isoformat(),
                    f"{elapsed_values[index]:.12e}",
                    f"{float(output_v):.12e}",
                    f"{float(output_v / gain):.12e}",
                ]
            )
    csv_partial.replace(csv_path)

    cumulative_mean_v, cumulative_lower_v, cumulative_upper_v = (
        cumulative_statistics(all_input_v)
    )
    reading_number = np.arange(1, all_input_v.size + 1)
    timestamps_array = np.asarray(timestamps, dtype=object)

    show_interactively = args.show
    try:
        figure, axes = plt.subplots(3, 1, figsize=(12, 11))
    except Exception as exc:
        if not args.show:
            raise
        print(
            f"WARNING: Interactive Matplotlib backend failed ({exc}); "
            "falling back to a saved PNG without an interactive window.",
            file=sys.stderr,
        )
        plt.switch_backend("Agg")
        show_interactively = False
        figure, axes = plt.subplots(3, 1, figsize=(12, 11))
    axes[0].scatter(
        timestamps_array,
        all_readings_v * 1e3,
        marker=".",
        s=18,
    )
    axes[0].axhline(
        float(output_statistics_v["mean"]) * 1e3,
        color="tab:red",
        linestyle="--",
        label=f"Mean: {float(output_statistics_v['mean']) * 1e3:+.6f} mV",
    )
    axes[0].set_ylabel("DMM output DCV (mV)")
    axes[0].set_title("Amplified DUT offset readings")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    axes[0].tick_params(axis="x", labelrotation=25)

    axes[1].plot(
        reading_number,
        cumulative_mean_v * 1e6,
        color="tab:blue",
        label="Cumulative mean",
    )
    axes[1].fill_between(
        reading_number,
        cumulative_lower_v * 1e6,
        cumulative_upper_v * 1e6,
        color="tab:blue",
        alpha=0.18,
        label="Descriptive 95% t interval",
    )
    final_input_mean_uv = float(input_statistics_v["mean"]) * 1e6
    axes[1].axhline(
        final_input_mean_uv,
        color="tab:red",
        linestyle="--",
        label=f"Final estimate: {final_input_mean_uv:+.6f} uV",
    )
    axes[1].set_xlabel("Reading number")
    axes[1].set_ylabel("Equivalent input offset (uV)")
    axes[1].set_title(f"Input-referred cumulative estimate (gain={gain:g})")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    axes[2].hist(
        all_input_v * 1e6,
        bins="auto",
        edgecolor="black",
        alpha=0.8,
    )
    axes[2].axvline(
        final_input_mean_uv,
        color="tab:red",
        linestyle="--",
        label="Mean",
    )
    axes[2].axvline(
        float(input_statistics_v["median"]) * 1e6,
        color="tab:orange",
        linestyle=":",
        label="Median",
    )
    axes[2].set_xlabel("Equivalent input offset (uV)")
    axes[2].set_ylabel("Count")
    axes[2].set_title("Input-referred offset distribution")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    figure.suptitle(
        f"{args.task_id}: DMM7510 DCV offset ({len(records)} run(s), "
        f"{all_readings_v.size} readings)"
    )
    figure.tight_layout()
    plot_partial = partial_path(plot_path)
    figure.savefig(plot_partial, dpi=220)
    plot_partial.replace(plot_path)

    summary: dict[str, object] = {
        "format_version": SUMMARY_FORMAT_VERSION,
        "task_id": args.task_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_count": len(records),
        "total_reading_count": int(all_readings_v.size),
        "source_files": [str(record.path) for record in records],
        "configuration": reference_configuration,
        "output_voltage_v": output_statistics_v,
        "equivalent_input_offset_v": input_statistics_v,
        "per_run": per_run,
        "between_run_output_mean_v": between_run_statistics_v,
        "between_run_equivalent_input_mean_v": (
            scale_statistics(between_run_statistics_v, 1.0 / gain)
            if between_run_statistics_v is not None
            else None
        ),
        "uncertainty_note": (
            "Standard errors and 95% t intervals are descriptive repeatability "
            "statistics. They assume independent readings and do not include DMM "
            "calibration uncertainty, thermoelectric EMF, gain error, or correlated "
            "DUT temperature and low-frequency drift."
        ),
        "plot": str(plot_path),
        "readings_csv": str(csv_path),
    }
    summary_partial = partial_path(summary_path)
    summary_partial.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary_partial.replace(summary_path)

    print(f"Task: {args.task_id}")
    print(f"Runs/readings: {len(records)}/{all_readings_v.size}")
    print(
        f"Output offset: {float(output_statistics_v['mean']) * 1e3:+.9f} mV "
        f"(sample std {float(output_statistics_v['sample_std']) * 1e6:.6f} uV, "
        f"SEM {float(output_statistics_v['standard_error']) * 1e6:.6f} uV)"
    )
    print(
        f"Equivalent input offset: {final_input_mean_uv:+.9f} uV "
        f"(sample std {float(input_statistics_v['sample_std']) * 1e9:.6f} nV, "
        f"SEM {float(input_statistics_v['standard_error']) * 1e9:.6f} nV, "
        "descriptive 95% interval "
        f"{float(input_statistics_v['confidence_95_lower']) * 1e6:+.9f} to "
        f"{float(input_statistics_v['confidence_95_upper']) * 1e6:+.9f} uV)"
    )
    if between_run_statistics_v is not None:
        print(
            "Between-run input-equivalent mean variation: "
            f"std={float(between_run_statistics_v['sample_std']) / gain * 1e9:.6f} nV"
        )
    print(f"Plot: {plot_path}")
    print(f"Readings CSV: {csv_path}")
    print(f"Summary JSON: {summary_path}")

    if show_interactively:
        plt.show()
    else:
        plt.close(figure)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
