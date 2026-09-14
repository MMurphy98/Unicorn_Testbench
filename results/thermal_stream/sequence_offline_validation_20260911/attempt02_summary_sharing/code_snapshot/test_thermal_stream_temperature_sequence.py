"""Offline sequence tests. All instrument requests terminate in an in-memory device."""

import contextlib
import csv
import io
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import thermal_stream_temperature_run as base
import thermal_stream_temperature_sequence as sequence


class VirtualClock:
    def __init__(self):
        self.now = 0.0
        self.on_sleep = None

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 0)
        if self.on_sleep:
            self.on_sleep(self.now)


class SimulatedDevice:
    """Decode real request bytes, mutate simulated registers, return Modbus frames."""

    def __init__(self, clock, *, initially_running=False, fault=None, profile=None):
        self.clock, self.fault, self.profile = clock, fault, profile
        self.coils = {10: initially_running, 16: True, 19: True, 22: False}
        self.registers = {3: base.encode_temperature(-100), 4: 2350, 103: 1250,
                          104: 650, 105: base.encode_temperature(-25), 107: 120, 126: 0}
        self.writes, self.requests = [], []
        self.started_at = None
        self.start_temperature = 25.0
        self.stopped_temperature = 25.0
        self.fault_fired = False
        self.targets_written = 0
        self.stop_attempts = 0
        self.starts = 0

    @property
    def mode(self):
        return next((name for name, (_, coil) in base.PRESETS.items()
                     if self.coils.get(coil)), "cold")

    @property
    def target(self):
        return base.temperature(self.registers[base.PRESETS[self.mode][0]])

    def product(self):
        if not self.coils.get(10) or self.started_at is None:
            return self.stopped_temperature
        age = self.clock.now - self.started_at
        if self.profile:
            return self.profile(self, age)
        # Arrival after ~2 seconds, then excursions during the fixed hold.
        return self.target + (3 if age < 2 or age >= 4 else 0)

    def maybe_fault(self, function, address):
        if self.fault_fired or (function, address) != (3, 0):
            return
        if self.fault == "before_start" and not self.coils.get(10) and self.targets_written:
            self.coils[16] = False
            self.fault_fired = True
        elif self.starts and self.coils.get(10) and self.fault in {
                "communication", "interrupt", "defrost", "tuning", "configuration", "device_stopped"}:
            self.fault_fired = True
            if self.fault == "communication":
                raise TimeoutError("Simulated missing response")
            if self.fault == "interrupt":
                raise KeyboardInterrupt()
            if self.fault == "defrost": self.coils[24] = True
            if self.fault == "tuning": self.coils[25] = True
            if self.fault == "configuration": self.coils[22] = False
            if self.fault == "device_stopped": self.coils[10] = False

    def respond(self, request):
        self.clock.now += 0.001
        tid, pid, length, unit, function, address, value = struct.unpack(">HHHBBHH", request)
        assert (tid, pid, length, unit) == (0, 0, 6, 0)
        self.requests.append((function, address, value))
        self.maybe_fault(function, address)
        if function == 1:
            pdu = bytes((1, 1, int(bool(self.coils.get(address, False)))))
        elif function == 3:
            raw = {0: base.encode_temperature(round(self.product() + 8, 1)),
                   1: base.encode_temperature(round(self.product(), 1)),
                   2: 250 if self.coils.get(10) else 0, 102: 120}.get(address)
            if raw is None: raw = self.registers[address]
            pdu = bytes((3, 2)) + struct.pack(">H", raw)
        elif function == 6:
            assert address in (103, 104, 105)
            self.writes.append((function, address, value))
            self.registers[address] = value
            self.targets_written += 1
            pdu = request[7:]
        elif function == 5:
            assert address in (0, 1, 14, 15, 16, 20, 21, 22)
            self.writes.append((function, address, value))
            if address == 0:
                self.starts += 1
                self.start_temperature = self.stopped_temperature
                self.started_at = self.clock.now
                self.coils[10] = self.fault != "start_failure"
            elif address == 1:
                self.stop_attempts += 1
                if self.fault != "stop_failure":
                    self.stopped_temperature = self.product()
                    self.coils[10] = False
            else:
                self.coils[address] = bool(value)
                if address in (14, 15, 16): self.coils[address + 3] = bool(value)
            pdu = request[7:]
        else:
            raise AssertionError("Unexpected function")
        return struct.pack(">HHHB", 0, 0, len(pdu) + 1, 0) + pdu


class MemorySocket:
    def __init__(self, device):
        self.device = device
        self.response = b""

    def sendall(self, request):
        self.response = self.device.respond(request)

    def recv(self, count):
        part, self.response = self.response[:min(count, 2)], self.response[min(count, 2):]
        return part

    def close(self):
        pass


def client_factory(device):
    class SimulatedClient(base.Client):
        def connect(self):
            self.close()
            self.sock = MemorySocket(device)
    return SimulatedClient


def execute_simulation(folder, *, fault=None, initially_running=False, profile=None,
                       stop_after=None, hold=5, interval=1, render=False, plot_failure=False):
    clock = VirtualClock()
    device = SimulatedDevice(clock, initially_running=initially_running, fault=fault, profile=profile)
    if stop_after is not None:
        clock.on_sleep = lambda now: (folder / "STOP").touch() if now >= stop_after else None
    args = sequence.parse_args(["--output-dir", str(folder), "--hold-seconds", str(hold),
                                "--interval", str(interval)])

    def plotter(path, dependencies):
        if fault != "stop_failure":
            assert not device.coils.get(10), "Rendering ran before STOP"
        if plot_failure:
            raise OSError("Simulated plot failure")
        if render:
            return sequence.plot_run(path, dependencies)
        output = path / "temperature_curve.png"
        output.write_bytes(b"plot stub; not an image")
        return output

    # Any accidental real network connection fails the tests instead of reaching equipment.
    with (patch.object(base, "time", clock),
          patch.object(base.socket, "create_connection", side_effect=AssertionError("REAL NETWORK FORBIDDEN")),
          contextlib.redirect_stdout(io.StringIO())):
        code = sequence.run(args, client_factory=client_factory(device), clock=clock,
                            plotter=plotter,
                            plot_preflight=sequence.load_pyplot if render else lambda _: None)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    with (folder / "temperature.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return code, summary, rows, device


class Tests(unittest.TestCase):
    def simulate(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            return execute_simulation(Path(directory) / "run", **kwargs)

    def test_timer_waits_without_timeout_and_latches_inclusive_boundaries(self):
        for target in (-40, 27, 125):
            for boundary in (target - 1, target + 1):
                timer = sequence.ArrivalTimer(target, 1, 300)
                self.assertFalse(timer.observe(100000, target + 1.1)[4])
                self.assertIsNone(timer.since)
                self.assertTrue(timer.observe(100001, boundary)[1])
                self.assertFalse(timer.observe(100300, target + 10)[4])
                result = timer.observe(100301, target + 10)
                self.assertFalse(result[0])
                self.assertEqual(result[2], 300)
                self.assertTrue(result[4])

    def test_three_stages_use_exact_addresses_and_fixed_independent_holds(self):
        code, summary, rows, device = self.simulate(initially_running=True)
        self.assertEqual(code, 0)
        self.assertTrue(summary["sequence_completed"])
        self.assertTrue(summary["stop_confirmed"])
        self.assertEqual([w for w in device.writes if w[0] == 6],
                         [(6, 105, 0xfe70), (6, 104, 0x010e), (6, 103, 0x04e2)])
        self.assertEqual(device.writes[0], (5, 1, 0xff00))
        self.assertEqual(device.writes[-1], (5, 1, 0xff00))
        self.assertEqual(device.starts, 3)
        self.assertEqual(device.stop_attempts, 4)
        for stage in summary["stages"]:
            self.assertEqual(stage["status"], "completed")
            self.assertGreaterEqual(stage["hold_elapsed_s"], 5)
            self.assertLess(stage["hold_elapsed_s"], 6.1)
            self.assertGreater(stage["hold_out_of_band_samples"], 0)
            self.assertGreater(stage["time_to_arrival_s"], 1)
        for previous, following in zip(summary["stages"], summary["stages"][1:]):
            self.assertLess(previous["completed_at_elapsed_s"], following["started_at_elapsed_s"])
        self.assertEqual(rows[-1]["phase"], "stopped")
        self.assertNotIn("stable_for_s", rows[0])
        self.assertEqual(summary["arrival_timeout_s"], None)

    def test_no_arrival_does_not_time_out_at_old_twenty_minute_limit(self):
        code, summary, rows, device = self.simulate(
            profile=lambda d, age: d.target + 10, stop_after=1801, interval=60)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "stop_requested")
        self.assertGreater(summary["elapsed_s"], 1800)
        self.assertNotIn("first_arrival_at_utc", summary["stages"][0])
        self.assertEqual(device.starts, 1)
        self.assertTrue(summary["stop_confirmed"])

    def test_faults_abort_without_advancing_and_stop_before_plotting(self):
        cases = {"communication": "error", "interrupt": "interrupted",
                 "defrost": "special_mode", "tuning": "special_mode",
                 "configuration": "configuration_changed", "device_stopped": "device_stopped",
                 "before_start": "configuration_changed", "start_failure": "error"}
        for fault, status in cases.items():
            with self.subTest(fault=fault):
                code, summary, rows, device = self.simulate(fault=fault)
                self.assertEqual(code, 1)
                self.assertEqual(summary["status"], status)
                self.assertFalse(summary["sequence_completed"])
                self.assertTrue(summary["stop_confirmed"])
                self.assertEqual(len(summary["stages"]), 1)
                self.assertEqual(device.starts, 0 if fault == "before_start" else 1)
                self.assertIn("plot_path", summary)

    def test_stop_failure_is_reported_and_blocks_next_stage(self):
        code, summary, rows, device = self.simulate(fault="stop_failure")
        self.assertEqual(code, 1)
        self.assertFalse(summary["stop_confirmed"])
        self.assertIn("STOP NOT CONFIRMED", summary["stop_error"])
        self.assertEqual(device.starts, 1)
        self.assertFalse(summary["sequence_completed"])

    def test_stop_file_during_hold_does_not_start_next_stage(self):
        code, summary, rows, device = self.simulate(stop_after=4)
        self.assertEqual(summary["status"], "stop_requested")
        self.assertIn("first_arrival_at_utc", summary["stages"][0])
        self.assertEqual(device.starts, 1)
        self.assertTrue(summary["stop_confirmed"])

    def test_render_failure_preserves_completed_control_and_confirmed_stop(self):
        code, summary, rows, device = self.simulate(plot_failure=True)
        self.assertEqual(code, 1)
        self.assertTrue(summary["sequence_completed"])
        self.assertTrue(summary["stop_confirmed"])
        self.assertIn("plot failure", summary["plot_error"])

    def test_plot_dependency_failure_precedes_any_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            args = sequence.parse_args(["--output-dir", str(Path(directory) / "run")])
            with self.assertRaises(ImportError):
                sequence.run(args, client_factory=lambda *a, **k: self.fail("Unexpected connection"),
                             plot_preflight=lambda _: (_ for _ in ()).throw(ImportError("Missing plotting")))

    def test_event_write_failure_still_stops(self):
        original_open = Path.open

        class BrokenEvents:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def flush(self): self.stream.flush()
            def write(self, value):
                if '"event": "first_arrival"' in value:
                    raise OSError("Simulated event disk failure")
                return self.stream.write(value)

        def selective_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return BrokenEvents(stream) if path.name == "events.jsonl" and args[0] == "x" else stream

        with patch.object(Path, "open", selective_open):
            code, summary, rows, device = self.simulate()
        self.assertEqual(code, 1)
        self.assertTrue(summary["stop_confirmed"])
        self.assertEqual(device.starts, 1)
        self.assertIn("disk failure", summary["event_log_error"])


def generate_plot_fixture(folder):
    """Produce a full 3 x 300 s synthetic run for visual inspection, with no sockets."""
    def profile(device, age):
        ramp = 20.0
        if age < ramp:
            return device.start_temperature + (device.target - device.start_temperature) * age / ramp
        return device.target + 1.3 * math.sin((age - ramp) * 0.65)

    result = execute_simulation(folder, hold=300, profile=profile)
    summary = result[1]
    summary.update(execution_environment="offline_simulation", virtual_clock=True,
                   real_network_connections=0)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (folder / "code_snapshot" / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (folder / "OFFLINE_SIMULATION.txt").write_text(
        "Synthetic validation only. Virtual clock and in-memory Modbus peer; no physical device was used.\n",
        encoding="utf-8")
    sequence.plot_run(folder, sequence.parse_args([]).plot_dependency_dir)
    return result


if __name__ == "__main__":
    unittest.main()
