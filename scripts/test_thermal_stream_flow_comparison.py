"""Offline tests of flow writes, comparison ordering, and uncertain-write recovery."""
import contextlib
import csv
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import thermal_stream_flow_comparison as flow
import thermal_stream_temperature_run as base
import thermal_stream_temperature_sequence as sequence
from test_thermal_stream_temperature_sequence import MemorySocket, SimulatedDevice, VirtualClock


class FlowDevice(SimulatedDevice):
    def __init__(self, clock, *, lose_flow_ack=False, change_running_flow=False):
        super().__init__(clock)
        self.registers.update({107: 60, 109: 20})
        self.lose_flow_ack = lose_flow_ack
        self.change_running_flow = change_running_flow

    def respond(self, request):
        _, _, _, _, function, address, value = struct.unpack(">HHHBBHH", request)
        if function == 6 and address == 107:
            assert not self.coils.get(10), "Flow written while running"
            assert value in (60, 80)
            self.requests.append((function, address, value))
            self.writes.append((function, address, value))
            self.registers[address] = value
            if self.lose_flow_ack and value == 80:
                self.lose_flow_ack = False
                raise TimeoutError("Write applied but acknowledgment lost")
            return request
        if self.change_running_flow and function == 3 and address == 107 and self.coils.get(10):
            self.registers[107] = 80
            self.change_running_flow = False
        return super().respond(request)


def factory(device):
    class SimulatedFlowClient(flow.FlowClient):
        def connect(self):
            self.close()
            self.sock = MemorySocket(device)
    return SimulatedFlowClient


class Tests(unittest.TestCase):
    def execute(self, **faults):
        clock = VirtualClock()
        device = FlowDevice(clock, **faults)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "run"
            args = sequence.parse_args(["--output-dir", str(folder), "--hold-seconds", "5"])
            with (patch.object(base, "time", clock),
                  patch.object(base.socket, "create_connection", side_effect=AssertionError("REAL NETWORK FORBIDDEN")),
                  contextlib.redirect_stdout(io.StringIO())):
                code = sequence.run(args, client_factory=factory(device), clock=clock,
                    stages=(("ambient", 27.0),) * 3, stage_setup=flow.prepare_stage,
                    extra_fields=flow.EXTRA_FIELDS, plot_preflight=lambda _: None,
                    plotter=lambda path, _: path / "plot_stub.png")
                recovery = flow.recover(args, Path(temp) / "recovery.json", client_factory=factory(device))
            summary = json.loads((folder / "summary.json").read_text())
            with (folder / "temperature.csv").open(newline="") as f:
                rows = list(csv.DictReader(f))
        return code, summary, rows, device, recovery

    def test_three_rounds_constant_setpoints_and_restore(self):
        code, summary, rows, device, recovery = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual([s["flow_setpoint_scfm"] for s in summary["stages"]], [6, 8, 6])
        self.assertEqual([w for w in device.writes if w[:2] == (6, 107)], [(6, 107, 80), (6, 107, 60)])
        self.assertEqual(device.starts, 3)
        for index, expected in enumerate((60, 80, 60), 1):
            held = [r for r in rows if int(r["stage_index"]) == index and r["phase"] == "holding"]
            self.assertTrue(held)
            self.assertEqual({int(r["flow_setpoint_raw"]) for r in held}, {expected})
        self.assertTrue(recovery["stop_confirmed"] and recovery["flow_restored"])
        self.assertFalse(device.coils[10])

    def test_lost_flow_ack_aborts_before_second_start_and_restores(self):
        code, summary, _, device, recovery = self.execute(lose_flow_ack=True)
        self.assertEqual(code, 1)
        self.assertEqual(device.starts, 1)
        self.assertFalse(summary["sequence_completed"])
        self.assertEqual([w for w in device.writes if w[:2] == (6, 107)], [(6, 107, 80), (6, 107, 60)])
        self.assertTrue(recovery["stop_confirmed"] and recovery["flow_restored"])

    def test_external_flow_change_aborts_and_restores(self):
        code, summary, _, device, recovery = self.execute(change_running_flow=True)
        self.assertEqual(code, 1)
        self.assertIn("Flow setpoint changed", summary["error"])
        self.assertEqual(device.starts, 1)
        self.assertTrue(recovery["flow_restored"])
        self.assertFalse(device.coils[10])

    def test_write_scope_is_explicit_and_running_changes_rejected(self):
        normal = base.Client("offline", 3000, 0, 1, io.StringIO())
        for address, value in ((107, 60), (109, 60)):
            with self.assertRaises(ValueError):
                normal.exchange(6, address, value)
        clock = VirtualClock()
        device = FlowDevice(clock)
        client = factory(device)("offline", 3000, 0, 1, io.StringIO())
        client.connect()
        with self.assertRaises(ValueError):
            client.exchange(6, 107, 100)
        device.coils[10] = True
        with self.assertRaises(base.ProtocolError):
            client.set_flow(80)
        self.assertEqual(device.writes, [])


if __name__ == "__main__":
    unittest.main()
