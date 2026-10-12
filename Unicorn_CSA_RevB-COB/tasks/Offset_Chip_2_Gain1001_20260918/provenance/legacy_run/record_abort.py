"""Verify and document the aborted Chip 2 run; reads saved files only."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def local(stamp):
    return datetime.fromisoformat(stamp).astimezone(timezone(timedelta(hours=8))).strftime("%H:%M:%S")


def main():
    summary, postflight, process = read("summary.json"), read("postflight.json"), read("process_result.json")
    request = read("dmm/stage_01/dmm_request.json")
    done = read("dmm/stage_01/dmm_done.json")
    stage = summary["stages"][0]
    with (ROOT / "temperature.csv").open(encoding="utf-8", newline="") as f:
        temperatures = list(csv.DictReader(f))
    with (ROOT / "dmm/stage_01/partial_readings.csv").open(encoding="utf-8", newline="") as f:
        readings = list(csv.DictReader(f))
    with (ROOT / "wire.jsonl").open(encoding="utf-8") as f:
        wire = [json.loads(line) for line in f]
    checks = {
        "sequence_aborted": summary["status"] == "error" and not summary["sequence_completed"],
        "main_and_worker_exit_one": process["main_exit_code"] == stage["dmm"]["worker_exit_code"] == 1,
        "worker_failure_recorded": done["status"] == "failed" and "Reading 1 is invalid or overrange" in done["error"],
        "request_and_failure_identity": all(done[k] == request[k] for k in ("schema_version", "task_id", "run_id", "job_id", "stage_index", "target_c")),
        "request_sha256": done["request_sha256"] == hashlib.sha256((ROOT / "dmm/stage_01/dmm_request.json").read_bytes()).hexdigest(),
        "chip2_label_and_gain": request["task_id"] == "Offset_Chip_2_Gain1001_20260918" and done["gain"] == request["dmm"]["gain"] == 1001,
        "zero_valid_readings": done["completed_readings"] == len(readings) == 0,
        "no_tdms_without_valid_data": not list(ROOT.rglob("*.tdms")),
        "later_stages_not_started": len(summary["stages"]) == 1 and not (ROOT / "dmm/stage_02").exists() and not (ROOT / "dmm/stage_03").exists(),
        "waiting_completed": stage["hold_elapsed_s"] >= 300,
        "temperature_rows_preserved": len(temperatures) == summary["samples"],
        "thermal_communication_succeeded": all(r["ok"] for r in wire),
        "controller_stop_confirmed": summary["stop_confirmed"] is True,
        "independent_stop_confirmed": not postflight["thermal"]["running"],
        "flow_6_scfm_confirmed": postflight["thermal"]["flow_setting_raw"] == 60,
        "dmm_fixed_range_preserved": float(postflight["dmm"]["range_v"]) == 0.1 and postflight["dmm"]["autorange"] == "0",
        "code_snapshots_match": all(hashlib.sha256((ROOT / "code_snapshot" / name).read_bytes()).hexdigest() == digest for name, digest in summary["script_sha256"].items()),
    }
    verification = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": "Abort handling and retained evidence verification; this is not a completed offset test.", "all_abort_checks_passed": all(checks.values()), "checks": checks,
                    "valid_readings": 0, "temperature_samples": len(temperatures), "thermal_requests": len(wire), "failed_thermal_requests": sum(not r["ok"] for r in wire)}
    (ROOT / "abort_verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    if not verification["all_abort_checks_passed"]:
        raise RuntimeError("Abort evidence verification failed")
    lines = ["# Chip 2 三温度 offset：首点超量程中止", "",
             f"2026-09-18 {local(summary['started_at_utc'])}–{local(summary['finished_at_utc'])}（Asia/Shanghai），Chip 2、Gain=1001测试在−40℃首点采集时中止。**有效电压读数为0，三温度测试未完成。**", "",
             "## 中止原因", "",
             "DMM配置读回通过：前端子、固定100 mV、10 NPLC、AUTO输入阻抗、Auto Zero及50 Hz同步开启；自动量程、内部平均、REL关闭。",
             "等待2秒后，3个丢弃读数均返回超量程/无效值；第一个计划保存的读数为`9.9e37 V`，触发无效/超量程保护。该值不作为实际电压或输入等效offset使用。", "",
             f"```text\n{done['error']}\n```", "",
             "目前只确认固定100 mV量程下无法取得有效读数，实际输出电压及现场原因尚未确定。未据此推测供电、trim或芯片故障。", "",
             "## 已执行与最终状态", "",
             "- 启动前受控停止27℃常温运行，再进入−40℃产品控温；流量设定6 SCFM。",
             f"- 首次进入−40℃±1℃耗时{stage['time_to_arrival_s']:.3f}秒，随后固定等待{stage['hold_elapsed_s']:.3f}秒。等待期间产品温度{stage['hold_product_min_c']:.1f}～{stage['hold_product_max_c']:.1f}℃，越界{stage['hold_out_of_band_samples']}/{stage['hold_samples']}个样本；流程不等于稳定性通过。",
             "- DMM失败标志已保存；主进程和DMM进程退出码均为1。没有进入27℃和125℃，没有自动改量程或续测。",
             f"- 程序于{local(summary['finished_at_utc'])}确认热流仪停止；{local(postflight['at_utc'])}独立只读复查仍为停止、R107=60（6 SCFM），当时产品温度{postflight['thermal']['product_temperature_c']:.1f}℃。",
             "- 独立复查DMM仍为DCV、前端子、固定100 mV、10 NPLC、AUTO输入阻抗；复查没有发起新的电压采样。",
             f"- 共保留{summary['samples']}条温度记录、{len(wire)}次热流仪通信（失败0次），{len(checks)}项中止处理及证据核验通过。", "",
             "没有有效电压数据，因此未生成有效TDMS、逐点结果CSV、offset均值或温漂斜率；`partial_readings.csv`只有表头。原计划的3000点及46项完整测试验收没有达成。", "",
             "## 保留文件", "",
             "- [总运行记录](summary.json)、[失败标志](dmm/stage_01/dmm_done.json)、[DMM完整日志](dmm/stage_01/worker.log)、[采集请求](dmm/stage_01/dmm_request.json)。",
             "- [部分读数文件（0点）](dmm/stage_01/partial_readings.csv)、[温度CSV](temperature.csv)、[温度曲线](temperature_curve.png)、[Modbus通信](wire.jsonl)、[事件日志](events.jsonl)。",
             "- [停机及DMM配置复查](postflight.json)、[进程退出结果](process_result.json)、[中止核验](abort_verification.json)、[执行环境](execution_context.json)、[代码快照](code_snapshot)。", "",
             "本目录已准备的`verify_saved_data.py`及`write_report.py`用于三点全部完成后的核验与报告，本次中止后未运行它们；本记录由`record_abort.py`生成。", "",
             "## 后续处理", "",
             "先确认Chip 2的现场接线、输入短接/offset测试状态、供电与输出电压。若要单独扩大量程定位输出电压，应作为另一次诊断记录；不能将诊断读数混入本次固定100 mV测试。",
             "重新开始正式三温度测试时使用新的运行目录，保留本次中止证据。", ""]
    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name != "artifact_sha256.json"}
    (ROOT / "artifact_sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
