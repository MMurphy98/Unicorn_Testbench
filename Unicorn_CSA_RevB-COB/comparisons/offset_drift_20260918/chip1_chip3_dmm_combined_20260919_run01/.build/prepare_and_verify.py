"""Extract and validate saved measurements; never connect to instruments."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

# The bundled runtime has NumPy but no TDMS reader. Use the installed, pure-Python
# npTDMS reader after bundled packages, without changing either environment.

from nptdms import TdmsFile

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
CSV = ROOT / "chip1_chip3_dmm_readings_20260918.csv"
FIELDS = ["chip_id", "stage_index", "target_temperature_c", "reading_index",
          "elapsed_s", "acquisition_time_utc", "output_voltage_v",
          "equivalent_input_offset_v", "equivalent_input_offset_uv",
          "gain_v_per_v", "flow_setpoint_scfm", "source_run_id"]
NUMERIC = [i for i in range(len(FIELDS)) if i not in (5, 11)]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources():
    rows, groups, sources = [], [], {}
    for chip in (1, 3):
        run = ROOT.parents[2] / "tasks" / f"Offset_Chip_{chip}_Gain1001_20260918" / "provenance/legacy_run"
        manifest = read_json(run / "artifact_sha256.json")

        def checked(path):
            digest = sha256(path)
            relative = path.relative_to(run).as_posix()
            assert digest == manifest[relative], f"Source hash mismatch: {path}"
            sources[path.relative_to(ROOT.parents[2]).as_posix()] = digest
            return path

        summary = read_json(checked(run / "offset_drift_summary.json"))
        process = read_json(checked(run / "summary.json"))
        verification = read_json(checked(run / "saved_data_verification.json"))
        assert summary["sequence_completed"] and verification["all_passed"]
        assert process["preflight"]["flow_setting_raw"] == 60
        assert [p["target_c"] for p in summary["points"]] == [-40, 27, 125]
        for point in summary["points"]:
            index, target = point["stage_index"], point["target_c"]
            stage = run / "dmm" / f"stage_{index:02d}"
            done = read_json(checked(stage / "dmm_done.json"))
            tdms_path = checked(stage / done["artifacts"]["tdms"])
            tdms = TdmsFile.read(tdms_path)
            meta = tdms.properties
            v = tdms[meta["tdms_group_name"]][meta["dcv_channel_name"]][:]
            elapsed = tdms[meta["tdms_group_name"]][meta["elapsed_time_channel_name"]][:]
            _, partial = read_csv(checked(stage / "partial_readings.csv"))
            _, published = read_csv(checked(stage / done["artifacts"]["readings_csv"]))
            assert done["status"] == "completed" and done["completed_readings"] == 1000
            assert done["stage_index"] == index and done["target_c"] == target
            assert meta["task_id"] == done["task_id"] == f"Offset_Chip_{chip}_Gain1001_20260918"
            assert meta["closed_loop_gain_v_per_v"] == point["gain"] == done["gain"] == 1001
            assert len(v) == len(elapsed) == len(partial) == len(published) == meta["reading_count"] == 1000
            assert v.dtype == elapsed.dtype == np.dtype("float64")
            assert np.all(np.isfinite(v)) and np.all(np.abs(v) <= 0.12)
            assert np.all(np.isfinite(elapsed)) and np.all(np.diff(elapsed) > 0)
            assert [int(r["reading_index"]) for r in partial] == list(range(1, 1001))
            assert [int(r["reading_index"]) for r in published] == list(range(1, 1001))
            assert np.array_equal(v, [float(r["output_voltage_v"]) for r in partial])
            assert np.array_equal(elapsed, [float(r["elapsed_s"]) for r in partial])
            assert np.array_equal(v / 1001, [float(r["equivalent_input_offset_v"]) for r in partial])
            assert np.allclose(v, [float(r["output_voltage_v"]) for r in published], rtol=6e-13, atol=1e-18)
            assert np.allclose(v / 1001, [float(r["equivalent_input_offset_v"]) for r in published], rtol=6e-13, atol=1e-21)
            start = datetime.fromisoformat(str(meta["acquisition_start_utc"])).replace(tzinfo=timezone.utc)
            stamps = [(start + timedelta(seconds=float(t))).isoformat(timespec="microseconds") for t in elapsed]
            assert stamps == [r["acquisition_time_utc"] for r in partial]
            assert stamps == [r["acquisition_time_utc"] for r in published]
            assert stamps[0] == done["first_reading_at_utc"] and stamps[-1] == done["last_reading_at_utc"]
            assert all(a < b for a, b in zip(stamps, stamps[1:]))
            mean, std = np.mean(v / 1001), np.std(v / 1001, ddof=1)
            assert np.isclose(mean, point["input_offset_mean_v"], rtol=1e-12, atol=1e-20)
            assert np.isclose(std, point["input_offset_sample_std_v"], rtol=1e-12, atol=1e-20)
            for j in range(1000):
                offset = float(v[j] / 1001)
                rows.append([chip, index, target, j + 1, float(elapsed[j]), stamps[j],
                             float(v[j]), offset, offset * 1e6, 1001, 6, run.name])
            groups.append({"chip_id": chip, "stage_index": index, "target_temperature_c": target,
                           "count": 1000, "mean_uv": float(mean * 1e6), "sample_std_uv": float(std * 1e6),
                           "source_tdms": tdms_path.relative_to(ROOT.parents[2]).as_posix(),
                           "first_reading_at_utc": stamps[0], "last_reading_at_utc": stamps[-1]})
    assert len(rows) == 6000 and len(groups) == 6
    assert len({(r[11], r[1], r[3]) for r in rows}) == 6000
    return rows, groups, sources


def prepare():
    rows, groups, sources = load_sources()
    (BUILD / "prepared_rows.json").write_text(json.dumps({"fields": FIELDS, "rows": rows}, allow_nan=False), encoding="utf-8")
    print(json.dumps({"source_groups_verified": len(groups), "readings": len(rows), "source_files_hash_checked": len(sources)}))


def write_readme(report):
    definitions = [
        ("chip_id", "芯片编号：1或3。"),
        ("stage_index", "该轮温度阶段：1=−40℃、2=27℃、3=125℃。"),
        ("target_temperature_c", "名义目标温度，单位℃；不是逐点实测产品温度。"),
        ("reading_index", "每个阶段内的有效读数序号，1～1000。"),
        ("elapsed_s", "原始TDMS的DMM采集相对时间，单位秒；每段独立起算，第一点约0.33秒。"),
        ("acquisition_time_utc", "原始采样时间戳，ISO 8601、UTC、微秒精度；北京时间为UTC+8。"),
        ("output_voltage_v", "DMM原始输出电压，单位V，从TDMS完整精度读取。"),
        ("equivalent_input_offset_v", "输入等效offset，单位V：output_voltage_v / 1001。"),
        ("equivalent_input_offset_uv", "输入等效offset，单位µV：equivalent_input_offset_v × 1000000，可直接绘图。"),
        ("gain_v_per_v", "实际增益元数据，所有行均为1001 V/V。"),
        ("flow_setpoint_scfm", "流量设定元数据，所有行均为6 SCFM；不是瞬时实测流量。"),
        ("source_run_id", "来源运行记录编号，用于区分Chip 1与Chip 3的独立测试。"),
    ]
    lines = ["# Chip 1 / Chip 3 DMM读数合并CSV", "",
             f"[下载统一CSV]({CSV.name})：6000条读数、12列，单行表头。Chip 1和Chip 3各3000点，−40℃、27℃、125℃各1000点。采集日期为2026-09-18。", "",
             "CSV为UTF-8带BOM编码、逗号分隔、小数点为句点。字段名含单位，数值单元格不混入单位文字。一个读数一行，按芯片、温度阶段、读数序号排列，可直接用Excel、Origin、MATLAB或Python导入。", "",
             "唯一键为source_run_id + stage_index + reading_index。该CSV可独立用于绘图，不需要TDMS或其他来源文件。", "",
             "## 字段与绘图", "", "| 字段 | 含义 |", "| --- | --- |"]
    lines += [f"| `{name}` | {meaning} |" for name, meaning in definitions]
    lines += ["", "绘制温度–offset曲线时，按chip_id、target_temperature_c分组，计算equivalent_input_offset_uv的均值和样本标准差（ddof=1）。绘制原始波形时，先选定一组芯片和目标温度，以elapsed_s或reading_index为横轴。输入等效列已经除过增益，不要再次除以1001。", "",
              "```python", "import pandas as pd", "import matplotlib.pyplot as plt", "",
              f'df = pd.read_csv("{CSV.name}", encoding="utf-8-sig", float_precision="round_trip")',
              'for chip, rows in df.groupby("chip_id"):',
              '    stats = rows.groupby("target_temperature_c")["equivalent_input_offset_uv"].agg(["mean", "std", "count"])',
              '    plt.errorbar(stats.index, stats["mean"], yerr=stats["std"], marker="o", label=f"Chip {chip}")',
              'plt.xlabel("Nominal temperature (deg C)")', 'plt.ylabel("Input-referred offset (uV)")',
              'plt.legend()', 'plt.tight_layout()', 'plt.show()', "```", "",
              "## 整理规则与核验", "",
              "六段TDMS的全部6000个有效读数均保留。未做平均、平滑、异常点删除、温度筛选、插值或重采样；各段采集前按协议丢弃的3个读数不属于原始TDMS的1000点有效数据。", "",
              "目标温度是分组标签。两轮均存在产品温度振荡及段内漂移，本CSV没有将低频温度记录插值成与DMM读数同步的实测温度。误差棒代表读数波动，不是均值置信区间。", "",
              f"已通过{len(report['checks'])}类核验：6000行、6组、各1000点，无缺失或重复；30个来源文件SHA-256一致；CSV的原始电压、相对时间和输入等效值与TDMS及计算结果逐点回读完全一致。原始电压最大差值为0 V。", "",
              "时间戳与TDMS采集起点加相对时间、两份原始逐点CSV及完成标志一致。六组均值和样本标准差与原报告一致；使用pandas的round_trip解析再次确认全部数值一致。", "",
              "| Chip | 目标温度(℃) | 点数 | 输入均值(µV) | 样本标准差(µV) |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for g in report["groups"]:
        lines.append(f"| {g['chip_id']} | {g['target_temperature_c']:g} | {g['count']} | {g['mean_uv']:+.9f} | {g['sample_std_uv']:.9f} |")
    lines += ["", f"CSV SHA-256：`{report['csv_sha256']}`。", "",
              "[逐项核验及原始TDMS来源](verification_report.json)。", "",
              "原始报告：[Chip 1](../chip1_gain1001_20260918_run01/README.md)、[Chip 3](../chip3_gain1001_20260918_run01/README.md)。原始运行目录保持不变。", ""]
    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def verify():
    expected, groups, sources = load_sources()
    fields, actual = read_csv(CSV)
    assert fields == FIELDS and len(actual) == 6000
    assert CSV.read_bytes().startswith(b"\xef\xbb\xbf")
    assert all(set(row) == set(FIELDS) and all(value != "" for value in row.values()) for row in actual)
    assert len({(r["source_run_id"], r["stage_index"], r["reading_index"]) for r in actual}) == 6000
    for saved, source in zip(actual, expected):
        for j, field in enumerate(FIELDS):
            if j in NUMERIC:
                assert float(saved[field]) == source[j], f"Numeric mismatch: {field} {saved}"
            else:
                assert saved[field] == source[j], f"Text mismatch: {field} {saved}"
    for group in groups:
        data = [r for r in actual if int(r["chip_id"]) == group["chip_id"] and int(r["stage_index"]) == group["stage_index"]]
        uv = np.array([float(r["equivalent_input_offset_uv"]) for r in data])
        assert len(data) == 1000
        assert np.isclose(uv.mean(), group["mean_uv"], rtol=1e-12, atol=1e-14)
        assert np.isclose(uv.std(ddof=1), group["sample_std_uv"], rtol=1e-12, atol=1e-14)
    import pandas as pd
    frame = pd.read_csv(CSV, encoding="utf-8-sig", float_precision="round_trip")
    assert frame.shape == (6000, 12)
    for j in NUMERIC:
        assert np.array_equal(frame[FIELDS[j]].to_numpy(), [r[j] for r in expected]), FIELDS[j]
    assert not frame.isna().any().any()
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(), "all_passed": True,
        "csv_file": CSV.name, "csv_sha256": sha256(CSV), "csv_size_bytes": CSV.stat().st_size,
        "row_count": len(actual), "column_count": len(FIELDS), "group_count": len(groups),
        "checks": {name: True for name in [
            "source_files_match_existing_sha256_manifests", "six_completed_stages_gain_1001_flow_6",
            "6000_valid_readings_1000_per_chip_temperature", "unique_keys_no_missing_or_duplicate_rows",
            "indices_and_timestamps_strictly_increasing_within_each_stage",
            "tdms_voltage_and_elapsed_equal_original_partial_csv",
            "tdms_agrees_with_published_csv_at_published_precision",
            "timestamps_equal_tdms_start_plus_elapsed_and_both_original_csvs",
            "exported_voltage_elapsed_and_offsets_round_trip_exactly",
            "gain_divided_exactly_once_and_microvolt_conversion_verified",
            "all_six_group_means_and_sample_standard_deviations_match_original_reports",
            "pandas_round_trip_import_matches_every_numeric_value", "utf8_bom_single_header_no_blank_cells"]},
        "maximum_raw_voltage_difference_v": 0.0, "maximum_elapsed_difference_s": 0.0,
        "groups": groups, "source_file_sha256": sources,
        "policy": "All 6000 saved valid readings retained. No averaging, smoothing, outlier deletion, temperature filtering, interpolation, or time resampling. The 3 pre-acquisition discarded readings per stage are not part of the saved valid records.",
        "temperature_column": "Nominal target temperature only; not a synchronized measured product temperature.",
    }
    (ROOT / "verification_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(report)
    print(json.dumps({k: report[k] for k in ("all_passed", "row_count", "column_count", "group_count", "csv_sha256", "maximum_raw_voltage_difference_v")}, indent=2))


if __name__ == "__main__":
    {"prepare": prepare, "verify": verify}[sys.argv[1]]()
