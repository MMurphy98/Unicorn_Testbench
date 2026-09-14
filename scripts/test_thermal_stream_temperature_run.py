"""Protocol and lifecycle checks without connecting to physical hardware."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import thermal_stream_temperature_run as run


class FragmentedSocket:
    def __init__(self, response):
        self.response = bytes.fromhex(response)
        self.sent = None
        self.requests = []

    def sendall(self, data):
        self.sent = data
        self.requests.append(data.hex())

    def recv(self, count):
        size = min(count, 2)
        part, self.response = self.response[:size], self.response[size:]
        return part

    def close(self):
        pass


class FakeClient:
    instances = []
    fail_while_running = False
    air_temperature_c = -26.0
    product_temperature_c = -25.0

    def __init__(self, *args, mode="cold"):
        self.running = False
        self.setpoint = -40.0
        self.mode = mode
        self.coils = {16: True, 19: True, 22: True}
        self.stopped = False
        self.writes = []
        self.instances.append(self)

    def connect(self): pass
    def close(self): pass

    def register(self, address):
        return {3: run.encode_temperature(-100), 4: 2350, 107: 120,
                run.PRESETS[self.mode][0]: run.encode_temperature(self.setpoint)}[address]

    def coil(self, address):
        return self.running if address == 10 else self.coils.get(address, False)

    def exchange(self, function, address, value):
        self.writes.append((function, address, value))
        self.setpoint = run.temperature(value)

    def set_coil(self, address, value):
        if self.coil(address) != value:
            self.write_coil(address, value)

    def write_coil(self, address, value):
        self.writes.append((5, address, value))
        if address == 0: self.running = True
        else: self.coils[address] = value

    def snapshot(self):
        if self.fail_while_running and self.running:
            raise OSError("Simulated lost response")
        return dict(air_temperature_c=self.air_temperature_c,
                    product_temperature_c=self.product_temperature_c,
                    temperature_output_raw=0, temperature_slope_raw=0,
                    defrost_active=False, tuning_active=False,
                    setpoint_readback_c=self.setpoint, flow_raw=120,
                    running=self.running, product_control=self.coil(22),
                    cold_mode=self.coil(16), cold_flag=self.coil(19),
                    hot_mode=self.coil(14), hot_flag=self.coil(17),
                    ambient_mode=self.coil(15), ambient_flag=self.coil(18),
                    program_mode=self.coil(20), timer_enabled=self.coil(21))

    def stop_verified(self):
        self.running = False
        self.stopped = True


class Tests(unittest.TestCase):
    def test_negative_temperature_and_write_frame(self):
        self.assertEqual(run.encode_temperature(-25), 0xff06)
        self.assertEqual(run.temperature(0xff06), -25)
        client = run.Client("unused", 3000, 0, 3, io.StringIO())
        peer = FragmentedSocket("00000000000600060069FF06")
        client.sock = peer
        client.exchange(6, 105, run.encode_temperature(-25))
        self.assertEqual(peer.sent.hex(), "00000000000600060069ff06")

    def test_bad_echo_and_forbidden_address(self):
        client = run.Client("unused", 3000, 0, 3, io.StringIO())
        client.sock = FragmentedSocket("000000000006000600690000")
        with self.assertRaises(run.ProtocolError):
            client.exchange(6, 105, 0xff06)
        with self.assertRaises(ValueError):
            client.exchange(6, 3, 0xff06)
        with self.assertRaises(ValueError):
            client.exchange(5, 19, 0xff00)

    def test_hot_target_frame_and_preset_write_isolation(self):
        client = run.Client("unused", 3000, 0, 3, io.StringIO(), mode="hot")
        peer = FragmentedSocket("0000000000060006006704e2")
        client.sock = peer
        client.exchange(6, 103, run.encode_temperature(125))
        self.assertEqual(peer.sent.hex(), "0000000000060006006704e2")
        with self.assertRaises(ValueError):
            client.exchange(6, 105, 0xff06)
        cold = run.Client("unused", 3000, 0, 3, io.StringIO())
        with self.assertRaises(ValueError):
            cold.exchange(6, 103, 1250)

    def test_stability_resets_on_departure_and_missing_samples(self):
        window = run.StabilityWindow(-25, 0.5, 3, 2)
        self.assertFalse(window.update(0, -25, True)[2])
        self.assertFalse(window.update(1, -24, True)[2])
        self.assertFalse(window.update(2, -25, True)[2])
        self.assertFalse(window.update(3, -25, True)[2])
        self.assertFalse(window.update(4, -25, True)[2])
        self.assertTrue(window.update(5, -25, True)[2])
        self.assertFalse(window.update(10, -25, True)[2])
        self.assertFalse(window.update(11, -25, False)[2])

    def test_stop_writes_command_then_verifies_running_is_false(self):
        client = run.Client("unused", 3000, 0, 3, io.StringIO())
        peer = FragmentedSocket("00000000000400010101 "
                                "00000000000600050001ff00 "
                                "00000000000400010100")
        client.sock = peer
        client.stop_verified()
        self.assertEqual(peer.requests, ["0000000000060001000a0001",
                                         "00000000000600050001ff00",
                                         "0000000000060001000a0001"])

    def test_uncertain_stop_reads_after_reconnect_before_any_retry(self):
        client = run.Client("unused", 3000, 0, 3, io.StringIO())
        first = FragmentedSocket("00000000000400010101")
        reconnected = FragmentedSocket("00000000000400010100")
        client.sock = first
        with patch.object(client, "connect", side_effect=lambda: setattr(client, "sock", reconnected)):
            client.stop_verified()
        self.assertEqual(first.requests[-1], "00000000000600050001ff00")
        self.assertEqual(reconnected.requests, ["0000000000060001000a0001"])

    def simulate(self, client_type=FakeClient, extra=()):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "run"
            args = run.parse_args(["--output-dir", str(folder), "--baseline-seconds", "0.001",
                                   "--interval", "0.002", "--hold-seconds", "0.01",
                                   "--max-seconds", "1", *extra])
            with patch.object(run, "Client", client_type), contextlib.redirect_stdout(io.StringIO()):
                code = run.run(args)
            summary = json.loads((folder / "summary.json").read_text())
            self.assertTrue((folder / "temperature.csv").is_file())
            return code, summary, client_type.instances[-1]

    def test_success_records_then_stops(self):
        code, summary, client = self.simulate()
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "stabilized")
        self.assertTrue(summary["stop_confirmed"])
        self.assertTrue(client.stopped)
        self.assertIn((6, 105, 0xff06), client.writes)

    def test_hot_run_switches_off_cold_before_start_and_records_hot_setpoint(self):
        class HotClient(FakeClient):
            air_temperature_c = 126.0
            product_temperature_c = 125.0

        code, summary, client = self.simulate(HotClient, extra=("--mode", "hot", "--target", "125"))
        self.assertEqual(code, 0)
        self.assertTrue(summary["stop_confirmed"])
        self.assertEqual(summary["setpoint_register"], 103)
        self.assertEqual(summary["last_sample"]["setpoint_readback_c"], 125.0)
        self.assertEqual(client.writes, [(6, 103, 1250), (5, 16, False),
                                         (5, 14, True), (5, 0, True)])
        self.assertTrue(summary["last_sample"]["hot_mode"])
        self.assertFalse(summary["last_sample"]["cold_mode"])
        self.assertTrue(client.stopped)

    def test_unconfirmed_mode_never_starts(self):
        class RevertingClient(FakeClient):
            def snapshot(self):
                self.coils[14] = False
                self.coils[16] = True
                return super().snapshot()

        code, summary, client = self.simulate(
            RevertingClient, extra=("--mode", "hot", "--target", "125"))
        self.assertEqual(code, 1)
        self.assertIn("before START", summary["error"])
        self.assertNotIn((5, 0, True), client.writes)
        self.assertTrue(client.stopped)

    def test_ambient_single_target_preserves_continuous_stability_behavior(self):
        class AmbientClient(FakeClient):
            air_temperature_c = 28.0
            product_temperature_c = 27.0

        code, summary, client = self.simulate(
            AmbientClient, extra=("--mode", "ambient", "--target", "27"))
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "stabilized")
        self.assertEqual(summary["setpoint_register"], 104)
        self.assertEqual(client.writes, [(6, 104, 270), (5, 16, False),
                                         (5, 15, True), (5, 0, True)])
        self.assertTrue(summary["last_sample"]["ambient_mode"])
        self.assertTrue(summary["stop_confirmed"])

    def test_changed_mode_during_hot_run_stops(self):
        class ChangedClient(FakeClient):
            def snapshot(self):
                state = super().snapshot()
                if self.running:
                    state["cold_mode"] = True
                return state

        code, summary, client = self.simulate(
            ChangedClient, extra=("--mode", "hot", "--target", "125"))
        self.assertEqual(code, 1)
        self.assertIn("changed during recording", summary["error"])
        self.assertFalse(summary["target_reached"])
        self.assertTrue(summary["stop_confirmed"])
        self.assertTrue(client.stopped)

    def test_lost_response_still_stops(self):
        class FailingClient(FakeClient):
            fail_while_running = True
        code, summary, client = self.simulate(FailingClient)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "error")
        self.assertTrue(client.stopped)
        self.assertTrue(summary["stop_confirmed"])

    def test_defrost_samples_do_not_count_as_stable_temperature(self):
        class DefrostingClient(FakeClient):
            def snapshot(self):
                state = super().snapshot()
                state["defrost_active"] = self.running
                return state

        code, summary, client = self.simulate(
            DefrostingClient, extra=("--max-seconds", "0.08",))
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "timeout")
        self.assertFalse(summary["target_reached"])
        self.assertTrue(client.stopped)

    def test_event_log_failure_does_not_erase_confirmed_stop(self):
        original_open = Path.open

        class FailingEventLog:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def flush(self): self.stream.flush()
            def write(self, value):
                if '"event": "stop_confirmed"' in value:
                    raise OSError("Simulated event log disk failure")
                return self.stream.write(value)

        def selective_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return FailingEventLog(stream) if path.name == "events.jsonl" else stream

        with patch.object(Path, "open", selective_open):
            code, summary, client = self.simulate()
        self.assertEqual(code, 0)
        self.assertTrue(client.stopped)
        self.assertTrue(summary["stop_confirmed"])
        self.assertIn("disk failure", summary["event_log_error"])

    def test_timeout_stops_and_inspect_never_writes(self):
        code, summary, client = self.simulate(extra=("--hold-seconds", "10", "--max-seconds", "0.03"))
        self.assertEqual(summary["status"], "timeout")
        self.assertTrue(client.stopped)
        code, summary, client = self.simulate(extra=("--inspect",))
        self.assertEqual(summary["status"], "inspected")
        self.assertEqual(client.writes, [])
        self.assertFalse(client.stopped)


if __name__ == "__main__":
    unittest.main()
