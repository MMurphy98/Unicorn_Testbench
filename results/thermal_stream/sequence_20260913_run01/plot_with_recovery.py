"""Render recorded temperatures and the separate, later STOP recovery evidence.

Does not modify the original CSV, events, summary or automatically generated plot.
"""
from pathlib import Path
from datetime import datetime
import csv
import json
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from plot_thermal_stream_temperature import load_pyplot


def main():
    plt = load_pyplot(ROOT / "tmp" / "thermal_plot_dependencies")
    summary = json.loads((FOLDER / "summary.json").read_text(encoding="utf-8"))
    recovery = json.loads((FOLDER / "stop_recovery_20260913T053048_663527Z.json").read_text(encoding="utf-8"))
    assert recovery["stop_confirmed"] and recovery["snapshot"]["running"] is False
    events = [json.loads(line) for line in (FOLDER / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    with (FOLDER / "temperature.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    start = datetime.fromisoformat(summary["started_at_utc"])
    stop = (datetime.fromisoformat(recovery["stop_confirmed_at_utc"]) - start).total_seconds() / 60
    failure = next(event["elapsed_s"] for event in events if event["event"] == "error") / 60
    arrival = summary["stages"][0]["first_arrival_at_elapsed_s"] / 60
    x = [float(row["elapsed_s"]) / 60 for row in rows]
    air = [float(row["air_temperature_c"]) for row in rows]
    product = [float(row["product_temperature_c"]) for row in rows]
    holding = [row for row in rows if row["phase"] == "holding"]
    fig, (ax, detail) = plt.subplots(2, 1, figsize=(12, 7.6), sharex=True,
                                    gridspec_kw={"height_ratios": [2.5, 1]})
    fig.subplots_adjust(left=.085, right=.97, top=.84, bottom=.13, hspace=.20)
    fig.suptitle("Thermal stream: -40 C stage interrupted; STOP later confirmed", x=.085,
                 ha="left", y=.975, fontsize=16)
    fig.text(.085, .932, "2026-09-13 | Product control | 209 recorded samples | 27 C and 125 C stages not started",
             fontsize=10, color="#475569")
    ax.plot(x, air, color="#2563eb", label="Air temperature", linewidth=1.6)
    ax.plot(x, product, color="#ea580c", label="Product temperature", linewidth=1.8)
    ax.plot([x[0], x[-1]], [-40, -40], color="#475569", linestyle="--", label="Target: -40 C")
    ax.scatter([stop], [recovery["snapshot"]["air_temperature_c"]], color="#2563eb", marker="s", s=30, zorder=5)
    ax.scatter([stop], [recovery["snapshot"]["product_temperature_c"]], color="#ea580c", marker="s", s=30, zorder=5,
               label="Separate recovery snapshot")
    detail.axhspan(-1, 1, color="#dbeafe", label="Target +/-1 C")
    detail.plot([float(row["elapsed_s"])/60 for row in holding],
                [float(row["error_c"]) for row in holding], color="#ea580c", linewidth=1.4)
    detail.axhline(0, color="#475569", linestyle="--", linewidth=1)
    for axes in (ax, detail):
        axes.axvspan(arrival, x[-1], color="#16a34a", alpha=.07)
        axes.axvspan(x[-1], stop, color="#94a3b8", alpha=.15)
        axes.axvline(arrival, color="#7c3aed", linestyle=":", linewidth=1.2)
        axes.axvline(failure, color="#d97706", linestyle="--", linewidth=1.2)
        axes.axvline(stop, color="#dc2626", linestyle=":", linewidth=1.4)
        axes.grid(alpha=.18)
        axes.spines[["top", "right"]].set_visible(False)
        axes.set_xlim(-.03, stop + .18)
    for position, text, color, align in (
        (arrival, "First arrival\n57.8 s", "#7c3aed", "center"),
        (failure, "Connection reset\n207.8 s", "#b45309", "right"),
        (stop, "STOP confirmed\n261.5 s", "#b91c1c", "center"),
    ):
        ax.text(position, 1.02, text, transform=ax.get_xaxis_transform(), color=color,
                ha=align, va="bottom", fontsize=9)
    ax.text((x[-1]+stop)/2, -.02, "No continuous telemetry", transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=8, color="#64748b")
    ax.set_ylabel("Temperature (C)")
    detail.set_ylabel("Product error (C)")
    detail.set_xlabel("Elapsed time since sequence recording began (min)")
    detail.set_ylim(-1.4, 5.4)
    ax.legend(loc="upper right", fontsize=9, framealpha=.93)
    detail.legend(loc="upper left", fontsize=8)
    fig.text(.085, .035, "Fixed timer reached 149.1 / 300 s before interruption; 79 of 150 hold samples were outside +/-1 C.\n"
             "Recovery points are separate measurements; the telemetry gap is not interpolated.", fontsize=9, color="#475569")
    output = FOLDER / "temperature_curve_with_recovery.png"
    fig.savefig(output, dpi=170)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
