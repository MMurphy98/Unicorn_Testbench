"""Replay the seven September 17-18 noise groups and three historical baselines.

Reads local TDMS/NPZ and existing summaries; never connects to an instrument.
Writes only the comparison and verification artifacts next to this script.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

import matplotlib
import numpy as np
from nptdms import TdmsFile

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = Path(__file__).resolve().parent
PROJECT = OUTPUT.parent.parent
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT))
import analyze_dut_revb_pmu_noise as analysis
import plot_dut_revb_pmu_noise as plotting

# max = 4'b1111, confirmed by the operator on 2026-09-18.
# Separate names are retained because Chip 1's 4b1111 group is a repeat.
CONDITIONS = [
    ("H1", 1, "default", 6, False),
    ("H2", 2, "default", 6, False),
    ("H3", 3, "default", 6, False),
    ("N1", 1, "max", 6, True),
    ("N2", 2, "max", 6, True),
    ("N3", 3, "max", 6, True),
    ("N4", 3, "default", 12, True),
    ("N5", 3, "max", 12, True),
    ("N6", 2, "4b1001", 6, True),
    ("N7", 1, "4b1111", 6, True),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def close(actual, expected):
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=0.0)


def write_csv(name, rows):
    with (OUTPUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    groups, manifest, curves = [], [], {}
    for group_id, chip, gmx, supply, is_new in CONDITIONS:
        task = f"RevB_Chip_{chip}_wiShield_Gmx_{gmx}_OSC_default_Vsup_pm{supply}V"
        captures = analysis.numbered_tdms_files(PROJECT / "data" / task, task)
        spectra = plotting.numbered_spectrum_files(PROJECT / "spectra" / task, task)
        require([n for n, _ in captures] == list(range(1, 101)), task + " TDMS sequence")
        require([n for n, _ in spectra] == list(range(1, 101)), task + " NPZ sequence")
        require(not list((PROJECT / "data" / task).glob("*.partial.*")), task + " partial TDMS")
        require(not list((PROJECT / "spectra" / task).glob("*.partial.*")), task + " partial NPZ")
        result_dir = PROJECT / "results" / task
        summary_path = result_dir / f"{task}_noise_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        require(summary["task_id"] == task and summary["spectrum_file_count"] == 100, task + " summary identity")
        with (result_dir / f"{task}_target_asd_distribution.csv").open(encoding="utf-8-sig") as stream:
            distribution = list(csv.DictReader(stream))
        require([int(row["run_number"]) for row in distribution] == list(range(1, 101)), task + " CSV sequence")
        mean_psd = None
        target_values = {1.0: [], 1000.0: []}
        configs, starts, ends, means, rms, peaks, clippings = [], [], [], [], [], [], []
        raw_bytes, max_relative_error = 0, 0.0
        for (run, path), (_, spectrum_path) in zip(captures, spectra, strict=True):
            tdms = TdmsFile.read(path)
            root = tdms.properties
            require(root["task_id"] == task and root["run_number"] == run, str(path) + " identity")
            channel = tdms[root["tdms_group_name"]][root["tdms_channel_name"]]
            cp, x = channel.properties, channel[:]
            require(x.dtype == np.float64 and x.size == 1_100_000 and np.all(np.isfinite(x)), str(path) + " samples")
            config = {k: root[k] for k in ("closed_loop_gain_v_per_v", "op_amp_gbw_hz", "estimated_closed_loop_bandwidth_hz", "resource_name", "instrument_model", "instrument_serial_number", "ni_scope_driver_version")}
            config.update({k: cp[k] for k in ("actual_sample_rate_hz", "actual_record_length", "vertical_range_vpp", "input_impedance_ohm", "coupling", "physical_channel", "max_input_frequency_hz", "trigger_type")})
            if config not in configs:
                configs.append(config)
            close(root["closed_loop_gain_v_per_v"], 1001.0)
            close(1.0 / cp["wf_increment"], 50_000.0)
            mean = float(np.mean(x))
            ac_rms = float(np.sqrt(np.mean((x - mean) ** 2)))
            peak = float(np.max(np.abs(x)))
            clipping = peak >= 0.98 * cp["vertical_range_vpp"] / 2.0
            close(mean, cp["dc_mean_v"])
            close(ac_rms, cp["ac_rms_v"])
            close(np.ptp(x), cp["peak_to_peak_v"])
            require(clipping == bool(cp["near_clipping"]), str(path) + " clipping flag")
            f, psd, segments, resolution = analysis.calculate_input_psd(x, 1.0 / cp["wf_increment"], root["closed_loop_gain_v_per_v"], 262144)
            with np.load(spectrum_path, allow_pickle=False) as archive:
                require(archive["task_id"].item() == task and archive["run_number"].item() == run, str(spectrum_path) + " identity")
                require(Path(archive["source_tdms"].item()).name == path.name, str(spectrum_path) + " source")
                for key, expected in {"welch_nperseg": 262144, "welch_noverlap": 131072, "welch_window": "hann", "welch_detrend": "constant", "welch_average": "mean", "welch_segment_count": 7, "source_sample_count": x.size, "channel_name": "CH0"}.items():
                    require(archive[key].item() == expected, str(spectrum_path) + " " + key)
                close(archive["closed_loop_gain_v_per_v"], root["closed_loop_gain_v_per_v"])
                close(archive["estimated_closed_loop_bandwidth_hz"], root["estimated_closed_loop_bandwidth_hz"])
                close(archive["sample_rate_hz"], 1.0 / cp["wf_increment"])
                close(archive["frequency_resolution_hz"], resolution)
                saved_psd = archive["input_psd_v2_per_hz"]
                close(f, archive["frequency_hz"])
                close(psd, saved_psd)
                max_relative_error = max(max_relative_error, float(np.max(np.abs(psd - saved_psd) / np.maximum(np.abs(saved_psd), np.finfo(float).tiny))))
            mean_psd = psd.copy() if mean_psd is None else mean_psd + (psd - mean_psd) / run
            for target in target_values:
                value = plotting.local_power_estimate(f, psd, target)[0]
                target_values[target].append(value)
                close(value, float(distribution[run - 1][f"asd_{target:g}_hz_nv_per_sqrt_hz"]))
            start = root["acquisition_start_utc"]
            end = start + np.timedelta64(round(x.size * cp["wf_increment"] * 1e6), "us")
            starts.append(start)
            ends.append(end)
            means.append(mean)
            rms.append(ac_rms)
            peaks.append(peak)
            clippings.append(clipping)
            raw_bytes += path.stat().st_size
            manifest.append({"group_id": group_id, "task_id": task, "run_number": run, "path": path.relative_to(REPO).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path), "acquisition_start_utc": str(start), "near_clipping": clipping})
        require(len(configs) == 1, task + " mixed acquisition settings")
        close(summary["frequency_resolution_hz"], resolution)
        require(summary["welch_nperseg"] == 262144 and summary["total_welch_segments"] == 700, task + " Welch counts")
        require(summary["first_run_number"] == 1 and summary["last_run_number"] == 100, task + " summary runs")
        values = {}
        for target, runs in target_values.items():
            key = f"{target:g}_hz"
            estimate, low, high, bins = plotting.local_power_estimate(f, mean_psd, target)
            nearest_f, nearest_asd = plotting.nearest_bin_estimate(f, mean_psd, target)
            expected = summary["targets"][key]
            for k, v in {"smoothed_estimate_asd_nv_per_sqrt_hz": estimate, "smoothing_band_lower_hz": low, "smoothing_band_upper_hz": high, "smoothing_bin_count": bins, "nearest_bin_frequency_hz": nearest_f, "nearest_bin_asd_nv_per_sqrt_hz": nearest_asd}.items():
                close(v, expected[k])
            for k, v in plotting.distribution_statistics(np.asarray(runs)).items():
                close(v, summary["target_distributions"][key][k])
            close(np.sqrt(np.mean(np.square(runs))), estimate)
            close(summary["target_distributions"][key]["asd_from_mean_psd_nv_per_sqrt_hz"], estimate)
            values[key] = {"asd_nv_per_sqrt_hz": estimate, "cv_percent": summary["target_distributions"][key]["coefficient_of_variation_percent"], "minimum": min(runs), "maximum": max(runs), "first_50_rms": float(np.sqrt(np.mean(np.square(runs[:50])))), "last_50_rms": float(np.sqrt(np.mean(np.square(runs[50:]))))}
        group = {"group_id": group_id, "task_id": task, "new_measurement": is_new, "chip": chip, "gmx_label": gmx, "trim_code": "0110" if gmx == "default" else "1001" if gmx == "4b1001" else "1111", "supply_magnitude_v": supply, "records": len(captures), "welch_segments": len(captures) * segments, "raw_bytes": raw_bytes, "first_start_beijing": str(min(starts) + np.timedelta64(8, "h")), "last_end_beijing": str(max(ends) + np.timedelta64(8, "h")), "near_clipping_count": sum(clippings), "dc_mean_v_range": [min(means), max(means)], "ac_rms_v_range": [min(rms), max(rms)], "max_absolute_output_v": max(peaks), "maximum_psd_relative_error": max_relative_error, "acquisition": configs[0], "targets": values, "summary_sha256": sha256(summary_path)}
        groups.append(group)
        curves[group_id] = plotting.smoothed_curve(f, mean_psd, 1.0, 10_000.0)
        print(f"PASS {group_id} {task}: 100 raw replays; 1 Hz={values['1_hz']['asd_nv_per_sqrt_hz']:.6f}, 1 kHz={values['1000_hz']['asd_nv_per_sqrt_hz']:.6f}; clipping={sum(clippings)}", flush=True)

    summary_rows = [{"group_id": g["group_id"], "task_id": g["task_id"], "new_measurement": g["new_measurement"], "trim_code": g["trim_code"], "records": g["records"], "first_start_beijing": g["first_start_beijing"], "last_end_beijing": g["last_end_beijing"], "asd_1_hz_nv_per_sqrt_hz": g["targets"]["1_hz"]["asd_nv_per_sqrt_hz"], "asd_1000_hz_nv_per_sqrt_hz": g["targets"]["1000_hz"]["asd_nv_per_sqrt_hz"], "cv_1_hz_percent": g["targets"]["1_hz"]["cv_percent"], "cv_1000_hz_percent": g["targets"]["1000_hz"]["cv_percent"], "near_clipping_count": g["near_clipping_count"]} for g in groups]
    write_csv("condition_summary.csv", summary_rows)
    write_csv("raw_file_manifest.csv", manifest)
    scripts = [Path(__file__), PROJECT / "capture_dut_revb_pmu_noise.py", PROJECT / "analyze_dut_revb_pmu_noise.py", PROJECT / "plot_dut_revb_pmu_noise.py", PROJECT / "run_dut_revb_pmu_noise_pipeline.py"]
    report = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "verification": "All 1000 TDMS waveforms checked and Welch PSD recomputed against existing NPZ; all target CSVs and JSON statistics reproduced at rtol=1e-10, atol=0", "git_head_at_verification": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "environment": {"python": sys.version, "platform": platform.platform(), "packages": {p: version(p) for p in ["numpy", "scipy", "npTDMS", "matplotlib", "niscope"]}}, "trim_mapping_provenance": {"max_and_4b1111": "Operator confirmed on 2026-09-18: same code 1111; Chip 1's explicitly named 4b1111 group is a repeat", "default": "Project README: 0110", "4b1001": "Acquisition task ID; not independently read from DUT"}, "code_sha256": {p.relative_to(REPO).as_posix(): sha256(p) for p in scripts}, "groups": groups}
    (OUTPUT / "verification_summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    panels = [(("H1", "default / +/-6 V (historical)"), ("N1", "1111 / +/-6 V (first)"), ("N7", "1111 / +/-6 V (repeat)")), (("H2", "default / +/-6 V (historical)"), ("N2", "1111 / +/-6 V"), ("N6", "1001 / +/-6 V")), (("H3", "default / +/-6 V (historical)"), ("N3", "1111 / +/-6 V"), ("N4", "default / +/-12 V"), ("N5", "1111 / +/-12 V"))]
    for chip, (ax, panel) in enumerate(zip(axes, panels, strict=True), 1):
        for group_id, label in panel:
            frequency, asd = curves[group_id]
            ax.loglog(frequency, asd, label=label, linewidth=1.6)
        ax.set(title=f"Chip {chip}", xlabel="Frequency (Hz)", ylabel="Input-referred ASD (nV/sqrt(Hz))", xlim=(1, 10000), ylim=(3, 150))
        ax.grid(True, which="both", alpha=0.18)
        ax.legend(fontsize=8, loc="upper right")
    fig.suptitle("RevB noise retest | 100 records per condition | local PSD power smoothing\nHistorical baselines are not same-session controls; no chain-noise subtraction", fontsize=12)
    fig.savefig(OUTPUT / "noise_comparison.png", dpi=180)
    plt.close(fig)
    print(f"Verified {len(manifest)} files; artifacts: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
