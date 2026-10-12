"""Read-only validation of this run's saved acquisition data; no device access."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from nptdms import TdmsFile

ROOT = Path(__file__).resolve().parent
TASK = "Offset_Chip_2_Gain1001_20260918"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    summary = read_json(ROOT / "summary.json")
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)

    check("completed_and_stopped", summary["status"] == "completed"
          and summary["sequence_completed"] and summary["stop_confirmed"])
    check("three_expected_stages", [s["target_c"] for s in summary["stages"]] == [-40, 27, 125])
    check("preflight_flow_6_scfm", summary["preflight"]["flow_setting_raw"] == 60)
    postflight = read_json(ROOT / "postflight.json")
    check("independent_stop_and_flow_confirmation", not postflight["thermal"]["running"]
          and postflight["thermal"]["flow_setting_raw"] == 60)
    check("main_process_exit_zero", read_json(ROOT / "process_result.json")["main_exit_code"] == 0)
    temperatures = read_csv(ROOT / "temperature.csv")
    check("temperature_row_count", len(temperatures) == summary["samples"])
    check("temperature_timestamps_ordered", all(a["timestamp_utc"] < b["timestamp_utc"]
          for a, b in zip(temperatures, temperatures[1:])))
    check("execution_snapshots_sha256", all(hashlib.sha256((ROOT / "code_snapshot" / name).read_bytes()).hexdigest() == digest
          for name, digest in summary["script_sha256"].items()))
    points, configurations = [], []
    for stage in summary["stages"]:
        index = stage["index"]
        prefix = f"stage_{index:02d}_"
        directory = ROOT / "dmm" / f"stage_{index:02d}"
        request_path = directory / "dmm_request.json"
        request, done = read_json(request_path), read_json(directory / "dmm_done.json")
        check(prefix + "flag_and_exit", stage["status"] == "completed"
              and done["status"] == "completed" and stage["dmm"]["worker_exit_code"] == 0)
        check(prefix + "request_identity", all(done[k] == request[k]
              for k in ("schema_version", "task_id", "run_id", "job_id", "stage_index", "target_c"))
              and done["request_sha256"] == hashlib.sha256(request_path.read_bytes()).hexdigest()
              and request["task_id"] == TASK)
        check(prefix + "count_and_gain", done["requested_readings"] == done["completed_readings"] == 1000
              and done["gain"] == request["dmm"]["gain"] == 1001)
        check(prefix + "hold_300s", stage["hold_elapsed_s"] >= 300
              and datetime.fromisoformat(done["first_reading_at_utc"]) > datetime.fromisoformat(stage["hold_completed_at_utc"]))
        artifacts = {k: directory / v for k, v in done["artifacts"].items()}
        check(prefix + "artifacts_exist", all(p.is_file() and p.stat().st_size > 0 for p in artifacts.values()))
        tdms = TdmsFile.read(artifacts["tdms"])
        meta = tdms.properties
        voltages = tdms[meta["tdms_group_name"]][meta["dcv_channel_name"]][:]
        elapsed = tdms[meta["tdms_group_name"]][meta["elapsed_time_channel_name"]][:]
        check(prefix + "tdms_valid", voltages.dtype == np.dtype("float64")
              and len(voltages) == len(elapsed) == meta["reading_count"] == 1000
              and np.all(np.isfinite(voltages)) and np.all(np.isfinite(elapsed))
              and np.all(np.diff(elapsed) > 0) and np.all(np.abs(voltages) <= 0.12)
              and meta["closed_loop_gain_v_per_v"] == 1001 and meta["task_id"] == TASK)
        rows, partial = read_csv(artifacts["readings_csv"]), read_csv(directory / "partial_readings.csv")
        check(prefix + "csv_counts_indices", len(rows) == len(partial) == 1000
              and [int(r["reading_index"]) for r in rows] == list(range(1, 1001))
              and [int(r["reading_index"]) for r in partial] == list(range(1, 1001)))
        check(prefix + "tdms_csv_values", np.allclose([float(r["output_voltage_v"]) for r in rows], voltages, rtol=6e-13, atol=1e-18)
              and np.array_equal([float(r["output_voltage_v"]) for r in partial], voltages)
              and np.array_equal([float(r["elapsed_s"]) for r in partial], elapsed)
              and np.array_equal([float(r["equivalent_input_offset_v"]) for r in partial], voltages / 1001)
              and np.allclose([float(r["equivalent_input_offset_v"]) for r in rows], voltages / 1001, rtol=6e-13, atol=1e-21)
              and np.allclose([float(r["elapsed_s"]) for r in rows], elapsed, rtol=6e-13, atol=1e-12))
        data = read_json(artifacts["summary"])
        config = data["configuration"]
        configurations.append(config)
        check(prefix + "dmm_configuration", config["instrument_serial_number"] == "04476049"
              and config["terminals"] in ("FRON", "FRONT") and config["range_v"] == 0.1
              and config["nplc"] == 10 and config["input_impedance_mode"] == "AUTO"
              and config["autozero_enabled"] and config["line_sync_enabled"]
              and config["line_frequency_hz"] == 50 and not config["autorange_enabled"]
              and not config["dmm_averaging_enabled"] and not config["relative_enabled"]
              and meta["discarded_reading_count"] == 3 and meta["settling_delay_s"] == 2)
        check(prefix + "summary_values", data["total_reading_count"] == 1000
              and np.isclose(data["equivalent_input_offset_v"]["mean"], np.mean(voltages / 1001), rtol=1e-12, atol=1e-20)
              and np.isclose(data["equivalent_input_offset_v"]["sample_std"], np.std(voltages / 1001, ddof=1), rtol=1e-12, atol=1e-20))
        matched = [r for r in temperatures if int(r["stage_index"]) == index
                   and done["first_reading_at_utc"] <= r["timestamp_utc"] <= done["last_reading_at_utc"]]
        values = np.array([float(r["product_temperature_c"]) for r in matched])
        gaps = np.diff([datetime.fromisoformat(r["timestamp_utc"]).timestamp() for r in matched])
        check(prefix + "temperature_coverage", len(values) > 0 and len(gaps) > 0
              and np.all(np.isfinite(values)) and np.all(gaps > 0))
        points.append({"stage_index": index, "target_c": stage["target_c"], "valid_readings": len(voltages),
                       "input_offset_mean_uv": float(np.mean(voltages / 1001) * 1e6),
                       "input_offset_std_uv": float(np.std(voltages / 1001, ddof=1) * 1e6),
                       "input_offset_peak_to_peak_uv": float(np.ptp(voltages / 1001) * 1e6),
                       "input_offset_first_100_mean_uv": float(np.mean(voltages[:100] / 1001) * 1e6),
                       "input_offset_last_100_mean_uv": float(np.mean(voltages[-100:] / 1001) * 1e6),
                       "output_mean_mv": float(np.mean(voltages) * 1e3),
                       "temperature_min_c": float(np.min(values)), "temperature_max_c": float(np.max(values)),
                       "temperature_mean_c": float(np.mean(values)), "temperature_samples": len(values),
                       "temperature_out_of_band_samples": int(np.sum(np.abs(values - stage["target_c"]) > 1 + 1e-9)),
                       "temperature_max_sample_gap_s": float(np.max(gaps)),
                       "reading_duration_s": float(elapsed[-1] - elapsed[0])})
    check("configuration_unchanged_across_stages", len(configurations) == 3 and all(c == configurations[0] for c in configurations))
    check("total_3000_valid_readings", sum(p["valid_readings"] for p in points) == 3000)
    drift = read_json(ROOT / "offset_drift_summary.json")
    check("aggregate_counts_and_means", len(drift["points"]) == len(points) == 3
          and all(a["stage_index"] == p["stage_index"] and a["target_c"] == p["target_c"]
                  and a["reading_count"] == 1000 and a["gain"] == 1001
                  and np.isclose(a["input_offset_mean_v"] * 1e6, p["input_offset_mean_uv"], rtol=1e-12, atol=1e-14)
                  and np.isclose(a["input_offset_sample_std_v"] * 1e6, p["input_offset_std_uv"], rtol=1e-12, atol=1e-14)
                  for a, p in zip(drift["points"], points)))
    check("aggregate_temperature_ranges", all(a["product_temperature_min_c"] == p["temperature_min_c"]
          and a["product_temperature_max_c"] == p["temperature_max_c"]
          and a["temperature_sample_count"] == p["temperature_samples"]
          and a["temperature_out_of_band_samples"] == p["temperature_out_of_band_samples"]
          for a, p in zip(drift["points"], points)))
    fit = np.polyfit([p["target_c"] for p in points], [p["input_offset_mean_uv"] * 1e-6 for p in points], 1)
    check("aggregate_drift_slope", np.isclose(fit[0], drift["nominal_temperature_linear_slope_v_per_c"], rtol=1e-12, atol=1e-18))
    report = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "all_passed": all(checks.values()),
              "checks": checks, "points": points,
              "note": "Data integrity and process checks are distinct from temperature stability. No stability pass is inferred."}
    (ROOT / "saved_data_verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
