#!/usr/bin/env python3
"""Plot a saved or actively growing thermal-stream CSV (requires matplotlib)."""

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys


def load_pyplot(dependency_dir=None):
    if dependency_dir:
        location = str(Path(dependency_dir).resolve())
        if location not in sys.path:
            sys.path.insert(0, location)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_run(run_dir, dependency_dir=None):
    """Render either a legacy single target CSV or a multi-stage sequence."""
    plt = load_pyplot(dependency_dir)
    folder = Path(run_dir).resolve()
    with (folder / "temperature.csv").open(encoding="utf-8", newline="") as source:
        # A live reader can encounter an unfinished final line. Keep only
        # complete records; this does not alter the acquisition CSV.
        rows = [row for row in csv.DictReader(source)
                if all(row.get(key) not in (None, "") for key in (
                    "timestamp_utc", "elapsed_s", "air_temperature_c",
                    "product_temperature_c", "target_c", "product_control", "flow_raw"))]
    if not rows:
        raise ValueError("No complete temperature samples")
    minutes = [float(r["elapsed_s"]) / 60 for r in rows]
    air = [float(r["air_temperature_c"]) for r in rows]
    product = [float(r["product_temperature_c"]) for r in rows]
    targets = [float(r["target_c"]) for r in rows]
    sequence = "stage_index" in rows[0]
    control = "product" if rows[-1]["product_control"] == "True" else "air"
    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    fig.subplots_adjust(left=0.09, right=0.985, top=0.84, bottom=0.19)
    ax.plot(minutes, air, color="#2563eb", linewidth=1.8, label="Air temperature")
    ax.plot(minutes, product, color="#ea580c", linewidth=1.8, label="Product temperature")
    if sequence:
        ax.step(minutes, targets, where="post", color="#475569", linestyle="--",
                linewidth=1.2, label="Stage target")
    else:
        ax.axhline(targets[-1], color="#475569", linestyle="--", linewidth=1.2,
                   label=f"Target {targets[-1]:g} °C")
    stopped = [r for r in rows if r["phase"] == "stopped"]
    events = []
    event_path = folder / "events.jsonl"
    if event_path.exists():
        for line in event_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # An actively growing event file may have a partial last line.
            events.append(event)

    def event_minute(event):
        if "elapsed_s" in event:
            return float(event["elapsed_s"]) / 60
        return (float(rows[0]["elapsed_s"]) + (
            datetime.fromisoformat(event["at_utc"])
            - datetime.fromisoformat(rows[0]["timestamp_utc"])).total_seconds()) / 60

    starts = [e for e in events if e.get("event") == "started"]
    for index, event in enumerate(starts):
        ax.axvline(event_minute(event), color="#16a34a", linewidth=1,
                   linestyle=":", label="START confirmed" if index == 0 else None)
        if sequence:
            next_start = event_minute(starts[index + 1]) if index + 1 < len(starts) else minutes[-1]
            middle = (event_minute(event) + next_start) / 2
            ax.text(middle, 1.025, f"{event['stage_index']}: {event['target_c']:g} °C",
                    transform=ax.get_xaxis_transform(), ha="center", fontsize=10)
    arrivals = [e for e in events if e.get("event") == "first_arrival"]
    for index, event in enumerate(arrivals):
        start = event_minute(event)
        end_event = next((e for e in events if e.get("event") in ("hold_completed", "stage_completed")
                          and e.get("stage_index") == event["stage_index"]), None)
        end = event_minute(end_event) if end_event else minutes[-1]
        ax.axvline(start, color="#7c3aed", linewidth=1, linestyle=":",
                   label="First arrival" if index == 0 else None)
        ax.axvspan(start, end, color="#16a34a", alpha=0.08,
                   label="Fixed hold after first arrival" if index == 0 else None)
    dmm_starts = [e for e in events if e.get("event") == "dmm_started"]
    for index, event in enumerate(dmm_starts):
        end_event = next((e for e in events if e.get("event") == "dmm_completed"
                          and e.get("stage_index") == event["stage_index"]), None)
        end = event_minute(end_event) if end_event else minutes[-1]
        ax.axvspan(event_minute(event), end, color="#2563eb", alpha=.08,
                   label="DMM worker active" if index == 0 else None)
    if stopped:
        ax.axvline(float(stopped[-1]["elapsed_s"]) / 60, color="#64748b",
                   linewidth=1, linestyle=":", label="STOP confirmed")
    simulated = False
    summary_path = folder / "summary.json"
    if summary_path.exists():
        try:
            simulated = json.loads(summary_path.read_text(encoding="utf-8")).get(
                "execution_environment") == "offline_simulation"
        except json.JSONDecodeError:
            pass
    prefix = "OFFLINE SIMULATION" if simulated else "Thermal stream"
    ax.set_title(f"{prefix} | {control} control | {len(rows)} samples", loc="left", pad=40)
    ax.set_xlabel("Time since recording began (min)")
    ax.set_ylabel("Temperature (°C)")
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="best", frameon=False, fontsize=9)
    ax.margins(x=0.025, y=0.12)
    initial_state = "running" if rows[0]["running"] == "True" else "stopped"
    detail = ("Shading: fixed time after first arrival; later excursions do not reset the timer."
              if sequence else f"START confirmed: {starts[0]['at_utc']}" if starts else
              "No START confirmation event in this recording.")
    fig.text(0.09, 0.025, f"First sample: {rows[0]['timestamp_utc']} | Initially {initial_state}\n"
             + detail,
             ha="left", fontsize=8, color="#64748b")
    output = folder / "temperature_curve.png"
    fig.savefig(output, dpi=170)
    plt.close(fig)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dependency-dir", type=Path,
                        help="Optional directory populated by pip install --target")
    args = parser.parse_args()
    print(plot_run(args.run_dir, args.dependency_dir))


if __name__ == "__main__":
    main()
