#!/usr/bin/env python3
"""Set a temperature preset, record a trajectory, and stop on completion."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
import struct
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PRESETS = {"hot": (103, 14), "ambient": (104, 15), "cold": (105, 16)}
FIELDS = (
    "timestamp_utc", "elapsed_s", "phase", "air_temperature_c",
    "product_temperature_c", "controlled_temperature_c", "target_c",
    "setpoint_readback_c", "error_c", "in_band", "stable_for_s", "running",
    "product_control", "cold_mode", "cold_flag", "flow_raw",
    "temperature_output_raw", "temperature_slope_raw", "defrost_active", "tuning_active",
    "hot_mode", "hot_flag", "ambient_mode", "ambient_flag",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def temperature(raw: int) -> float:
    return (raw if raw < 32768 else raw - 65536) / 10.0


def encode_temperature(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("Temperature must be finite")
    scaled = round(value * 10)
    if abs(value * 10 - scaled) > 1e-6:
        raise ValueError("Temperature must be finite and a multiple of 0.1 C")
    if not -32768 <= scaled <= 32767:
        raise ValueError("Temperature does not fit a signed 16-bit register")
    return scaled & 0xffff


class ProtocolError(Exception):
    pass


class Client:
    """Sequential vendor-compatible requests; writes restricted to this task."""

    # An experiment subclass may explicitly allow documented R107 values.
    # Ordinary temperature runs retain their existing setpoint-only write scope.
    FLOW_WRITE_VALUES = frozenset()

    def __init__(self, host, port, unit, timeout, wire_log, *, mode="cold"):
        self.host, self.port, self.unit = host, port, unit
        self.timeout, self.wire_log = timeout, wire_log
        self.select_preset(mode)
        self.sock = None
        self.logging_failed = False

    def select_preset(self, mode):
        """Select the local read/write address; this does not write the device."""
        self.setpoint_address = PRESETS[mode][0]

    def connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), self.timeout)

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def exchange(self, function, address, value):
        if function not in (1, 3, 5, 6):
            raise ValueError("Unsupported function")
        if function == 5 and (address not in {0, 1, 14, 15, 16, 20, 21, 22}
                              or value not in {0, 0xff00}):
            raise ValueError("Coil write outside the temperature-run allowlist")
        if function == 6 and address != self.setpoint_address and not (
                address == 107 and value in self.FLOW_WRITE_VALUES):
            raise ValueError(f"Only the selected setpoint R{self.setpoint_address} may be written")
        if self.sock is None:
            raise ConnectionError("Not connected")
        request = struct.pack(">HHHBBHH", 0, 0, 6, self.unit, function, address, value)
        received = bytearray()
        record = {"at_utc": utc_now(), "function": function, "address": address,
                  "request_hex": request.hex(" ").upper(), "ok": False}

        def exact(count):
            part = bytearray()
            while len(part) < count:
                data = self.sock.recv(count - len(part))
                if not data:
                    raise ProtocolError("Connection closed during response")
                part.extend(data)
                received.extend(data)
            return bytes(part)

        try:
            self.sock.sendall(request)
            tid, pid, length, unit = struct.unpack(">HHHB", exact(7))
            if (tid, pid, unit) != (0, 0, self.unit) or not 2 <= length <= 254:
                raise ProtocolError("Unexpected MBAP header")
            pdu = exact(length - 1)
            if pdu[0] == function | 0x80:
                raise ProtocolError(f"Modbus exception: {pdu.hex(' ')}")
            if function in (5, 6):
                if pdu != request[7:]:
                    raise ProtocolError("Write response does not echo address and value")
                result = value
            else:
                size = 1 if function == 1 else 2
                if len(pdu) != size + 2 or pdu[:2] != bytes((function, size)):
                    raise ProtocolError("Unexpected read response")
                raw = int.from_bytes(pdu[2:], "big")
                result = bool(raw & 1) if function == 1 else raw
            record["ok"] = True
            return result
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            self.close()
            raise
        finally:
            record["response_hex"] = received.hex(" ").upper()
            if not self.logging_failed:
                try:
                    self.wire_log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    self.wire_log.flush()
                except OSError:
                    # Abort acquisition, but allow the cleanup STOP to use the
                    # network even if the disk can no longer accept wire logs.
                    self.logging_failed = True
                    raise

    def coil(self, address):
        return self.exchange(1, address, 1)

    def register(self, address):
        return self.exchange(3, address, 1)

    def write_coil(self, address, value):
        self.exchange(5, address, 0xff00 if value else 0)

    def set_coil(self, address, value):
        if self.coil(address) != value:
            self.write_coil(address, value)
        if self.coil(address) != value:
            raise ProtocolError(f"Coil C{address} readback mismatch")

    def snapshot(self):
        return {
            "air_temperature_c": temperature(self.register(0)),
            "product_temperature_c": temperature(self.register(1)),
            "temperature_output_raw": self.register(2),
            "setpoint_readback_c": temperature(self.register(self.setpoint_address)),
            "temperature_slope_raw": self.register(126),
            "flow_raw": self.register(102),
            "running": self.coil(10), "product_control": self.coil(22),
            "cold_mode": self.coil(16), "cold_flag": self.coil(19),
            "hot_mode": self.coil(14), "ambient_mode": self.coil(15),
            "hot_flag": self.coil(17), "ambient_flag": self.coil(18),
            "program_mode": self.coil(20), "timer_enabled": self.coil(21),
            "defrost_active": self.coil(24), "tuning_active": self.coil(25),
        }

    def stop_verified(self):
        errors = []
        for attempt in range(2):
            try:
                if self.sock is None:
                    self.connect()
                # Read first after any uncertain write; never blindly replay it.
                if not self.coil(10):
                    return
                self.write_coil(1, True)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if not self.coil(10):
                        return
                    time.sleep(0.25)
                raise ProtocolError("C10 remained ON after STOP")
            except (OSError, ProtocolError) as exc:
                errors.append(str(exc))
                self.close()
        raise ProtocolError("STOP NOT CONFIRMED: " + "; ".join(errors))


class StabilityWindow:
    def __init__(self, target, tolerance, hold, max_gap):
        self.target, self.tolerance, self.hold = target, tolerance, hold
        self.max_gap = max_gap
        self.since = self.previous = None

    def update(self, now, value, running):
        gap = self.previous is not None and now - self.previous > self.max_gap
        in_band = running and abs(value - self.target) <= self.tolerance + 1e-9
        if not in_band or gap:
            self.since = None
        if in_band and self.since is None:
            self.since = now
        duration = now - self.since if self.since is not None else 0.0
        self.previous = now
        return in_band, duration, in_band and duration >= self.hold


def positive(value):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be positive and finite")
    return parsed


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="192.168.1.50")
    p.add_argument("--port", type=int, default=3000)
    p.add_argument("--unit-id", type=int, default=0)
    p.add_argument("--target", type=float, default=-25.0)
    p.add_argument("--mode", choices=tuple(PRESETS), default="cold",
                   help="Select hot R103/C14, ambient R104/C15 or cold R105/C16")
    p.add_argument("--control", choices=("current", "air", "product"), default="current")
    p.add_argument("--interval", type=positive, default=1.0)
    p.add_argument("--tolerance", type=positive, default=1.0)
    p.add_argument("--hold-seconds", type=positive, default=60.0)
    p.add_argument("--max-seconds", type=positive, default=1200.0)
    p.add_argument("--timeout", type=positive, default=3.0)
    p.add_argument("--baseline-seconds", type=positive, default=5.0)
    p.add_argument("--stop-file", type=Path,
                   help="Creating this file requests a controlled stop")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--inspect", action="store_true", help="Read preflight only; no writes")
    p.add_argument("--keep-running", action="store_true",
                   help="Only on successful stabilization, leave temperature control running")
    args = p.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 0 <= args.unit_id <= 255:
        p.error("Invalid port or unit ID")
    if args.max_seconds <= args.baseline_seconds:
        p.error("max-seconds must exceed baseline-seconds")
    try:
        encode_temperature(args.target)
    except (ValueError, OverflowError) as exc:
        p.error(str(exc))
    return args


def run(args):
    folder = args.output_dir or ROOT / "results" / "thermal_stream" / (
        "temperature_run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    stop_file = args.stop_file or folder / "STOP"
    summary = {"started_at_utc": utc_now(), "settings": {
        k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "output_dir": str(folder), "status": "preflight", "samples": 0,
        "target_reached": False, "stop_confirmed": None}
    started = time.monotonic()
    owned = False
    selected_product = None
    setpoint_address, mode_coil = PRESETS[args.mode]
    summary["setpoint_register"] = setpoint_address
    summary["mode_coil"] = mode_coil
    last_status_time = -30.0
    window = StabilityWindow(args.target, args.tolerance, args.hold_seconds,
                             max(3 * args.interval, args.interval + 1))
    print(f"OUTPUT_DIR={folder}", flush=True)
    print(f"Stop request file: {stop_file}", flush=True)

    with (folder / "wire.jsonl").open("x", encoding="utf-8") as wire, \
         (folder / "events.jsonl").open("x", encoding="utf-8") as events, \
         (folder / "temperature.csv").open("x", newline="", encoding="utf-8") as csv_file:
        client = Client(args.host, args.port, args.unit_id, args.timeout, wire, mode=args.mode)
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        csv_file.flush()

        def configuration_matches(state):
            return (state["hot_mode"] == (args.mode == "hot")
                    and state["cold_mode"] == (args.mode == "cold")
                    and state["ambient_mode"] == (args.mode == "ambient")
                    and not state["program_mode"]
                    and not state["timer_enabled"]
                    and state["product_control"] == selected_product
                    and state["setpoint_readback_c"] == args.target)

        def event(kind, *, best_effort=False, **details):
            try:
                events.write(json.dumps({"at_utc": utc_now(), "event": kind, **details},
                                        ensure_ascii=False) + "\n")
                events.flush()
            except OSError as exc:
                summary["event_log_error"] = str(exc)
                # A failed event log must not prevent STOP or turn an already
                # confirmed STOP into a communication failure in the summary.
                if not best_effort:
                    raise

        def record(state, phase, track=False):
            nonlocal last_status_time
            elapsed = time.monotonic() - started
            product = state["product_control"] if selected_product is None else selected_product
            actual = state["product_temperature_c" if product else "air_temperature_c"]
            can_count_stability = (state["running"] and track
                                   and not state["defrost_active"] and not state["tuning_active"])
            in_band, duration, stable = window.update(elapsed, actual, can_count_stability)
            row = {k: state[k] for k in FIELDS if k in state}
            row.update(timestamp_utc=utc_now(), elapsed_s=round(elapsed, 3), phase=phase,
                       controlled_temperature_c=actual, target_c=args.target,
                       error_c=round(actual - args.target, 3), in_band=in_band,
                       stable_for_s=round(duration, 3))
            writer.writerow(row)
            csv_file.flush()
            os.fsync(csv_file.fileno())
            summary["samples"] += 1
            summary["last_sample"] = row
            if elapsed - last_status_time >= 15 or phase == "stopped":
                print(f"t={elapsed:.1f}s {phase}: air={state['air_temperature_c']:.1f} C, "
                      f"product={state['product_temperature_c']:.1f} C, "
                      f"running={state['running']}, stable={duration:.1f}s", flush=True)
                last_status_time = elapsed
            return stable

        try:
            client.connect()
            initial = client.snapshot()
            low, high = temperature(client.register(3)), temperature(client.register(4))
            summary["preflight"] = {**initial, "control_min_c": low, "control_max_c": high,
                                    "flow_setting_raw": client.register(107),
                                    "defrost_active": client.coil(24), "tuning_active": client.coil(25)}
            event("preflight", **summary["preflight"])
            record(initial, "baseline")
            if args.inspect:
                summary["status"] = "inspected"
                return 0
            if not low <= args.target <= high:
                raise ValueError(f"Target outside device limits {low}..{high} C")
            if summary["preflight"]["defrost_active"] or summary["preflight"]["tuning_active"]:
                raise ValueError("Device is in defrost or tuning mode")
            selected_product = (initial["product_control"] if args.control == "current"
                                else args.control == "product")
            summary["selected_control"] = "product" if selected_product else "air"
            actual = initial["product_temperature_c" if selected_product else "air_temperature_c"]
            if not low <= actual <= high:
                raise ValueError("Selected temperature feedback is outside configured limits")
            if stop_file.exists():
                raise ValueError("Stop request file already exists")
            owned = True
            while time.monotonic() - started < args.baseline_seconds:
                time.sleep(args.interval)
                record(client.snapshot(), "baseline")
            current = client.snapshot()
            if initial["running"] and not current["running"]:
                summary["status"] = "device_stopped"
                return 1
            if stop_file.exists():
                summary["status"] = "stop_requested"
                return 1
            already_selected = configuration_matches(current)
            if current["running"] and not already_selected:
                client.stop_verified()
                event("stopped_before_reconfiguration")
            # Establish and verify the requested target. Do not touch limits,
            # flow, slope, program registers or the ambiguous C17..C19 flags.
            client.exchange(6, setpoint_address, encode_temperature(args.target))
            if temperature(client.register(setpoint_address)) != args.target:
                raise ProtocolError(f"{args.mode.capitalize()} setpoint readback mismatch")
            event("setpoint_verified", address=setpoint_address, target_c=args.target,
                  mode=args.mode)
            for address, value in ((20, False), (21, False), (22, selected_product),
                                   *((address, False) for address in (14, 15, 16)
                                     if address != mode_coil), (mode_coil, True)):
                client.set_coil(address, value)
            configured = client.snapshot()
            event("configured", **configured)
            if not configuration_matches(configured):
                raise ProtocolError("Control configuration did not hold before START")
            if not configured["running"]:
                client.write_coil(0, True)
                deadline = time.monotonic() + 5
                while not client.coil(10):
                    if time.monotonic() >= deadline:
                        raise ProtocolError("START not confirmed by C10")
                    time.sleep(0.25)
                event("started")
            else:
                event("adopted_existing_run")
            summary["status"] = "recording"
            while True:
                tick = time.monotonic()
                if stop_file.exists():
                    summary["status"] = "stop_requested"
                    break
                state = client.snapshot()
                if not configuration_matches(state):
                    record(state, "configuration_changed")
                    raise ProtocolError("Control configuration changed during recording")
                phase = ("defrost" if state["defrost_active"] else
                         "tuning" if state["tuning_active"] else "recording")
                if record(state, phase, track=True):
                    summary.update(status="stabilized", target_reached=True,
                                   stabilized_at_elapsed_s=round(time.monotonic() - started, 3))
                    break
                if not state["running"]:
                    summary["status"] = "device_stopped"
                    break
                if time.monotonic() - started >= args.max_seconds:
                    summary["status"] = "timeout"
                    break
                time.sleep(max(0, args.interval - (time.monotonic() - tick)))
        except KeyboardInterrupt:
            summary["status"] = "interrupted"
            event("interrupted", best_effort=True)
        except Exception as exc:
            summary.update(status="error", error=f"{type(exc).__name__}: {exc}")
            event("error", best_effort=True, error=summary["error"])
            print(summary["error"], flush=True)
        finally:
            if owned and not (summary["target_reached"] and args.keep_running):
                try:
                    client.stop_verified()
                    summary["stop_confirmed"] = True
                    event("stop_confirmed", best_effort=True)
                except Exception as exc:
                    summary.update(stop_confirmed=False, stop_error=str(exc))
                    event("stop_not_confirmed", best_effort=True, error=str(exc))
                    print(f"STOP NOT CONFIRMED: {exc}", flush=True)
                if summary["stop_confirmed"]:
                    try:
                        record(client.snapshot(), "stopped")
                    except Exception as exc:
                        summary["final_sample_error"] = str(exc)
            client.close()
            summary["finished_at_utc"] = utc_now()
            summary["elapsed_s"] = round(time.monotonic() - started, 3)
            (folder / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"RESULT={summary['status']}; stop_confirmed={summary['stop_confirmed']}; "
                  f"samples={summary['samples']}", flush=True)
    return 0 if summary["target_reached"] and summary["stop_confirmed"] is not False else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(run(parse_args()))
