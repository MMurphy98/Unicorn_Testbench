#!/usr/bin/env python3
"""Analyze a DUT RevB (with PMU) NI-SCOPE TDMS noise capture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import numpy as np
from nptdms import TdmsFile
from scipy.signal import welch


GROUP_NAME = "DUT RevB with PMU"
CHANNEL_NAME = "CH0"
WELCH_NPERSEG = 262_144
PLOT_FMIN_HZ = 1.0
PLOT_FMAX_HZ = 25_000.0
TARGET_FREQUENCIES_HZ = (1.0, 1_000.0)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate DUT RevB (with PMU) input-referred noise ASD from "
            "a float64 NI-SCOPE TDMS capture."
        )
    )
    parser.add_argument("tdms_file", type=Path, help="Input TDMS capture")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Plot output directory (default: results beside this script)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show the plot interactively after saving it",
    )
    return parser.parse_args(argv)


def _required_float(properties: dict, name: str, location: str) -> float:
    if name not in properties:
        raise ValueError(f"Required TDMS property {name!r} is missing from {location}.")
    try:
        value = float(properties[name])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"TDMS property {name!r} in {location} is not numeric: "
            f"{properties[name]!r}"
        ) from exc
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(
            f"TDMS property {name!r} in {location} must be positive and finite; "
            f"got {value!r}."
        )
    return value


def read_capture(tdms_path: Path) -> tuple[np.ndarray, float, float, float, dict]:
    if not tdms_path.is_file():
        raise FileNotFoundError(f"TDMS file not found: {tdms_path}")

    tdms = TdmsFile.read(tdms_path)
    root_properties = dict(tdms.properties)

    try:
        channel = tdms[GROUP_NAME][CHANNEL_NAME]
    except KeyError as exc:
        available = [
            f"{group.name}/{item.name}"
            for group in tdms.groups()
            for item in group.channels()
        ]
        raise ValueError(
            f"Expected TDMS channel {GROUP_NAME!r}/{CHANNEL_NAME!r}; "
            f"available channels: {available}"
        ) from exc

    samples = channel[:]
    if samples.dtype != np.dtype(np.float64):
        raise TypeError(
            f"{GROUP_NAME}/{CHANNEL_NAME} must be float64; got {samples.dtype}."
        )
    if samples.ndim != 1 or samples.size < WELCH_NPERSEG:
        raise ValueError(
            f"Capture must be one-dimensional with at least {WELCH_NPERSEG:,} "
            f"samples; got shape {samples.shape}."
        )
    if not np.all(np.isfinite(samples)):
        raise ValueError("Capture contains NaN or infinite voltage samples.")

    channel_properties = dict(channel.properties)
    sample_interval_s = _required_float(
        channel_properties, "wf_increment", f"{GROUP_NAME}/{CHANNEL_NAME}"
    )
    closed_loop_gain = _required_float(
        root_properties, "closed_loop_gain_v_per_v", "TDMS root"
    )
    closed_loop_bandwidth_hz = _required_float(
        root_properties, "estimated_closed_loop_bandwidth_hz", "TDMS root"
    )

    metadata = {
        "root": root_properties,
        "channel": channel_properties,
    }
    return (
        np.asarray(samples, dtype=np.float64),
        1.0 / sample_interval_s,
        closed_loop_gain,
        closed_loop_bandwidth_hz,
        metadata,
    )


def estimate_input_noise_asd(
    samples_v: np.ndarray,
    sample_rate_hz: float,
    closed_loop_gain: float,
) -> tuple[np.ndarray, np.ndarray, int, int, float]:
    nperseg = min(WELCH_NPERSEG, samples_v.size)
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
    input_asd_nv_per_rt_hz = (
        np.sqrt(np.maximum(output_psd_v2_per_hz, 0.0))
        / closed_loop_gain
        * 1.0e9
    )
    frequency_resolution_hz = sample_rate_hz / nperseg
    return (
        frequency_hz,
        input_asd_nv_per_rt_hz,
        nperseg,
        segment_count,
        frequency_resolution_hz,
    )


def nearest_frequency_value(
    frequency_hz: np.ndarray,
    values: np.ndarray,
    target_hz: float,
) -> tuple[float, float]:
    usable = np.flatnonzero(frequency_hz > 0.0)
    if usable.size == 0:
        raise ValueError("PSD result does not contain any positive-frequency bins.")
    index = usable[np.argmin(np.abs(frequency_hz[usable] - target_hz))]
    return float(frequency_hz[index]), float(values[index])


def create_plot(
    tdms_path: Path,
    output_dir: Path,
    frequency_hz: np.ndarray,
    input_asd_nv_per_rt_hz: np.ndarray,
    closed_loop_bandwidth_hz: float,
    target_values: dict[float, tuple[float, float]],
    show: bool,
) -> Path:
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{tdms_path.stem}_input_noise_asd.png"

    upper_frequency_hz = min(PLOT_FMAX_HZ, float(frequency_hz[-1]))
    plot_mask = (
        (frequency_hz >= PLOT_FMIN_HZ)
        & (frequency_hz <= upper_frequency_hz)
        & np.isfinite(input_asd_nv_per_rt_hz)
        & (input_asd_nv_per_rt_hz > 0.0)
    )
    if np.count_nonzero(plot_mask) < 2:
        raise ValueError("Not enough valid PSD bins in the requested plot range.")

    fig, axis = plt.subplots(figsize=(11.5, 7.0))
    axis.loglog(
        frequency_hz[plot_mask],
        input_asd_nv_per_rt_hz[plot_mask],
        color="tab:blue",
        linewidth=1.0,
        label="Welch input-referred noise ASD",
    )

    if PLOT_FMIN_HZ < closed_loop_bandwidth_hz < upper_frequency_hz:
        axis.axvspan(
            closed_loop_bandwidth_hz,
            upper_frequency_hz,
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

    marker_colors = {1.0: "tab:red", 1_000.0: "tab:green"}
    for target_hz, (actual_hz, value) in target_values.items():
        axis.scatter(
            [actual_hz],
            [value],
            s=48,
            color=marker_colors.get(target_hz, "tab:orange"),
            zorder=4,
            label=(
                f"{target_hz:g} Hz target: {actual_hz:.6g} Hz bin, "
                f"{value:.4g} nV/√Hz"
            ),
        )

    axis.set_xlim(PLOT_FMIN_HZ, upper_frequency_hz)
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("Equivalent input noise ASD (nV/√Hz)")
    axis.set_title("DUT RevB (with PMU) equivalent input noise")
    axis.grid(True, which="both", alpha=0.28)
    axis.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)

    if show:
        plt.show()
    else:
        plt.close(fig)
    return output_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tdms_path = args.tdms_file.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else Path(__file__).resolve().parent / "results"
    )

    (
        samples_v,
        sample_rate_hz,
        closed_loop_gain,
        closed_loop_bandwidth_hz,
        metadata,
    ) = read_capture(tdms_path)
    (
        frequency_hz,
        input_asd_nv_per_rt_hz,
        nperseg,
        segment_count,
        frequency_resolution_hz,
    ) = estimate_input_noise_asd(samples_v, sample_rate_hz, closed_loop_gain)

    target_values = {
        target_hz: nearest_frequency_value(
            frequency_hz, input_asd_nv_per_rt_hz, target_hz
        )
        for target_hz in TARGET_FREQUENCIES_HZ
    }

    plot_path = create_plot(
        tdms_path=tdms_path,
        output_dir=output_dir,
        frequency_hz=frequency_hz,
        input_asd_nv_per_rt_hz=input_asd_nv_per_rt_hz,
        closed_loop_bandwidth_hz=closed_loop_bandwidth_hz,
        target_values=target_values,
        show=args.show,
    )

    ac_samples = samples_v - np.mean(samples_v)
    print(f"TDMS: {tdms_path}")
    print(f"Samples: {samples_v.size:,} ({samples_v.dtype})")
    print(f"Sample rate: {sample_rate_hz:,.9f} Sa/s")
    print(f"Duration: {samples_v.size / sample_rate_hz:.9f} s")
    print(f"Mean: {np.mean(samples_v):.12g} V")
    print(f"AC RMS: {np.sqrt(np.mean(ac_samples**2)):.12g} V")
    print(f"Peak-to-peak: {np.ptp(samples_v):.12g} Vpp")
    print(f"Closed-loop gain: {closed_loop_gain:.12g} V/V")
    print(f"Estimated closed-loop bandwidth: {closed_loop_bandwidth_hz:,.6g} Hz")
    print(
        f"Welch: Hann, nperseg={nperseg:,}, 50% overlap, "
        f"segments={segment_count}, df={frequency_resolution_hz:.9f} Hz"
    )
    for target_hz, (actual_hz, value) in target_values.items():
        print(
            f"{target_hz:g} Hz target -> {actual_hz:.9f} Hz bin: "
            f"{value:.9g} nV/sqrt(Hz)"
        )

    vertical_range_vpp = metadata["channel"].get("vertical_range_vpp")
    vertical_offset_v = float(metadata["channel"].get("vertical_offset_v", 0.0))
    if vertical_range_vpp is not None:
        half_range = float(vertical_range_vpp) / 2.0
        peak_from_center = float(np.max(np.abs(samples_v - vertical_offset_v)))
        if peak_from_center >= 0.98 * half_range:
            print(
                "WARNING: Capture is within 2% of the configured vertical full scale; "
                "noise results may be affected by clipping.",
                file=sys.stderr,
            )

    print(f"Plot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
