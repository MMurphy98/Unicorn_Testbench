#!/usr/bin/env python3
"""Read documented thermal-stream settings and outputs without changing the device."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from thermal_stream_temperature_run import Client, ROOT, positive, temperature, utc_now


READS = (
    (3, 0, "air_temperature_c", "temperature"),
    (3, 1, "product_temperature_c", "temperature"),
    (3, 2, "temperature_output_raw", "raw"),
    (3, 3, "control_min_c", "temperature"),
    (3, 4, "control_max_c", "temperature"),
    (3, 14, "defrost_candidate_R14_raw", "raw"),
    (3, 15, "defrost_candidate_R15_raw", "raw"),
    (3, 16, "defrost_candidate_R16_raw", "raw"),
    (3, 102, "flow_actual_raw", "raw"),
    (3, 103, "hot_setpoint_c", "temperature"),
    (3, 104, "ambient_setpoint_c", "temperature"),
    (3, 105, "cold_setpoint_c", "temperature"),
    (3, 106, "defrost_flow_setpoint_scfm", "tenths"),
    (3, 107, "flow_setpoint_scfm", "tenths"),
    (3, 109, "flow_output_raw", "raw"),
    (3, 110, "runtime_hours", "raw"),
    (3, 111, "runtime_minutes", "raw"),
    (3, 112, "runtime_seconds", "raw"),
    (3, 124, "defrost_time_H_raw", "raw"),
    (3, 125, "defrost_time_minutes", "tenths"),
    (3, 126, "temperature_slope_raw", "raw"),
    (1, 10, "running", "bool"),
    (1, 14, "hot_mode", "bool"),
    (1, 15, "ambient_mode", "bool"),
    (1, 16, "cold_mode", "bool"),
    (1, 17, "hot_flag", "bool"),
    (1, 18, "ambient_flag", "bool"),
    (1, 19, "cold_flag", "bool"),
    (1, 20, "program_mode", "bool"),
    (1, 21, "timer_enabled", "bool"),
    (1, 22, "product_control", "bool"),
    (1, 24, "defrost_active", "bool"),
    (1, 25, "tuning_active", "bool"),
)


class ReadOnlyClient(Client):
    def exchange(self, function, address, value):
        if function not in (1, 3):
            raise ValueError("Diagnostic client permits read operations only")
        return super().exchange(function, address, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.50")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--unit-id", type=int, default=0)
    parser.add_argument("--timeout", type=positive, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 <= args.unit_id <= 255:
        parser.error("Invalid port or unit ID")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output = args.output or ROOT / "results" / "thermal_stream" / f"diagnostics_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"started_at_utc": utc_now(), "read_only": True,
              "target": {"host": args.host, "port": args.port, "unit_id": args.unit_id},
              "reads": [], "notes": [
                  "Output and actual-flow units/scaling are not established by the documents.",
                  "Slope time base and the meaning of a zero slope are not documented.",
                  "Defrost temperature/period table addresses (15/16) conflict with example addresses (14/15).",
                  "For this device, R125=150 was matched to panel defrost time 15 min on 2026-09-11; use 0.1 min per count provisionally.",
                  "R124/R125 ranges and H/M composition are undocumented; the single R125 panel match is not a complete calibration.",
                  "A stopped-state snapshot cannot establish the preceding running-state output."]}
    with output.open("x", encoding="utf-8") as result_file, \
         output.with_suffix(".wire.jsonl").open("x", encoding="utf-8") as wire:
        client = ReadOnlyClient(args.host, args.port, args.unit_id, args.timeout, wire)
        try:
            client.connect()
            for function, address, name, kind in READS:
                raw = client.exchange(function, address, 1)
                value = (temperature(raw) if kind == "temperature" else
                         raw / 10 if kind == "tenths" else raw)
                report["reads"].append({"at_utc": utc_now(), "name": name,
                                        "function": function, "address": address,
                                        "raw": raw, "value": value})
                print(f"{name} = {value}", flush=True)
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
            print(report["error"], flush=True)
        finally:
            client.close()
            report["finished_at_utc"] = utc_now()
            report["ok"] = len(report["reads"]) == len(READS) and "error" not in report
            json.dump(report, result_file, ensure_ascii=False, indent=2)
            result_file.write("\n")
    print(f"Read-only diagnostic report: {output.resolve()}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
