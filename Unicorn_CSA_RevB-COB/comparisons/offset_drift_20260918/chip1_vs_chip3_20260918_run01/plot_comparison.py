"""Plot the saved Chip 1 / Chip 3 results; no instrument access."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MultipleLocator
import numpy as np

ROOT = Path(__file__).resolve().parent
STEM = "chip1_vs_chip3_offset_vs_temperature"


def main():
    for name in ("msyh.ttc", "msyhbd.ttc"):
        font_manager.fontManager.addfont(str(Path("C:/Windows/Fonts") / name))
    plt.rcParams.update({
        "font.family": "Microsoft YaHei", "font.size": 11,
        "axes.unicode_minus": False, "axes.spines.top": False,
        "axes.spines.right": False, "axes.edgecolor": "#AAB4C0",
        "axes.labelcolor": "#243449", "text.color": "#172B43",
        "xtick.color": "#40516A", "ytick.color": "#40516A",
        "svg.fonttype": "path", "savefig.facecolor": "white",
    })
    fig = plt.figure(figsize=(10.8, 7.4), facecolor="white")
    ax = fig.add_axes([0.105, 0.25, 0.855, 0.595])
    fig.text(0.105, 0.945, "Chip 1 / Chip 3 温度–Offset 对比", fontsize=20, weight="bold")
    fig.text(0.105, 0.895, "输入等效 Offset = DMM 电压 / 1001  ·  固定 6 SCFM  ·  每点 1000 个读数", fontsize=11.5, color="#53657A")
    records = []
    for chip, color, marker in ((1, "#2563EB", "o"), (3, "#DB6B22", "s")):
        source = ROOT.parents[2] / "tasks" / f"Offset_Chip_{chip}_Gain1001_20260918" / "provenance/legacy_run"
        summary_path = source / "offset_drift_summary.json"
        verification_path = source / "saved_data_verification.json"
        manifest = json.loads((source / "artifact_sha256.json").read_text(encoding="utf-8"))
        for path in (summary_path, verification_path):
            assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[path.name]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        assert summary["sequence_completed"] and verification["all_passed"]
        assert summary["task_id"] == f"Offset_Chip_{chip}_Gain1001_20260918"
        points = sorted(summary["points"], key=lambda p: p["target_c"])
        assert [p["target_c"] for p in points] == [-40, 27, 125]
        assert all(p["reading_count"] == 1000 and p["gain"] == 1001 for p in points)
        x = np.array([p["target_c"] for p in points])
        mean = np.array([p["input_offset_mean_v"] for p in points]) * 1e6
        std = np.array([p["input_offset_sample_std_v"] for p in points]) * 1e6
        assert np.all(np.isfinite(mean)) and np.all(np.isfinite(std)) and np.all(std >= 0)
        ax.errorbar(x, mean, yerr=std, label=f"Chip {chip}", color=color,
                    marker=marker, markersize=7.5, markerfacecolor="white",
                    markeredgewidth=2, linewidth=2.4, elinewidth=1.6,
                    capsize=5.5, capthick=1.6, zorder=3)
        for temperature, value, spread in zip(x, mean, std):
            direction = 1 if chip == 1 else -1
            ax.annotate(f"{value:+.3f}", (temperature, value + direction * spread),
                        xytext=(0, direction * 9), textcoords="offset points",
                        ha="center", va="bottom" if direction == 1 else "top",
                        fontsize=11, color=color, weight="bold")
        records.append({
            "chip_id": chip,
            "source_summary": summary_path.relative_to(ROOT.parent).as_posix(),
            "source_sha256": manifest[summary_path.name],
            "nominal_slope_nv_per_c": summary["nominal_temperature_linear_slope_v_per_c"] * 1e9,
            "points": [{
                "target_c": p["target_c"], "reading_count": p["reading_count"],
                "input_mean_uv": float(m), "input_sample_std_uv": float(s),
                "actual_temperature_min_c": p["product_temperature_min_c"],
                "actual_temperature_max_c": p["product_temperature_max_c"],
            } for p, m, s in zip(points, mean, std)],
        })
    ax.axhline(0, color="#A0AEC0", linewidth=1, linestyle=(0, (4, 4)), zorder=1)
    ax.set_xlim(-55, 140)
    ax.set_ylim(-2.95, 0.92)
    ax.set_xticks([-40, 27, 125])
    ax.yaxis.set_major_locator(MultipleLocator(0.5))
    ax.set_xlabel("名义目标温度（℃）", labelpad=12, fontsize=12)
    ax.set_ylabel("输入等效 Offset（μV）", labelpad=12, fontsize=12)
    ax.grid(axis="both", color="#E6EBF1", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=4, pad=7)
    ax.legend(loc="upper right", frameon=False, fontsize=12, ncol=2,
              columnspacing=1.8, handlelength=2.2)
    fig.text(0.105, 0.11, "误差棒：±1 样本标准差，表示读数波动；不是均值置信区间。", fontsize=10.5, color="#53657A")
    fig.text(0.105, 0.066, "两轮均存在温度振荡及段内漂移；连线仅用于比较三个测量点。", fontsize=10.5, color="#53657A")
    fig.text(0.96, 0.066, "2026-09-18", fontsize=10.5, color="#53657A", ha="right")
    for ext in ("png", "svg"):
        fig.savefig(ROOT / f"{STEM}.{ext}", dpi=220)
    plt.close(fig)
    (ROOT / "comparison_data.json").write_text(json.dumps({
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "x_axis": "nominal target temperature in degrees Celsius",
        "y_axis": "input-referred mean offset in microvolts",
        "error_bars": "plus/minus one sample standard deviation, not standard error or confidence interval",
        "gain": 1001, "flow_setting_scfm": 6, "series": records,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "README.md").write_text(
        "# Chip 1 / Chip 3 offset对比\n\n"
        "使用2026-09-18两轮已核验的三温度结果，Gain=1001、6 SCFM、每点1000读数。"
        "均值及样本标准差直接读取输入等效统计值，不再除以增益。\n\n"
        "横轴为名义目标温度；误差棒为±1样本标准差，并非均值置信区间。"
        "两轮都存在温度振荡和段内漂移，连线只用于比较三个测量点。\n\n"
        f"![Chip 1与Chip 3对比]({STEM}.png)\n\n"
        f"[矢量SVG]({STEM}.svg) · [绘图数据及来源SHA-256](comparison_data.json) · [复现脚本](plot_comparison.py)\n\n"
        "[Chip 1原始报告](../../../tasks/Offset_Chip_1_Gain1001_20260918/README.md) · "
        "[Chip 3原始报告](../../../tasks/Offset_Chip_3_Gain1001_20260918/README.md)\n",
        encoding="utf-8")
    print(json.dumps({"png": str(ROOT / f"{STEM}.png"),
                      "svg": str(ROOT / f"{STEM}.svg"), "series": records}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
