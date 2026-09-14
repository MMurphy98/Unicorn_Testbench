#!/usr/bin/env python3
"""Summarize completed DMM jobs against nominal and recorded product temperature."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics

from offset_drift_handshake import atomic_json
from plot_thermal_stream_temperature import load_pyplot


def analyze_run(folder, dependency_dir=None):
    folder = Path(folder).resolve()
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    with (folder / "temperature.csv").open(encoding="utf-8", newline="") as stream:
        temperatures = list(csv.DictReader(stream))
    points = []
    for stage in summary["stages"]:
        job = stage.get("dmm", {})
        if stage["status"] != "completed" or job.get("status") != "completed":
            continue
        # Resolve locations from this result directory so archived runs can be relocated.
        job_folder = folder / "dmm" / f"stage_{stage['index']:02d}"
        data = json.loads((job_folder / "results/offset/offset_dcv_offset_summary.json").read_text(encoding="utf-8"))
        first, last = (datetime.fromisoformat(job[key]) for key in ("first_reading_at_utc", "last_reading_at_utc"))
        matched = [row for row in temperatures if row["stage_index"] == str(stage["index"])
                   and first <= datetime.fromisoformat(row["timestamp_utc"]) <= last]
        values = [float(row["product_temperature_c"]) for row in matched]
        points.append({
            "stage_index": stage["index"], "target_c": stage["target_c"],
            "reading_count": data["total_reading_count"],
            "gain": data["configuration"]["closed_loop_gain_v_per_v"],
            "output_mean_v": data["output_voltage_v"]["mean"],
            "input_offset_mean_v": data["equivalent_input_offset_v"]["mean"],
            "input_offset_sample_std_v": data["equivalent_input_offset_v"]["sample_std"],
            "product_temperature_mean_c": statistics.mean(values) if values else None,
            "product_temperature_min_c": min(values) if values else None,
            "product_temperature_max_c": max(values) if values else None,
            "temperature_sample_count": len(values),
            "temperature_out_of_band_samples": sum(row["in_band"] == "False" for row in matched),
            "first_reading_at_utc": job["first_reading_at_utc"],
            "last_reading_at_utc": job["last_reading_at_utc"],
        })
    report = {"sequence_completed": summary["sequence_completed"],
              "stop_confirmed": summary["stop_confirmed"], "points": points,
              "temperature_window": "Thermal samples between the first and last DMM query-midpoint timestamps; no gap interpolation.",
              "drift_note": "The three-point slope uses nominal setpoints. It is a descriptive linear fit, not a device specification or uncertainty budget.",
              "nominal_temperature_linear_slope_v_per_c": None}
    if len(points) == 3:
        xs, ys = [point["target_c"] for point in points], [point["input_offset_mean_v"] for point in points]
        xm, ym = statistics.mean(xs), statistics.mean(ys)
        report["nominal_temperature_linear_slope_v_per_c"] = (
            sum((x-xm)*(y-ym) for x, y in zip(xs, ys)) / sum((x-xm)**2 for x in xs))
    atomic_json(folder / "offset_drift_summary.json", report)
    if points:
        with (folder / "offset_vs_temperature.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(points[0]))
            writer.writeheader()
            writer.writerows(points)
        plt = load_pyplot(dependency_dir)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.errorbar([p["target_c"] for p in points], [p["input_offset_mean_v"]*1e6 for p in points],
                    yerr=[p["input_offset_sample_std_v"]*1e6 for p in points], fmt="o-", capsize=5,
                    color="#2563eb", label="Mean +/- sample standard deviation")
        ax.set_xticks([-40, 27, 125])
        ax.set_xlabel("Nominal product temperature target (C)")
        ax.set_ylabel("Input-referred offset (uV)")
        simulated = summary.get("execution_environment") == "offline_simulation"
        ax.set_title(("OFFLINE SIMULATION | " if simulated else "") + f"Offset vs temperature: {len(points)}/3 points")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(folder / "offset_vs_temperature.png", dpi=170)
        plt.close(fig)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dependency-dir", type=Path)
    args = parser.parse_args()
    analyze_run(args.run_dir, args.dependency_dir)
