#!/usr/bin/env python3
"""Product temperature sequence: -40, 27, 125 C; hold after first arrival, then stop."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import os
import sys
import time

from thermal_stream_temperature_run import (
    Client, FIELDS as SINGLE_FIELDS, PRESETS, ProtocolError, ROOT,
    encode_temperature, positive, temperature, utc_now,
)
from plot_thermal_stream_temperature import load_pyplot, plot_run


STAGES = (("cold", -40.0), ("ambient", 27.0), ("hot", 125.0))
FIELDS = tuple(key for key in SINGLE_FIELDS if key != "stable_for_s") + (
    "stage_index", "stage_mode", "stage_elapsed_s", "tolerance_c",
    "first_arrival_at_utc", "hold_elapsed_s", "hold_remaining_s",
    "program_mode", "timer_enabled",
)


class ArrivalTimer:
    """Latch first arrival. Later temperature excursions never reset this clock."""

    def __init__(self, target, tolerance, hold_seconds):
        self.target, self.tolerance, self.hold_seconds = target, tolerance, hold_seconds
        self.since = None

    def observe(self, now, value):
        inside = abs(value - self.target) <= self.tolerance + 1e-9
        first = inside and self.since is None
        if first:
            self.since = now
        elapsed = 0.0 if self.since is None else now - self.since
        return inside, first, elapsed, max(0.0, self.hold_seconds - elapsed), (
            self.since is not None and elapsed >= self.hold_seconds)


class SequenceAbort(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.50")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--unit-id", type=int, default=0)
    parser.add_argument("--interval", type=positive, default=1.0)
    parser.add_argument("--tolerance", type=positive, default=1.0)
    parser.add_argument("--hold-seconds", type=positive, default=300.0)
    parser.add_argument("--timeout", type=positive, default=3.0,
                        help="Socket timeout only; waiting for arrival has no time limit")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stop-file", type=Path)
    local_dependencies = ROOT / "tmp" / "thermal_plot_dependencies"
    parser.add_argument("--plot-dependency-dir", type=Path,
                        default=local_dependencies if local_dependencies.is_dir() else None)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 0 <= args.unit_id <= 255:
        parser.error("Invalid port or unit ID")
    return args


def configuration_matches(state, mode, target):
    return (state["product_control"] and not state["program_mode"]
            and not state["timer_enabled"] and state["setpoint_readback_c"] == target
            and all(state[f"{name}_mode"] == (name == mode) for name in PRESETS))


def run(args, *, client_factory=None, clock=None, plotter=None, plot_preflight=None):
    """Dependencies can be injected by offline tests; the CLI uses the real client."""
    client_factory = client_factory or Client
    clock = clock or time
    plotter = plotter or plot_run
    plot_preflight = plot_preflight or load_pyplot
    # Fail before connecting or issuing commands if required plotting support is missing.
    plot_preflight(args.plot_dependency_dir)
    folder = (args.output_dir or ROOT / "results" / "thermal_stream" / (
        "sequence_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    stop_file = (args.stop_file or folder / "STOP").resolve()
    snapshot_dir = folder / "code_snapshot"
    snapshot_dir.mkdir()
    hashes = {}
    for name in (Path(__file__).name, "thermal_stream_temperature_run.py",
                 "plot_thermal_stream_temperature.py"):
        data = (Path(__file__).parent / name).read_bytes()
        (snapshot_dir / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    summary = {
        "started_at_utc": utc_now(), "status": "preflight", "samples": 0,
        "sequence_completed": False, "stop_confirmed": None,
        "settings": {key: str(value) if isinstance(value, Path) else value
                     for key, value in vars(args).items()},
        "control": "product", "hold_policy": "fixed_time_after_first_arrival",
        "arrival_timeout_s": None, "output_dir": str(folder), "stages": [],
        "python_executable": sys.executable, "python_version": sys.version,
        "script_sha256": hashes,
    }
    started = clock.monotonic()
    owned = False
    client = None
    stage = None
    stage_started = None
    last_print = -15.0

    def save_summary(best_effort=False):
        try:
            temporary = folder / "summary.tmp"
            temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
            temporary.replace(folder / "summary.json")
        except OSError as exc:
            summary["summary_write_error"] = str(exc)
            if not best_effort:
                raise

    def check_stop():
        if stop_file.exists():
            raise SequenceAbort("stop_requested", "STOP file requested termination")

    def checked_sleep(seconds):
        deadline = clock.monotonic() + max(0.0, seconds)
        while clock.monotonic() < deadline:
            check_stop()
            clock.sleep(min(0.2, deadline - clock.monotonic()))

    print(f"OUTPUT_DIR={folder}\nStop request file: {stop_file}", flush=True)
    with ExitStack() as stack:
        wire = stack.enter_context((folder / "wire.jsonl").open("x", encoding="utf-8"))
        events = stack.enter_context((folder / "events.jsonl").open("x", encoding="utf-8"))
        csv_file = stack.enter_context((folder / "temperature.csv").open(
            "x", newline="", encoding="utf-8"))
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        csv_file.flush()

        def event(kind, *, best_effort=False, **details):
            entry = {"at_utc": utc_now(), "elapsed_s": round(clock.monotonic() - started, 6),
                     "event": kind, **details}
            if stage:
                entry.update(stage_index=stage["index"], mode=stage["mode"],
                             target_c=stage["target_c"])
            try:
                events.write(json.dumps(entry, ensure_ascii=False) + "\n")
                events.flush()
            except OSError as exc:
                summary["event_log_error"] = str(exc)
                if not best_effort:
                    raise

        def record(state, phase, *, now=None, at_utc=None, hold_elapsed=0.0):
            nonlocal last_print
            now = clock.monotonic() if now is None else now
            target = stage["target_c"] if stage else state["setpoint_readback_c"]
            error = state["product_temperature_c"] - target
            row = {key: state[key] for key in FIELDS if key in state}
            row.update(timestamp_utc=at_utc or utc_now(), elapsed_s=round(now - started, 6),
                       phase=phase, stage_index=stage["index"] if stage else 0,
                       stage_mode=stage["mode"] if stage else "preflight",
                       stage_elapsed_s=round(now - stage_started, 6) if stage_started is not None else 0,
                       controlled_temperature_c=state["product_temperature_c"], target_c=target,
                       tolerance_c=args.tolerance, error_c=round(error, 6),
                       in_band=abs(error) <= args.tolerance + 1e-9,
                       first_arrival_at_utc=stage.get("first_arrival_at_utc", "") if stage else "",
                       hold_elapsed_s=round(hold_elapsed, 6),
                       hold_remaining_s=round(max(0.0, args.hold_seconds - hold_elapsed), 6))
            writer.writerow(row)
            csv_file.flush()
            os.fsync(csv_file.fileno())
            summary["samples"] += 1
            summary["last_sample"] = row
            if now - started - last_print >= 15 or phase in ("configured", "stopped"):
                print(f"t={now-started:.1f}s stage={row['stage_index']} {phase}: "
                      f"product={state['product_temperature_c']:.1f} C, "
                      f"air={state['air_temperature_c']:.1f} C, target={target:g} C, "
                      f"hold={hold_elapsed:.1f}/{args.hold_seconds:g}s", flush=True)
                last_print = now - started
                save_summary()
            return row

        try:
            check_stop()
            client = client_factory(args.host, args.port, args.unit_id, args.timeout, wire,
                                    mode="cold")
            client.connect()
            initial = client.snapshot()
            low, high = temperature(client.register(3)), temperature(client.register(4))
            summary["preflight"] = {**initial, "control_min_c": low, "control_max_c": high,
                                    "flow_setting_raw": client.register(107)}
            event("preflight", **summary["preflight"])
            record(initial, "preflight")
            if not all(low <= target <= high for _, target in STAGES):
                raise ValueError(f"Sequence target outside device limits {low}..{high} C")
            if not low <= initial["product_temperature_c"] <= high:
                raise ValueError("Product feedback outside configured limits")
            if initial["defrost_active"] or initial["tuning_active"]:
                raise SequenceAbort("special_mode", "Device is in defrost or tuning mode")
            check_stop()
            owned = True

            for index, (mode, target) in enumerate(STAGES, 1):
                check_stop()
                stage = {"index": index, "mode": mode, "target_c": target,
                         "status": "configuring", "hold_samples": 0,
                         "hold_out_of_band_samples": 0, "hold_elapsed_s": 0.0}
                stage_started = None
                summary["stages"].append(stage)
                summary["status"] = "configuring"
                client.stop_verified()
                event("transition_stop_confirmed")
                check_stop()
                client.select_preset(mode)
                before = client.snapshot()
                if before["running"] or before["defrost_active"] or before["tuning_active"]:
                    raise SequenceAbort("configuration_changed", "Device not ready for reconfiguration")
                address, mode_coil = PRESETS[mode]
                client.exchange(6, address, encode_temperature(target))
                if temperature(client.register(address)) != target:
                    raise ProtocolError(f"R{address} target readback mismatch")
                event("setpoint_verified", address=address)
                for coil, value in ((20, False), (21, False), (22, True),
                                    *((c, False) for c in (14, 15, 16) if c != mode_coil),
                                    (mode_coil, True)):
                    check_stop()
                    client.set_coil(coil, value)
                configured = client.snapshot()
                record(configured, "configured")
                if (configured["running"] or not configuration_matches(configured, mode, target)
                        or configured["defrost_active"] or configured["tuning_active"]):
                    raise SequenceAbort("configuration_changed", "Configuration not confirmed before START")
                event("configured", **configured)
                check_stop()
                client.write_coil(0, True)
                deadline = clock.monotonic() + 5
                while not client.coil(10):
                    if clock.monotonic() >= deadline:
                        raise ProtocolError("START not confirmed by C10")
                    checked_sleep(0.25)
                stage_started = clock.monotonic()
                stage.update(status="waiting", started_at_utc=utc_now(),
                             started_at_elapsed_s=round(stage_started - started, 6))
                event("started")
                timer = ArrivalTimer(target, args.tolerance, args.hold_seconds)
                save_summary()

                while True:
                    tick = clock.monotonic()
                    check_stop()
                    state = client.snapshot()
                    now, stamp = clock.monotonic(), utc_now()
                    if not configuration_matches(state, mode, target):
                        record(state, "configuration_changed")
                        raise SequenceAbort("configuration_changed", "Control configuration changed")
                    if not state["running"]:
                        record(state, "device_stopped")
                        raise SequenceAbort("device_stopped", "Device stopped during sequence")
                    if state["defrost_active"] or state["tuning_active"]:
                        record(state, "special_mode")
                        raise SequenceAbort("special_mode", "Defrost or tuning became active")
                    if not low <= state["product_temperature_c"] <= high:
                        record(state, "invalid_feedback")
                        raise SequenceAbort("invalid_feedback", "Product feedback outside configured limits")
                    inside, first, elapsed, remaining, done = timer.observe(
                        now, state["product_temperature_c"])
                    if first:
                        stage.update(first_arrival_at_utc=stamp,
                                     first_arrival_at_elapsed_s=round(now - started, 6),
                                     time_to_arrival_s=round(now - stage_started, 6))
                        event("first_arrival", at_utc=stamp, elapsed_s=round(now - started, 6),
                              product_temperature_c=state["product_temperature_c"])
                    phase = "waiting" if timer.since is None else "holding"
                    summary["status"] = stage["status"] = phase
                    stage["hold_elapsed_s"] = round(elapsed, 6)
                    if timer.since is not None:
                        value = state["product_temperature_c"]
                        stage["hold_samples"] += 1
                        stage["hold_out_of_band_samples"] += int(not inside)
                        stage["hold_product_min_c"] = min(stage.get("hold_product_min_c", value), value)
                        stage["hold_product_max_c"] = max(stage.get("hold_product_max_c", value), value)
                    record(state, phase, now=now, at_utc=stamp, hold_elapsed=elapsed)
                    if first:
                        save_summary()
                    if done:
                        stage.update(status="completed", completed_at_utc=stamp,
                                     completed_at_elapsed_s=round(now - started, 6))
                        event("stage_completed", at_utc=stamp, elapsed_s=round(now - started, 6),
                              hold_elapsed_s=round(elapsed, 6))
                        save_summary()
                        break
                    delay = args.interval - (clock.monotonic() - tick)
                    if timer.since is not None:
                        delay = min(delay, remaining)
                    checked_sleep(delay)
            summary.update(status="completed", sequence_completed=True)
        except KeyboardInterrupt:
            summary.update(status="interrupted", error="KeyboardInterrupt")
            event("interrupted", best_effort=True)
        except SequenceAbort as exc:
            summary.update(status=exc.status, error=str(exc))
            event("aborted", best_effort=True, reason=str(exc), status=exc.status)
        except Exception as exc:
            summary.update(status="error", error=f"{type(exc).__name__}: {exc}")
            event("error", best_effort=True, error=summary["error"])
        finally:
            if stage and stage["status"] != "completed":
                stage.update(status="aborted", reason=summary.get("error", summary["status"]))
            if owned:
                try:
                    client.stop_verified()
                    summary["stop_confirmed"] = True
                    event("stop_confirmed", best_effort=True)
                except Exception as exc:
                    summary.update(stop_confirmed=False, stop_error=str(exc))
                    event("stop_not_confirmed", best_effort=True, error=str(exc))
                if summary["stop_confirmed"]:
                    try:
                        record(client.snapshot(), "stopped",
                               hold_elapsed=stage.get("hold_elapsed_s", 0) if stage else 0)
                    except Exception as exc:
                        summary["final_sample_error"] = str(exc)
            if client:
                client.close()
            summary.update(finished_at_utc=utc_now(), elapsed_s=round(clock.monotonic() - started, 6))
            save_summary(best_effort=True)

    # All device cleanup precedes rendering, including partial-run rendering.
    if summary["samples"]:
        try:
            summary["plot_path"] = str(plotter(folder, args.plot_dependency_dir))
        except Exception as exc:
            summary["plot_error"] = f"{type(exc).__name__}: {exc}"
    save_summary(best_effort=True)
    print(f"RESULT={summary['status']}; stop_confirmed={summary['stop_confirmed']}; "
          f"samples={summary['samples']}", flush=True)
    if summary.get("error"):
        print(summary["error"], flush=True)
    if summary.get("stop_error"):
        print(f"STOP NOT CONFIRMED: {summary['stop_error']}", flush=True)
    if summary.get("plot_error"):
        print(f"PLOT FAILED: {summary['plot_error']}", flush=True)
    return 0 if (summary["sequence_completed"] and summary["stop_confirmed"]
                 and "plot_path" in summary and not any(key in summary for key in (
                     "summary_write_error", "event_log_error", "final_sample_error"))) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(run(parse_args()))
    except (OSError, ImportError, ValueError) as error:
        print(f"Sequence could not finish: {error}", file=sys.stderr)
        raise SystemExit(1)
