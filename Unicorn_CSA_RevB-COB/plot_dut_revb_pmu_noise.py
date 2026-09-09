#!/usr/bin/env python3
"""Average saved DUT noise PSDs and plot raw and smoothed ASD estimates."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re

import matplotlib
import numpy as np


DEFAULT_TASK_ID = "DUT_RevB_with_PMU"
PLOT_FMIN_HZ = 1.0
PLOT_FMAX_HZ = 25_000.0
TARGET_FREQUENCIES_HZ = (1.0, 1_000.0)
SMOOTHING_FULL_WIDTH_OCTAVE = 1.0 / 6.0
SMOOTHING_MINIMUM_BINS = 5


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
            "Average per-run input-referred PSD files, convert the average to "
            "nV/sqrt(Hz), and plot the exact and smoothed estimates."
        )
    )
    parser.add_argument("--task-id", type=task_id_value, default=DEFAULT_TASK_ID)
    parser.add_argument(
        "--spectra-dir",
        type=Path,
        default=project_dir / "spectra",
        help="Base spectrum directory containing the task-ID subdirectory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "results",
        help="Base result directory; a task-ID subdirectory is created",
    )
    parser.add_argument("--show", action="store_true")
    return parser.parse_args(argv)


def numbered_spectrum_files(
    task_dir: Path, task_id: str
) -> list[tuple[int, Path]]:
    pattern = re.compile(
        rf"^{re.escape(task_id)}_(\d+)_spectrum\.npz$", re.IGNORECASE
    )
    matches: list[tuple[int, Path]] = []
    for path in task_dir.glob(f"{task_id}_*_spectrum.npz"):
        match = pattern.fullmatch(path.name)
        if match:
            matches.append((int(match.group(1)), path))
    return sorted(matches)


def scalar(archive: np.lib.npyio.NpzFile, name: str) -> object:
    if name not in archive.files:
        raise ValueError(f"Spectrum archive is missing {name!r}.")
    return archive[name].item()


def load_average_psd(
    files: list[tuple[int, Path]], expected_task_id: str
) -> tuple[
    np.ndarray,
    np.ndarray,
    float,
    int,
    int,
    float,
    np.ndarray,
    dict[float, np.ndarray],
]:
    reference_frequency_hz: np.ndarray | None = None
    mean_input_psd_v2_per_hz: np.ndarray | None = None
    reference_bandwidth_hz: float | None = None
    reference_nperseg: int | None = None
    total_welch_segments = 0
    run_numbers: list[int] = []
    target_asd_by_frequency: dict[float, list[float]] = {
        target_hz: [] for target_hz in TARGET_FREQUENCIES_HZ
    }

    for count, (filename_run_number, path) in enumerate(files, start=1):
        with np.load(path, allow_pickle=False) as archive:
            task_id = str(scalar(archive, "task_id"))
            run_number = int(scalar(archive, "run_number"))
            if task_id != expected_task_id or run_number != filename_run_number:
                raise ValueError(
                    f"Task/run metadata mismatch in {path}: "
                    f"task={task_id!r}, run={run_number}."
                )
            frequency_hz = np.asarray(archive["frequency_hz"], dtype=np.float64)
            input_psd = np.asarray(
                archive["input_psd_v2_per_hz"], dtype=np.float64
            )
            bandwidth_hz = float(
                scalar(archive, "estimated_closed_loop_bandwidth_hz")
            )
            nperseg = int(scalar(archive, "welch_nperseg"))
            segment_count = int(scalar(archive, "welch_segment_count"))

        if (
            frequency_hz.ndim != 1
            or input_psd.shape != frequency_hz.shape
            or not np.all(np.isfinite(frequency_hz))
            or not np.all(np.isfinite(input_psd))
            or np.any(input_psd < 0.0)
        ):
            raise ValueError(f"Invalid frequency or PSD data in {path}.")

        if reference_frequency_hz is None:
            reference_frequency_hz = frequency_hz.copy()
            mean_input_psd_v2_per_hz = input_psd.copy()
            reference_bandwidth_hz = bandwidth_hz
            reference_nperseg = nperseg
        else:
            if not np.array_equal(frequency_hz, reference_frequency_hz):
                raise ValueError(
                    f"Frequency grid in {path} differs from earlier spectra."
                )
            if not np.isclose(
                bandwidth_hz, reference_bandwidth_hz, rtol=1e-12, atol=0.0
            ):
                raise ValueError(f"Closed-loop bandwidth mismatch in {path}.")
            if nperseg != reference_nperseg:
                raise ValueError(f"Welch nperseg mismatch in {path}.")
            mean_input_psd_v2_per_hz += (
                input_psd - mean_input_psd_v2_per_hz
            ) / count
        run_numbers.append(run_number)
        for target_hz in TARGET_FREQUENCIES_HZ:
            target_asd_by_frequency[target_hz].append(
                local_power_estimate(frequency_hz, input_psd, target_hz)[0]
            )
        total_welch_segments += segment_count

    assert reference_frequency_hz is not None
    assert mean_input_psd_v2_per_hz is not None
    assert reference_bandwidth_hz is not None
    assert reference_nperseg is not None
    return (
        reference_frequency_hz,
        mean_input_psd_v2_per_hz,
        reference_bandwidth_hz,
        reference_nperseg,
        total_welch_segments,
        float(reference_frequency_hz[1] - reference_frequency_hz[0]),
        np.asarray(run_numbers, dtype=np.int64),
        {
            target_hz: np.asarray(values, dtype=np.float64)
            for target_hz, values in target_asd_by_frequency.items()
        },
    )


def local_power_estimate(
    frequency_hz: np.ndarray,
    input_psd_v2_per_hz: np.ndarray,
    center_hz: float,
) -> tuple[float, float, float, int]:
    half_width_octave = SMOOTHING_FULL_WIDTH_OCTAVE / 2.0
    ratio = 2.0**half_width_octave
    lower_hz = center_hz / ratio
    upper_hz = center_hz * ratio
    indices = np.flatnonzero(
        (frequency_hz > 0.0)
        & (frequency_hz >= lower_hz)
        & (frequency_hz <= upper_hz)
    )

    if indices.size < SMOOTHING_MINIMUM_BINS:
        positive = np.flatnonzero(frequency_hz > 0.0)
        nearest_position = int(
            np.argmin(np.abs(frequency_hz[positive] - center_hz))
        )
        half_count = SMOOTHING_MINIMUM_BINS // 2
        start = max(0, nearest_position - half_count)
        stop = min(positive.size, start + SMOOTHING_MINIMUM_BINS)
        start = max(0, stop - SMOOTHING_MINIMUM_BINS)
        indices = positive[start:stop]

    estimate_asd_nv_per_rt_hz = float(
        np.sqrt(np.mean(input_psd_v2_per_hz[indices])) * 1.0e9
    )
    return (
        estimate_asd_nv_per_rt_hz,
        float(frequency_hz[indices[0]]),
        float(frequency_hz[indices[-1]]),
        int(indices.size),
    )


def smoothed_curve(
    frequency_hz: np.ndarray,
    input_psd_v2_per_hz: np.ndarray,
    lower_hz: float,
    upper_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    centers_hz = np.geomspace(lower_hz, upper_hz, 360)
    estimates = np.array(
        [
            local_power_estimate(frequency_hz, input_psd_v2_per_hz, center)[0]
            for center in centers_hz
        ],
        dtype=np.float64,
    )
    return centers_hz, estimates


def nearest_bin_estimate(
    frequency_hz: np.ndarray,
    input_psd_v2_per_hz: np.ndarray,
    target_hz: float,
) -> tuple[float, float]:
    positive = np.flatnonzero(frequency_hz > 0.0)
    index = positive[np.argmin(np.abs(frequency_hz[positive] - target_hz))]
    return (
        float(frequency_hz[index]),
        float(np.sqrt(input_psd_v2_per_hz[index]) * 1.0e9),
    )


def distribution_statistics(
    values: np.ndarray,
) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("Distribution values must be a non-empty finite vector.")
    percentiles = np.percentile(values, [2.5, 25.0, 50.0, 75.0, 97.5])
    sample_std = float(np.std(values, ddof=1)) if values.size > 1 else None
    mean_value = float(np.mean(values))
    return {
        "count": int(values.size),
        "mean_asd_nv_per_sqrt_hz": mean_value,
        "sample_std_asd_nv_per_sqrt_hz": sample_std,
        "coefficient_of_variation_percent": (
            100.0 * sample_std / mean_value if sample_std is not None else None
        ),
        "minimum_asd_nv_per_sqrt_hz": float(np.min(values)),
        "percentile_2p5_asd_nv_per_sqrt_hz": float(percentiles[0]),
        "percentile_25_asd_nv_per_sqrt_hz": float(percentiles[1]),
        "median_asd_nv_per_sqrt_hz": float(percentiles[2]),
        "percentile_75_asd_nv_per_sqrt_hz": float(percentiles[3]),
        "percentile_97p5_asd_nv_per_sqrt_hz": float(percentiles[4]),
        "maximum_asd_nv_per_sqrt_hz": float(np.max(values)),
    }


def write_target_distribution_csv(
    path: Path,
    run_numbers: np.ndarray,
    target_asd_by_frequency: dict[float, np.ndarray],
) -> None:
    columns = {
        target_hz: f"asd_{target_hz:g}_hz_nv_per_sqrt_hz"
        for target_hz in TARGET_FREQUENCIES_HZ
    }
    partial_path = path.with_name(path.stem + ".partial" + path.suffix)
    with partial_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["run_number", *columns.values()])
        for index, run_number in enumerate(run_numbers):
            writer.writerow(
                [
                    int(run_number),
                    *[
                        format(target_asd_by_frequency[target_hz][index], ".17g")
                        for target_hz in TARGET_FREQUENCIES_HZ
                    ],
                ]
            )
    partial_path.replace(path)


def create_target_distribution_figure(
    plt: object,
    task_id: str,
    target_asd_by_frequency: dict[float, np.ndarray],
    target_results: dict[str, dict[str, float | int]],
    target_distribution_results: dict[str, dict[str, float | int | None]],
) -> object:
    figure, axes = plt.subplots(
        len(TARGET_FREQUENCIES_HZ),
        1,
        figsize=(10.0, 7.5),
        sharex=True,
    )
    axes = np.atleast_1d(axes)
    colors = {1.0: "tab:purple", 1_000.0: "tab:green"}
    all_values = np.concatenate(
        [target_asd_by_frequency[target_hz] for target_hz in TARGET_FREQUENCIES_HZ]
    )
    x_min = float(np.min(all_values))
    x_max = float(np.max(all_values))
    x_padding = max(0.08 * (x_max - x_min), 0.05)

    for axis, target_hz in zip(axes, TARGET_FREQUENCIES_HZ, strict=True):
        key = f"{target_hz:g}_hz"
        values = target_asd_by_frequency[target_hz]
        statistics = target_distribution_results[key]
        color = colors[target_hz]
        histogram_edges = np.histogram_bin_edges(values, bins="auto")
        axis.hist(
            values,
            bins=histogram_edges,
            color=color,
            alpha=0.68,
            label="Per-record local power estimate",
        )
        lower = float(statistics["percentile_2p5_asd_nv_per_sqrt_hz"])
        upper = float(statistics["percentile_97p5_asd_nv_per_sqrt_hz"])
        median = float(statistics["median_asd_nv_per_sqrt_hz"])
        pooled = float(
            target_results[key]["smoothed_estimate_asd_nv_per_sqrt_hz"]
        )
        axis.axvspan(
            lower,
            upper,
            color="tab:gray",
            alpha=0.14,
            label="2.5th-97.5th percentile",
        )
        axis.axvline(
            median,
            color=color,
            linewidth=2.0,
            label=f"Median: {median:.4g} nV/√Hz",
        )
        axis.axvline(
            pooled,
            color="black",
            linestyle="--",
            linewidth=1.5,
            label=f"ASD from mean PSD: {pooled:.4g} nV/√Hz",
        )
        band_lower = float(target_results[key]["smoothing_band_lower_hz"])
        band_upper = float(target_results[key]["smoothing_band_upper_hz"])
        band_bins = int(target_results[key]["smoothing_bin_count"])
        axis.set_title(
            f"{target_hz:g} Hz estimate: {band_lower:.6g}-{band_upper:.6g} Hz, "
            f"{band_bins} FFT bins"
        )
        axis.set_ylabel("Record count")
        axis.grid(axis="y", alpha=0.28)
        axis.legend(loc="best", fontsize=8)

    axes[-1].set_xlabel("Per-record equivalent input noise ASD (nV/√Hz)")
    axes[-1].set_xlim(x_min - x_padding, x_max + x_padding)
    figure.suptitle(
        f"{task_id}: 1 Hz and 1 kHz per-record noise distributions\n"
        f"{all_values.size // len(TARGET_FREQUENCIES_HZ)} records"
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    return figure


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    task_spectra_dir = args.spectra_dir.expanduser().resolve() / args.task_id
    task_output_dir = args.output_dir.expanduser().resolve() / args.task_id
    files = numbered_spectrum_files(task_spectra_dir, args.task_id)
    if not files:
        raise FileNotFoundError(
            f"No numbered spectrum files found for task {args.task_id!r} in "
            f"{task_spectra_dir}."
        )
    task_output_dir.mkdir(parents=True, exist_ok=True)

    (
        frequency_hz,
        mean_input_psd_v2_per_hz,
        closed_loop_bandwidth_hz,
        nperseg,
        total_welch_segments,
        frequency_resolution_hz,
        run_numbers,
        target_asd_by_frequency,
    ) = load_average_psd(files, args.task_id)
    mean_asd_nv_per_rt_hz = np.sqrt(mean_input_psd_v2_per_hz) * 1.0e9

    plot_upper_hz = min(PLOT_FMAX_HZ, float(frequency_hz[-1]))
    plot_mask = (
        (frequency_hz >= PLOT_FMIN_HZ)
        & (frequency_hz <= plot_upper_hz)
        & (mean_asd_nv_per_rt_hz > 0.0)
    )
    if np.count_nonzero(plot_mask) < 2:
        raise ValueError("Not enough positive PSD bins in the requested plot range.")
    smooth_frequency_hz, smooth_asd_nv_per_rt_hz = smoothed_curve(
        frequency_hz,
        mean_input_psd_v2_per_hz,
        PLOT_FMIN_HZ,
        plot_upper_hz,
    )

    target_results: dict[str, dict[str, float | int]] = {}
    for target_hz in TARGET_FREQUENCIES_HZ:
        nearest_frequency_hz, nearest_asd = nearest_bin_estimate(
            frequency_hz, mean_input_psd_v2_per_hz, target_hz
        )
        estimated_asd, band_lower_hz, band_upper_hz, band_bins = (
            local_power_estimate(
                frequency_hz, mean_input_psd_v2_per_hz, target_hz
            )
        )
        target_results[f"{target_hz:g}_hz"] = {
            "target_frequency_hz": target_hz,
            "nearest_bin_frequency_hz": nearest_frequency_hz,
            "nearest_bin_asd_nv_per_sqrt_hz": nearest_asd,
            "smoothed_estimate_asd_nv_per_sqrt_hz": estimated_asd,
            "smoothing_band_lower_hz": band_lower_hz,
            "smoothing_band_upper_hz": band_upper_hz,
            "smoothing_bin_count": band_bins,
        }

    fig, axis = plt.subplots(figsize=(11.5, 7.0))
    axis.loglog(
        frequency_hz[plot_mask],
        mean_asd_nv_per_rt_hz[plot_mask],
        color="tab:blue",
        linewidth=0.75,
        alpha=0.72,
        label=f"ASD from mean PSD ({len(files)} records)",
    )
    axis.loglog(
        smooth_frequency_hz,
        smooth_asd_nv_per_rt_hz,
        color="tab:red",
        linestyle="--",
        linewidth=2.0,
        label="Smoothed power estimate (1/6 octave, min. 5 bins)",
    )

    if PLOT_FMIN_HZ < closed_loop_bandwidth_hz < plot_upper_hz:
        axis.axvspan(
            closed_loop_bandwidth_hz,
            plot_upper_hz,
            color="tab:gray",
            alpha=0.14,
            label="Above estimated closed-loop bandwidth",
        )
        axis.axvline(
            closed_loop_bandwidth_hz,
            color="tab:gray",
            linestyle="--",
            linewidth=1.2,
        )

    marker_colors = {1.0: "tab:purple", 1_000.0: "tab:green"}
    for target_hz in TARGET_FREQUENCIES_HZ:
        result = target_results[f"{target_hz:g}_hz"]
        estimate = float(result["smoothed_estimate_asd_nv_per_sqrt_hz"])
        axis.scatter(
            [target_hz],
            [estimate],
            color=marker_colors[target_hz],
            s=52,
            zorder=5,
            label=f"{target_hz:g} Hz estimate: {estimate:.4g} nV/√Hz",
        )

    axis.set_xlim(PLOT_FMIN_HZ, plot_upper_hz)
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("Equivalent input noise ASD (nV/√Hz)")
    axis.set_title(f"{args.task_id}: averaged equivalent input noise")
    axis.grid(True, which="both", alpha=0.28)
    axis.legend(loc="best", fontsize=9)
    fig.tight_layout()

    plot_path = task_output_dir / f"{args.task_id}_average_input_noise_asd.png"
    partial_plot_path = task_output_dir / (
        f"{args.task_id}_average_input_noise_asd.partial.png"
    )
    fig.savefig(partial_plot_path, dpi=220)
    partial_plot_path.replace(plot_path)

    target_distribution_results: dict[
        str, dict[str, float | int | None]
    ] = {}
    for target_hz in TARGET_FREQUENCIES_HZ:
        key = f"{target_hz:g}_hz"
        distribution = distribution_statistics(
            target_asd_by_frequency[target_hz]
        )
        distribution.update(
            {
                "target_frequency_hz": target_hz,
                "smoothing_band_lower_hz": target_results[key][
                    "smoothing_band_lower_hz"
                ],
                "smoothing_band_upper_hz": target_results[key][
                    "smoothing_band_upper_hz"
                ],
                "smoothing_bin_count": target_results[key][
                    "smoothing_bin_count"
                ],
                "asd_from_mean_psd_nv_per_sqrt_hz": target_results[key][
                    "smoothed_estimate_asd_nv_per_sqrt_hz"
                ],
            }
        )
        target_distribution_results[key] = distribution

    distribution_csv_path = (
        task_output_dir / f"{args.task_id}_target_asd_distribution.csv"
    )
    write_target_distribution_csv(
        distribution_csv_path,
        run_numbers,
        target_asd_by_frequency,
    )

    distribution_figure = create_target_distribution_figure(
        plt,
        args.task_id,
        target_asd_by_frequency,
        target_results,
        target_distribution_results,
    )
    distribution_plot_path = (
        task_output_dir / f"{args.task_id}_target_asd_distributions.png"
    )
    partial_distribution_plot_path = distribution_plot_path.with_name(
        distribution_plot_path.stem + ".partial" + distribution_plot_path.suffix
    )
    distribution_figure.savefig(partial_distribution_plot_path, dpi=220)
    partial_distribution_plot_path.replace(distribution_plot_path)

    approximate_asd_one_sigma_fraction = 1.0 / (
        2.0 * math.sqrt(total_welch_segments)
    )
    summary = {
        "format_version": 2,
        "task_id": args.task_id,
        "spectrum_file_count": len(files),
        "first_run_number": files[0][0],
        "last_run_number": files[-1][0],
        "welch_nperseg": nperseg,
        "total_welch_segments": total_welch_segments,
        "frequency_resolution_hz": frequency_resolution_hz,
        "estimated_closed_loop_bandwidth_hz": closed_loop_bandwidth_hz,
        "smoothing_method": (
            "arithmetic mean of PSD in a 1/6-octave full-width band, "
            "with at least 5 FFT bins"
        ),
        "approximate_single_bin_asd_one_sigma_fraction": (
            approximate_asd_one_sigma_fraction
        ),
        "targets": target_results,
        "target_distribution_method": (
            "for each record, arithmetic mean of local PSD followed by square "
            "root and conversion to nV/sqrt(Hz)"
        ),
        "target_distributions": target_distribution_results,
        "plot": str(plot_path),
        "distribution_plot": str(distribution_plot_path),
        "distribution_csv": str(distribution_csv_path),
    }
    summary_path = task_output_dir / f"{args.task_id}_noise_summary.json"
    partial_summary_path = task_output_dir / (
        f"{args.task_id}_noise_summary.partial.json"
    )
    partial_summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    partial_summary_path.replace(summary_path)

    print(f"Task: {args.task_id}")
    print(
        f"Averaged {len(files)} spectrum file(s), "
        f"{total_welch_segments} total Welch segments, "
        f"df={frequency_resolution_hz:.12g} Hz."
    )
    print(
        "Approximate single-bin ASD random uncertainty: "
        f"{approximate_asd_one_sigma_fraction * 100.0:.3f}% (1 sigma, idealized)."
    )
    for target_hz in TARGET_FREQUENCIES_HZ:
        key = f"{target_hz:g}_hz"
        result = target_results[key]
        print(
            f"{target_hz:g} Hz: nearest bin "
            f"{float(result['nearest_bin_frequency_hz']):.9f} Hz = "
            f"{float(result['nearest_bin_asd_nv_per_sqrt_hz']):.9g} "
            "nV/sqrt(Hz); smoothed estimate = "
            f"{float(result['smoothed_estimate_asd_nv_per_sqrt_hz']):.9g} "
            "nV/sqrt(Hz) over "
            f"{float(result['smoothing_band_lower_hz']):.6g}-"
            f"{float(result['smoothing_band_upper_hz']):.6g} Hz "
            f"({int(result['smoothing_bin_count'])} bins)."
        )
        distribution = target_distribution_results[key]
        sample_std = distribution["sample_std_asd_nv_per_sqrt_hz"]
        sample_std_text = "n/a" if sample_std is None else f"{float(sample_std):.9g}"
        print(
            f"  Per-record distribution: n={int(distribution['count'])}, "
            f"mean={float(distribution['mean_asd_nv_per_sqrt_hz']):.9g}, "
            f"median={float(distribution['median_asd_nv_per_sqrt_hz']):.9g}, "
            f"sample std={sample_std_text}, 2.5th-97.5th percentile="
            f"{float(distribution['percentile_2p5_asd_nv_per_sqrt_hz']):.9g}-"
            f"{float(distribution['percentile_97p5_asd_nv_per_sqrt_hz']):.9g} "
            "nV/sqrt(Hz)."
        )
    if args.show:
        plt.show()
    else:
        plt.close(fig)
        plt.close(distribution_figure)
    print(f"Plot: {plot_path}")
    print(f"Distribution plot: {distribution_plot_path}")
    print(f"Distribution CSV: {distribution_csv_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
