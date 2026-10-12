"""Create a report from this completed run's saved files; no instrument access."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = timezone(timedelta(hours=8))


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def local(stamp):
    return datetime.fromisoformat(stamp).astimezone(LOCAL).strftime("%H:%M:%S")


def main():
    summary = read("summary.json")
    verification = read("saved_data_verification.json")
    drift = read("offset_drift_summary.json")
    postflight = read("postflight.json")
    process = read("process_result.json")
    context = read("execution_context.json")
    if not verification["all_passed"]:
        raise RuntimeError("Saved data verification has not passed")
    with (ROOT / "wire.jsonl").open(encoding="utf-8") as stream:
        wire = [json.loads(line) for line in stream]
    wire_report = {"requests": len(wire), "failed_requests": sum(not r["ok"] for r in wire),
                   "function_counts": dict(Counter(r["function"] for r in wire)),
                   "flow_setting_writes": sum(r["function"] == 6 and r["address"] == 107 for r in wire)}
    (ROOT / "communication_verification.json").write_text(json.dumps(wire_report, indent=2) + "\n", encoding="utf-8")
    points = verification["points"]
    slope = drift["nominal_temperature_linear_slope_v_per_c"] * 1e9
    lines = ["# Chip 2 三温度 offset 实机测试记录", "",
             f"2026-09-18 {local(summary['started_at_utc'])}–{local(summary['finished_at_utc'])}（Asia/Shanghai），"
             f"完成 −40℃ → 27℃ → 125℃，各1000个有效读数，共3000点。主进程退出码 {process['main_exit_code']}，"
             "三个DMM子进程退出码均为0，数据回读和完成标志检查通过。", "",
             f"热流仪已停止；{local(postflight['at_utc'])} 独立复查 C10=0、R107=60（6 SCFM），"
             f"此时产品温度 {postflight['thermal']['product_temperature_c']:.1f}℃。", "",
             "**完成的是固定等待时间下的采集流程。三个温度点均存在温度振荡，不能视为持续±1℃稳定性通过。**", "",
             "## 条件及执行规则", "",
             "- 芯片：Chip 2；实际增益：1001 V/V，由用户确认。供电、trim等未提供条件不作推测。",
             f"- 任务标签：`{summary['settings']['task_id']}`。",
             "- 产品控温；目标−40、27、125℃。每点首次进入目标±1℃后固定等待300秒，后续越界不重置计时、不自动重测。",
             "- 固定流量设定6 SCFM：启动前和停止后均读回60；本次脚本没有写入R107。逐秒保存流量原始反馈，不能将起止读回描述为设定值的逐秒验证。",
             "- DMM7510：`USB0::0x05E6::0x7510::04476049::INSTR`，前端子、固定100 mV、10 NPLC、AUTO高输入阻抗。",
             "- Auto Zero及50 Hz同步开启；自动量程、内部平均、REL关闭。每段独立进程配置并读回；等待2秒，丢弃3读数，再保存1000点。",
             "- 温度和通信持续记录；通信错误、无效/超量程读数、配置或完成标志不匹配、采集超时均按入口规则中止并尝试停机。本轮没有触发中止。", "",
             "## 测量结果", "",
             "原始TDMS保存DMM输出电压；输入等效offset=输出电压/1001，仅除一次。标准差采用样本标准差（ddof=1），不是均值置信区间或纯随机噪声。", "",
             "| 目标温度 | 点数 | 输出均值(mV) | 输入offset均值(µV) | 输入标准差(µV) | 输入峰峰值(µV) | 采集实际产品温度范围 | 超出±1℃的温度样本 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for p in points:
        ratio = 100 * p["temperature_out_of_band_samples"] / p["temperature_samples"]
        lines.append(f"| {p['target_c']:g}℃ | {p['valid_readings']} | {p['output_mean_mv']:+.6f} | {p['input_offset_mean_uv']:+.6f} | {p['input_offset_std_uv']:.6f} | {p['input_offset_peak_to_peak_uv']:.6f} | {p['temperature_min_c']:.1f}～{p['temperature_max_c']:.1f}℃ | {p['temperature_out_of_band_samples']}/{p['temperature_samples']}（{ratio:.2f}%） |")
    lines += ["", f"三个名义温度点与各点输入等效均值的最小二乘直线斜率为 **{slope:+.6f} nV/℃**。",
              "该斜率是本次顺序测试的描述性拟合，受到温度振荡和读数随时间变化的影响，不能直接作为稳定控温下的器件温漂规格。",
              "实际温度统计只使用第一和最后一个有效DMM读数时间戳之间的温度样本，不插值补齐空隙。", "",
              "| 目标温度 | 实际温度均值 | 采集首100点输入均值(µV) | 末100点输入均值(µV) | 末段−首段(µV) | 温度最大采样间隔 |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for p in points:
        difference = p["input_offset_last_100_mean_uv"] - p["input_offset_first_100_mean_uv"]
        lines.append(f"| {p['target_c']:g}℃ | {p['temperature_mean_c']:.4f}℃ | {p['input_offset_first_100_mean_uv']:+.6f} | {p['input_offset_last_100_mean_uv']:+.6f} | {difference:+.6f} | {p['temperature_max_sample_gap_s']:.3f} s |")
    lines += ["", "首尾100点比较用于描述段内变化；主结果仍使用全部1000点，没有筛选温度或删除越界期间的读数。", "",
              "![输入等效offset与名义温度](offset_vs_temperature.png)", "",
              "## 时序及核验", "",
              "| 目标 | 首次到温耗时 | 固定等待 | 有效采集开始 | 有效采集结束 | 有效采集跨度 |",
              "| --- | ---: | ---: | --- | --- | ---: |"]
    for stage, p in zip(summary["stages"], points):
        job = stage["dmm"]
        lines.append(f"| {stage['target_c']:g}℃ | {stage['time_to_arrival_s']:.3f} s | {stage['hold_elapsed_s']:.3f} s | {local(job['first_reading_at_utc'])} | {local(job['last_reading_at_utc'])} | {p['reading_duration_s']:.3f} s |")
    lines += ["", f"总流程 {summary['elapsed_s']:.3f} 秒，共 {summary['samples']} 条温度记录。"
              f"主通信记录 {wire_report['requests']} 次请求，失败 {wire_report['failed_requests']} 次。",
              f"独立数据核验共 {len(verification['checks'])} 项全部通过，涵盖三个TDMS的float64读数、1000点数量、增益、逐点CSV一致性、请求SHA-256、完成标志、配置一致性、进程退出码、执行代码快照和最终停机/流量。",
              "实机启动前沿用已完成的11项离线联动测试；本轮未修改联动接口。", "",
              "## 文件", "",
              "- [总运行记录](summary.json)、[输入offset汇总](offset_drift_summary.json)、[三点汇总CSV](offset_vs_temperature.csv)。",
              "- [逐秒温度CSV](temperature.csv)、[温度曲线](temperature_curve.png)、[Modbus原始通信](wire.jsonl)、[事件记录](events.jsonl)。",
              "- [独立数据核验](saved_data_verification.json)、[通信统计](communication_verification.json)、[停机及流量复查](postflight.json)、[主进程结果](process_result.json)。",
              "- [启动复查](preflight.json)、[执行环境](execution_context.json)、[代码快照](code_snapshot)。", ""]
    for stage in summary["stages"]:
        base = Path("dmm") / f"stage_{stage['index']:02d}"
        artifacts = stage["dmm"]["artifacts"]
        links = "；".join(f"[{label}]({(base / artifacts[key]).as_posix()})" for key, label in (("tdms", "原始TDMS"), ("readings_csv", "逐点CSV"), ("plot", "读数图"), ("summary", "统计JSON")))
        lines.append(f"- {stage['target_c']:g}℃：{links}；[DMM日志]({(base / 'worker.log').as_posix()})。")
    lines += ["", "## 复现", "",
              f"基线Git HEAD：`{context['git_head']}`。工作区存在未提交修改；实际运行版本以`code_snapshot`和`summary.json`中的SHA-256为准。", "",
              "本次实机命令如下。重跑会再次操作硬件，必须使用新的运行目录；本轮没有自动续测或重测。", "",
              "```powershell",
              "& 'C:\\Users\\jinge\\Envs\\ni-scope-2023q4\\Scripts\\python.exe' -u .\\scripts\\thermal_stream_offset_drift.py --task-id Offset_Chip_2_Gain1001_20260918 --readings 1000 --gain 1001 --dmm-resource 'USB0::0x05E6::0x7510::04476049::INSTR' --terminals FRONT --dmm-range 0.1 --nplc 10 --host 192.168.1.50 --port 3000 --unit-id 0 --interval 1 --tolerance 1 --hold-seconds 300 --output-dir .\\results\\offset_drift\\chip2_gain1001_20260918_run01",
              "```", "", "目录内 `verify_saved_data.py` 和 `write_report.py` 仅处理本地已保存文件，不连接仪器。", ""]
    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name != 'artifact_sha256.json'}
    (ROOT / "artifact_sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(ROOT / "README.md"), "artifact_count": len(manifest),
                      "slope_nv_per_c": slope, "communication": wire_report}, indent=2))


if __name__ == "__main__":
    main()
