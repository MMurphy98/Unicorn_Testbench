#!/usr/bin/env python3
"""Analyze independently acquired DMM7510 TDMS files at -40, 27 and 125 C.

Read-only instrument data analysis. No instrument drivers or connections are used.
Each supplied task directory must contain one selected record; no runs are silently
selected, discarded, filtered or detrended. Temperatures are nominal task labels.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from nptdms import TdmsFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Unicorn_CSA_RevB-COB"))
import analyze_dmm7510_offset as dmm

TEMPERATURES = (-40.0, 27.0, 125.0)
LOCAL_TZ = timezone(timedelta(hours=8))
COLORS = ("#2563eb", "#0f766e", "#d97706", "#9333ea")
METHOD_SOURCE = "https://www.ti.com/lit/ug/tiduf45a/tiduf45a.pdf"
THERMAL_EMF_SOURCE = "https://www.analog.com/en/resources/technical-articles/layout-for-precision-op-amps.html"


def parse_task_id(task_id):
    match = re.fullmatch(r"(?P<device>.+)_Chip_(?P<chip>\d+)_(?P<condition>.+)_"
                         r"(?P<temperature>-?\d+(?:\.\d+)?)C_(?P<date>\d{8})", task_id)
    if not match:
        raise ValueError(f"Expected a task ID containing _Chip_N_..._TC_YYYYMMDD: {task_id}")
    fields = match.groupdict()
    temperature = float(fields["temperature"])
    if temperature not in TEMPERATURES:
        raise ValueError(f"Unexpected temperature in {task_id}: {temperature}")
    datetime.strptime(fields["date"], "%Y%m%d")
    fields.update(chip=int(fields["chip"]), temperature_c=temperature,
                  device_id=f"{fields['device']}_Chip_{int(fields['chip'])}_{fields['condition']}")
    return fields


def drift_metrics(temperatures_c, offsets_nv):
    """Three-point observed box drift and signed slopes; offsets are already input-referred."""
    x, y = np.asarray(temperatures_c, dtype=float), np.asarray(offsets_nv, dtype=float)
    if x.ndim != 1 or y.shape != x.shape or x.size < 2 or not np.all(np.isfinite([x, y])):
        raise ValueError("Drift requires at least two finite temperature/offset pairs")
    order = np.argsort(x)
    x, y = x[order], y[order]
    if np.any(np.diff(x) <= 0):
        raise ValueError("Drift temperatures must be distinct")
    dx, dy = x - np.mean(x), y - np.mean(y)
    slope = float(np.dot(dx, dy) / np.dot(dx, dx))
    fitted = np.mean(y) + slope * dx
    residual = y - fitted
    segments = np.diff(y) / np.diff(x)
    span = float(x[-1] - x[0])
    variance = float(np.dot(dy, dy))
    return {
        "temperature_span_c": span,
        "offset_span_nv": float(np.ptp(y)),
        "box_drift_nv_per_c": float(np.ptp(y) / span),
        "linear_fit_slope_nv_per_c": slope,
        "linear_fit_offset_at_27_nv": float(np.mean(y) + slope * (27 - np.mean(x))),
        "linear_fit_r_squared": None if variance == 0 else float(1 - np.dot(residual, residual) / variance),
        "linear_fit_max_abs_residual_nv": float(np.max(np.abs(residual))),
        "endpoint_slope_nv_per_c": float((y[-1] - y[0]) / span),
        "max_abs_segment_slope_nv_per_c": float(np.max(np.abs(segments))),
        "segment_slopes": [{"from_c": float(a), "to_c": float(b), "slope_nv_per_c": float(s)}
                           for a, b, s in zip(x[:-1], x[1:], segments)],
    }


def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                                    default=str) + "\n", encoding="utf-8")


def csv_write(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class Measurement:
    record: dmm.DcvRecord
    identity: dict
    metadata: dict
    sha256: str
    point: dict

    @property
    def input_nv(self):
        return self.record.readings_v / self.record.gain * 1e9


def point_statistics(record, identity, metadata, tail_seconds):
    y = record.readings_v / record.gain * 1e9
    t = record.elapsed_s
    first = y[t <= t[0] + tail_seconds]
    last = y[t >= t[-1] - tail_seconds]
    centered_time = t - t.mean()
    time_slope = float(np.dot(centered_time, y - y.mean()) / np.dot(centered_time, centered_time))
    rho = None
    if y.size > 2 and np.std(y[:-1]) > 0 and np.std(y[1:]) > 0:
        rho = float(np.corrcoef(y[:-1], y[1:])[0, 1])
    return {
        "device_id": identity["device_id"], "chip": identity["chip"], "test_date": identity["date"],
        "task_id": metadata["task_id"], "nominal_temperature_c": identity["temperature_c"],
        "temperature_source": "task_id; no measured temperature time series supplied",
        "temperature_metadata_c": metadata.get("temperature_c"),
        "run_number": record.run_number, "reading_count": int(y.size), "gain_v_per_v": record.gain,
        "start_utc": record.acquisition_start_utc.isoformat(),
        "start_local": record.acquisition_start_utc.astimezone(LOCAL_TZ).isoformat(),
        "first_reading_utc": (record.acquisition_start_utc + timedelta(seconds=float(t[0]))).isoformat(),
        "last_reading_utc": (record.acquisition_start_utc + timedelta(seconds=float(t[-1]))).isoformat(),
        "acquisition_duration_s": float(metadata["acquisition_duration_s"]),
        "readings_time_span_s": float(t[-1] - t[0]),
        "output_mean_v": float(record.readings_v.mean()),
        "input_offset_mean_nv": float(y.mean()), "input_offset_median_nv": float(np.median(y)),
        "input_offset_sample_std_nv": float(y.std(ddof=1)),
        "input_offset_min_nv": float(y.min()), "input_offset_max_nv": float(y.max()),
        "input_offset_peak_to_peak_nv": float(np.ptp(y)),
        "diagnostic_window_s": tail_seconds,
        "first_window_count": int(first.size), "first_window_mean_nv": float(first.mean()),
        "last_window_count": int(last.size), "last_window_mean_nv": float(last.mean()),
        "last_minus_first_window_mean_nv": float(last.mean() - first.mean()),
        "time_linear_slope_nv_per_min": time_slope * 60,
        "lag_one_sample_correlation": rho,
    }


def load_measurements(data_dir, tail_seconds):
    files = sorted(Path(data_dir).rglob("*.tdms"))
    if not files:
        raise ValueError(f"No TDMS data found in {data_dir}")
    measurements, seen = [], set()
    reference = None
    for path in files:
        task_id = path.parent.name
        identity = parse_task_id(task_id)
        match = re.fullmatch(re.escape(task_id) + r"_dcv_(\d+)\.tdms", path.name)
        if not match:
            raise ValueError(f"Unexpected/incomplete TDMS filename: {path}")
        key = (identity["device_id"], identity["date"], identity["temperature_c"])
        if key in seen:
            raise ValueError(f"Multiple records for {key}; use a data directory with one selected record per point")
        seen.add(key)
        record = dmm.read_record(path, task_id, int(match[1]))
        if reference is None:
            reference = record.configuration
        dmm.require_matching_configuration(reference, record.configuration, path)
        tdms = TdmsFile.read(path)
        metadata = dict(tdms.properties)
        if "temperature_c" in metadata:
            tagged = float(metadata["temperature_c"])
            if not np.isfinite(tagged) or tagged != identity["temperature_c"]:
                raise ValueError(f"Temperature metadata disagrees with task ID: {path}")
        duration = float(metadata["acquisition_duration_s"])
        if not np.isfinite(duration) or duration < record.elapsed_s[-1]:
            raise ValueError(f"Invalid acquisition duration in {path}")
        channel = tdms[metadata["tdms_group_name"]][metadata["dcv_channel_name"]]
        recalculated = {"mean_v": record.readings_v.mean(), "sample_std_v": record.readings_v.std(ddof=1),
                        "equivalent_input_offset_v": record.readings_v.mean() / record.gain}
        for name, expected in recalculated.items():
            if name not in channel.properties or not np.isclose(float(channel.properties[name]), expected,
                                                               rtol=1e-10, atol=1e-18):
                raise ValueError(f"Saved TDMS statistic {name} does not match the samples: {path}")
        point = point_statistics(record, identity, metadata, tail_seconds)
        point["source_relative_path"] = path.relative_to(data_dir).as_posix()
        measurements.append(Measurement(record, identity, metadata, hashlib.sha256(path.read_bytes()).hexdigest(), point))
    grouped = {}
    for measurement in measurements:
        key = (measurement.identity["device_id"], measurement.identity["date"])
        grouped.setdefault(key, []).append(measurement)
    for key, group in grouped.items():
        group.sort(key=lambda m: m.identity["temperature_c"])
        if tuple(m.identity["temperature_c"] for m in group) != TEMPERATURES:
            raise ValueError(f"Missing one or more of {TEMPERATURES}: {key}")
    return measurements, grouped


def summarize_devices(grouped):
    summaries = []
    for (device, date), group in sorted(grouped.items()):
        means = [m.point["input_offset_mean_nv"] for m in group]
        tail = [m.point["last_window_mean_nv"] for m in group]
        whole_metrics = drift_metrics(TEMPERATURES, means)
        tail_metrics = drift_metrics(TEMPERATURES, tail)
        order = sorted(group, key=lambda m: m.record.acquisition_start_utc)
        row = {
            "device_id": device, "chip": group[0].identity["chip"], "test_date": date,
            "gain_v_per_v": group[0].record.gain,
            "counts_cold_ambient_hot": "/".join(str(m.point["reading_count"]) for m in group),
            "observed_acquisition_order_c": " -> ".join(f"{m.identity['temperature_c']:g}" for m in order),
            "offset_minus40_nv": means[0], "offset_27_nv": means[1], "offset_125_nv": means[2],
            "cold_minus_27_nv": means[0] - means[1], "hot_minus_27_nv": means[2] - means[1],
            **{k: v for k, v in whole_metrics.items() if k != "segment_slopes"},
            "cold_to_ambient_slope_nv_per_c": whole_metrics["segment_slopes"][0]["slope_nv_per_c"],
            "ambient_to_hot_slope_nv_per_c": whole_metrics["segment_slopes"][1]["slope_nv_per_c"],
            "tail_window_s": group[0].point["diagnostic_window_s"],
            "tail_box_drift_nv_per_c": tail_metrics["box_drift_nv_per_c"],
            "tail_linear_fit_slope_nv_per_c": tail_metrics["linear_fit_slope_nv_per_c"],
        }
        summaries.append(row)
    return summaries


def save_figure(fig, folder, name):
    fig.savefig(folder / (name + ".png"), dpi=180, facecolor="white")
    fig.savefig(folder / (name + ".svg"), facecolor="white")
    plt.close(fig)


def plots(folder, grouped, summaries, window_s):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "svg.fonttype": "none"})
    groups = list(sorted(grouped.items()))
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.6))
    for index, ((_, date), group) in enumerate(groups):
        color = COLORS[index % len(COLORS)]
        y = np.array([m.point["input_offset_mean_nv"] for m in group])
        sd = [m.point["input_offset_sample_std_nv"] for m in group]
        label = f"Chip {group[0].identity['chip']}"
        axes[0].errorbar(TEMPERATURES, y, yerr=sd, fmt="o-", color=color, capsize=4,
                         linewidth=1.7, label=label)
        axes[1].plot(TEMPERATURES, y - y[1], "o-", color=color, linewidth=1.7, label=label)
    axes[0].set(title="Mean offset and sample spread", ylabel="Input-referred offset (nV)")
    axes[1].set(title="Mean offset relative to 27 C", ylabel="Change from each chip's 27 C mean (nV)")
    axes[1].axhline(0, color="#64748b", linewidth=.8)
    for ax in axes:
        ax.set_xticks(TEMPERATURES)
        ax.set_xlabel("Nominal temperature (C)")
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle("RevB offset versus temperature", fontsize=17, y=.98)
    fig.text(.5, .025, "All supplied readings; G from TDMS = " + f"{groups[0][1][0].record.gain:g}. "
             "Left error bars: sample SD, not uncertainty of the mean. No temperature time series supplied.",
             ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .07, 1, .93))
    save_figure(fig, folder, "offset_vs_temperature")

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.5))
    x, width = np.arange(len(summaries)), .34
    for ax, field, title in zip(axes, ("box_drift_nv_per_c", "linear_fit_slope_nv_per_c"),
                               ("Observed box drift: (max mean - min mean) / 165 C", "Signed three-point linear fit slope")):
        full = [s[field] for s in summaries]
        tail = [s["tail_" + field] for s in summaries]
        first = ax.bar(x - width/2, full, width, label="All readings", color="#2563eb")
        last = ax.bar(x + width/2, tail, width, label=f"Last {window_s:g} s only", color="#94a3b8")
        ax.bar_label(first, fmt="%.4f", padding=4, fontsize=9)
        ax.bar_label(last, fmt="%.4f", padding=4, fontsize=9)
        ax.set_xticks(x, [f"Chip {s['chip']}" for s in summaries])
        ax.set(title=title, ylabel="Input-referred drift (nV/C)")
        ax.axhline(0, color="#64748b", linewidth=.8)
        ax.margins(y=.24)
        ax.grid(axis="y", alpha=.2)
        ax.legend(loc="upper left", fontsize=9)
    fig.suptitle("Offset drift and averaging-window sensitivity", fontsize=17, y=.98)
    fig.text(.5, .025, "Primary result uses every reading. The final-window result is a sensitivity check; "
             "it does not establish thermal stability.", ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .07, 1, .93))
    save_figure(fig, folder, "offset_drift_comparison")

    fig, axes = plt.subplots(len(groups), 3, figsize=(14, 3.05 * len(groups) + 1.2),
                             squeeze=False, sharey="row")
    for row, ((_, _), group) in enumerate(groups):
        for col, m in enumerate(group):
            ax = axes[row, col]
            y, seconds = m.input_nv, m.record.elapsed_s
            ax.plot(seconds / 60, y, color=COLORS[row % len(COLORS)], linewidth=.9)
            ax.axhline(m.point["input_offset_mean_nv"], color="#334155", ls="--", linewidth=1,
                       label="All-reading mean")
            ax.axvspan(max(seconds[0], seconds[-1] - window_s) / 60, seconds[-1] / 60,
                       alpha=.12, color="#475569", label=f"Last {window_s:g} s")
            ax.set_title(f"Chip {m.identity['chip']} | {m.identity['temperature_c']:g} C | "
                         f"N = {m.point['reading_count']}", fontsize=11)
            ax.text(.02, .96, f"Mean {y.mean():.2f} nV   SD {y.std(ddof=1):.2f} nV",
                    transform=ax.transAxes, va="top", fontsize=9,
                    bbox={"facecolor": "white", "alpha": .8, "edgecolor": "none"})
            ax.set_xlabel("Elapsed acquisition time (min)")
            ax.set_xlim(seconds[0] / 60, seconds[-1] / 60)
            ax.margins(y=.18)
            ax.grid(alpha=.2)
            if col == 0:
                ax.set_ylabel("Input-referred offset (nV)")
    axes[0, 0].legend(loc="lower left", fontsize=8)
    fig.suptitle("All recorded offset samples", fontsize=18, y=.985)
    fig.text(.5, .016, "Raw DCV divided by recorded gain; no filtering, detrending or sample rejection. "
             "Time axes are local to each acquisition; temperatures are nominal labels.",
             ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .045, 1, .95))
    save_figure(fig, folder, "offset_time_traces")


def make_report(folder, measurements, summaries, args):
    def ps_literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    rows = ["# 三温度 offset drift 数据分析", "", "主结果使用每份 TDMS 中的全部有效读数，按文件增益归算到输入端。",
            "温度来自 task-id 标签；本批输入没有温度过程文件。末段窗口仅用于检查均值对选取区间的敏感性。", "",
            "## 输入与方法", "", f"- 输入目录：`{args.data_dir}`。",
            f"- 文件数：{len(measurements)}；有效读数总数：{sum(m.point['reading_count'] for m in measurements)}。",
            f"- 增益：{measurements[0].record.gain:g} V/V，来自每个 TDMS 的 `closed_loop_gain_v_per_v`。",
            "- 单点 offset：`mean(DCV) / gain`；本报告用 nV 表示输入等效值。",
            "- 三点 box 温漂：`(max(Vos[-40,27,125]) - min(Vos[-40,27,125])) / 165`，单位 nV/℃。",
            "- 线性拟合：三个温度点等权最小二乘拟合 `Vos = a + b*T`，报告带符号斜率 b。",
            "- 同时保留端点及两段斜率。Box 值描述三个已测均值的跨度，不代表每一处的局部斜率或全温区保证值。",
            f"- Box 定义参考 [TI TIDA-010945 第 4.4.2 节]({METHOD_SOURCE})；本次只在三个提供的温度点上应用该公式。",
            "", "## 三点结果", "",
            "| 芯片 | −40℃ offset (nV) | 27℃ offset (nV) | 125℃ offset (nV) | Box (nV/℃) | 线性拟合 (nV/℃) | 端点斜率 (nV/℃) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summaries:
        rows.append(f"| Chip {s['chip']} | {s['offset_minus40_nv']:.4f} | {s['offset_27_nv']:.4f} | "
                    f"{s['offset_125_nv']:.4f} | {s['box_drift_nv_per_c']:.6f} | "
                    f"{s['linear_fit_slope_nv_per_c']:.6f} | {s['endpoint_slope_nv_per_c']:.6f} |")
    rows += ["", "![三温度 offset](offset_vs_temperature.png)", "", "## 采集波动与窗口敏感性", "",
             "| 芯片 | 温度 (℃) | 点数 | 时长 (s) | offset SD (nV) | 末窗口−首窗口均值 (nV) | 相邻读数相关系数 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in sorted(measurements, key=lambda m: (m.identity["chip"], m.identity["temperature_c"])):
        p = m.point
        rho = "<TBD>" if p["lag_one_sample_correlation"] is None else f"{p['lag_one_sample_correlation']:.4f}"
        rows.append(f"| Chip {p['chip']} | {p['nominal_temperature_c']:g} | {p['reading_count']} | "
                    f"{p['acquisition_duration_s']:.3f} | {p['input_offset_sample_std_nv']:.4f} | "
                    f"{p['last_minus_first_window_mean_nv']:.4f} | {rho} |")
    rows += ["", f"首／末窗口各 {args.tail_seconds:g} 秒，以实际读数时间筛选。",
             "相邻读数相关系数只作描述；图中的 SD 是样本波动，不能当作均值的总测量不确定度。",
             "本次不提供基于独立样本假设的均值置信区间，也不把窗口变化解释为确定的故障原因。", "",
             "| 芯片 | 全部读数 Box (nV/℃) | 仅末窗口 Box (nV/℃) | 全部读数拟合 (nV/℃) | 仅末窗口拟合 (nV/℃) |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for s in summaries:
        rows.append(f"| Chip {s['chip']} | {s['box_drift_nv_per_c']:.6f} | {s['tail_box_drift_nv_per_c']:.6f} | "
                    f"{s['linear_fit_slope_nv_per_c']:.6f} | {s['tail_linear_fit_slope_nv_per_c']:.6f} |")
    rows += ["", "![窗口敏感性](offset_drift_comparison.png)", "", "![逐点时序](offset_time_traces.png)", "",
             "## 测试条件与解释范围", "", args.test_conditions, "",
             "现场说明按上述内容记录；未提供同步温度日志，无法用本批 DMM 文件独立复核实际 DUT 温度、等待过程及采集期间的温度范围。",
             "读取文件时已检查任务号、run 编号、点数、Float64 通道、有限值、严格递增时间戳、保存的统计值及一致的 DMM 配置。",
             "本报告分析的是收到的文件；文件编号不连续不代表已取得此前所有运行记录。原始文件保持不变。", "",
             "固定增益归算得到的是整个测试链路的输入等效 offset。未独立扣除增益温漂、DMM 零点及连接处热电势，",
             f"因此不能直接将该系数归因于芯片本体。热电势的影响参见 [ADI 精密运放布局说明]({THERMAL_EMF_SOURCE})。", "",
             "### 文件中的实际采集顺序", ""]
    for s in summaries:
        rows.append(f"- Chip {s['chip']}：{s['observed_acquisition_order_c']} ℃；点数（冷／常／热）：{s['counts_cold_ambient_hot']}。")
    rows += ["", "## 文件与复现", "", "- `offset_drift_summary.csv`：各芯片 offset 和温漂指标。",
             "- `temperature_point_summary.csv`：每次采集的统计、时间和窗口诊断。",
             "- `all_readings.csv`：原始 DCV 和输入等效值，共同保留文件、run 与采集时间。",
             "- `input_manifest.json`：原始文件 SHA-256 和 TDMS 元数据。",
             "- `analysis_summary.json`：完整数值、方法、运行环境、验证状态和源码 SHA-256。",
             "- `code_snapshot/`：本次分析源码快照。图表另存 SVG 便于缩放。", "",
             "```powershell", f"& {ps_literal(sys.executable)} {ps_literal(Path(__file__).resolve())} `",
             f"  --data-dir {ps_literal(args.data_dir)} `",
             f"  --tail-seconds {args.tail_seconds:g} `",
             f"  --test-conditions {ps_literal(args.test_conditions)}", "```", "",
             "省略输出参数时创建新的带时间戳结果目录；也可用 `--output-dir` 指定尚不存在的目录。",
             "若有现场说明，可通过 `--test-conditions` 记录；`--tail-seconds` 默认 60。", ""]
    (folder / "README.md").write_text("\n".join(rows), encoding="utf-8")


def analyze(args):
    args.data_dir = args.data_dir.expanduser().resolve()
    measurements, grouped = load_measurements(args.data_dir, args.tail_seconds)
    summaries = summarize_devices(grouped)
    folder = args.output_dir or ROOT / "results/offset_drift" / (
        "analysis_" + datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S_%f"))
    folder = folder.expanduser().resolve()
    if folder.is_relative_to(args.data_dir):
        raise ValueError("Keep derived analysis outside the raw data directory")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "code_snapshot").mkdir()
    sources = [Path(__file__).resolve(), Path(dmm.__file__).resolve()]
    hashes = {}
    for source in sources:
        payload = source.read_bytes()
        (folder / "code_snapshot" / source.name).write_bytes(payload)
        hashes[source.name] = hashlib.sha256(payload).hexdigest()
    csv_write(folder / "temperature_point_summary.csv", [m.point for m in measurements])
    csv_write(folder / "offset_drift_summary.csv", summaries)
    all_readings = []
    for m in measurements:
        for index, (elapsed, output_v, input_nv) in enumerate(zip(m.record.elapsed_s, m.record.readings_v, m.input_nv), 1):
            all_readings.append({"task_id": m.metadata["task_id"], "chip": m.identity["chip"],
                "nominal_temperature_c": m.identity["temperature_c"], "run_number": m.record.run_number,
                "reading_index": index, "elapsed_s": float(elapsed),
                "timestamp_utc": (m.record.acquisition_start_utc + timedelta(seconds=float(elapsed))).isoformat(),
                "output_voltage_v": float(output_v), "gain_v_per_v": m.record.gain, "input_offset_nv": float(input_nv)})
    csv_write(folder / "all_readings.csv", all_readings)
    json_write(folder / "input_manifest.json", [{"path": m.point["source_relative_path"],
        "sha256": m.sha256, "size_bytes": m.record.path.stat().st_size, "tdms_root_properties": m.metadata}
        for m in measurements])
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    report = {"analysis_created_utc": datetime.now(timezone.utc).isoformat(), "input_directory": str(args.data_dir),
        "git_base_commit": git.stdout.strip() if git.returncode == 0 else None,
        "python_executable": sys.executable, "python_version": sys.version,
        "package_versions": {p: version(p) for p in ("numpy", "nptdms", "scipy", "matplotlib")},
        "script_sha256": hashes, "record_count": len(measurements), "reading_count": len(all_readings),
        "temperature_basis": "nominal task-id labels; no measured temperature log supplied",
        "primary_average": "all provided readings, no filtering/detrending/rejection",
        "drift_unit": "input-referred nV/C", "box_definition": "range of point means / temperature span",
        "fit_definition": "unweighted least squares of the three point means versus nominal temperature",
        "sample_std_is_measurement_uncertainty": False, "tail_sensitivity_window_s": args.tail_seconds,
        "test_conditions": args.test_conditions, "instrument_configuration": measurements[0].record.configuration,
        "source_references": {"box_drift": METHOD_SOURCE, "thermal_emf": THERMAL_EMF_SOURCE},
        "temperature_points": [m.point for m in measurements], "devices": summaries,
        "validation": {"complete_three_temperature_sets": True, "saved_tdms_statistics_match": True,
                       "matching_instrument_configuration": True, "raw_files_unchanged": False}}
    json_write(folder / "analysis_summary.json", report)
    plots(folder, grouped, summaries, args.tail_seconds)
    for m in measurements:
        if hashlib.sha256(m.record.path.read_bytes()).hexdigest() != m.sha256:
            raise RuntimeError(f"Input changed during analysis: {m.record.path}")
    report["validation"]["raw_files_unchanged"] = True
    json_write(folder / "analysis_summary.json", report)
    make_report(folder, measurements, summaries, args)
    print(json.dumps({"output_directory": str(folder), "records": len(measurements),
                      "readings": len(all_readings), "results": summaries}, ensure_ascii=False, indent=2))
    return folder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "results/offset_drift/data")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--tail-seconds", type=float, default=60.0)
    parser.add_argument("--test-conditions", default="罩体闭合情况、实际到温及到温后等待时间尚未得到本批测试的现场确认。")
    args = parser.parse_args(argv)
    if not np.isfinite(args.tail_seconds) or args.tail_seconds <= 0:
        parser.error("--tail-seconds must be finite and positive")
    analyze(args)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
