"""OFFLINE TEST FIXTURE. Replaces VISA with a simulated DMM; no hardware access."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dmm_offset_worker as worker
from offset_drift_handshake import atomic_json


class Clock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class Instrument:
    def __init__(self, request, folder, clock):
        self.request, self.folder, self.clock = request, folder, clock
        self.reads, self.closed = 0, False
    def write(self, command): pass
    def close(self): self.closed = True
    def query(self, command):
        config = self.request["dmm"]
        if command == ":READ?":
            self.clock.now += .01
            self.reads += 1
            if self.request.get("simulation_case") == "fail" and self.reads == 7:
                raise TimeoutError("SIMULATED DMM timeout")
            if self.request.get("simulation_case") == "cancel" and self.reads == 7:
                (self.folder / "CANCEL").touch()
            return str(config["gain"] * (1e-6 + self.request["target_c"] * 2e-9)
                       + (self.reads % 5 - 2) * 1e-7)
        values = {
            "*IDN?": "KEITHLEY INSTRUMENTS,DMM7510,SIMULATED,OFFLINE",
            "*OPC?": "1", ":SYSTem:ERRor?": '0,"No error"',
            ":ROUTe:TERMinals?": config["terminals"], ":SENSe:FUNCtion?": '"VOLT:DC"',
            ":SENSe:VOLTage:RANGe:AUTO?": "0", ":SENSe:VOLTage:RANGe?": str(config["range_v"]),
            ":SENSe:VOLTage:INPutimpedance?": "AUTO", ":SENSe:VOLTage:NPLCycles?": str(config["nplc"]),
            ":SENSe:VOLTage:AZERo?": "1", ":SENSe:VOLTage:AVERage?": "0",
            ":SENSe:VOLTage:RELative:STATe?": "0", ":SENSe:VOLTage:LINE:SYNC?": "1",
            ":SYSTem:LFRequency?": "50",
        }
        return values[command]


class Manager:
    def __init__(self, instrument): self.instrument, self.closed = instrument, False
    def list_resources(self, _): return ("USB0::0x05E6::0x7510::SIMULATED::INSTR",)
    def open_resource(self, *args, **kwargs): return self.instrument
    def close(self): self.closed = True
    def __str__(self): return "OFFLINE SIMULATED VISA"


def run(path):
    path = Path(path)
    request = json.loads(path.read_text(encoding="utf-8"))
    case = request.get("simulation_case", "success")
    (path.parent / "simulation.ready").touch()
    if case == "crash": return 9
    if case == "hang":
        time.sleep(30)  # Parent cancellation test terminates this isolated fixture process.
        return 9
    capture, analyze = worker.load_modules()
    clock = Clock()
    instrument = Instrument(request, path.parent, clock)
    manager = Manager(instrument)
    epoch = datetime.fromisoformat(request["issued_at_utc"])

    class SimDateTime(datetime):
        @classmethod
        def now(cls, tz=None): return (epoch + timedelta(seconds=clock.now)).astimezone(tz or timezone.utc)

    import matplotlib.figure
    title = matplotlib.figure.Figure.suptitle
    with (patch.object(capture, "time", clock), patch.object(capture, "datetime", SimDateTime),
          patch.object(capture.pyvisa, "ResourceManager", return_value=manager),
          patch("socket.create_connection", side_effect=AssertionError("REAL NETWORK FORBIDDEN")),
          patch.object(matplotlib.figure.Figure, "suptitle", lambda fig, text, **kw: title(fig, "OFFLINE SIMULATION | " + text, **kw))):
        code = worker.run_request(path, modules=(capture, analyze))
    atomic_json(path.parent / "simulation.json", {"execution_environment": "offline_simulation",
                "real_instrument_connections": 0, "visa_closed": manager.closed and instrument.closed,
                "read_queries": instrument.reads})
    flag = path.parent / "dmm_done.json"
    if case == "no_flag":
        flag.unlink()
    elif case in ("bad_job", "bad_count", "bad_task"):
        data = json.loads(flag.read_text(encoding="utf-8"))
        key, value = {"bad_job": ("job_id", "0"*32), "bad_count": ("completed_readings", 999999),
                      "bad_task": ("task_id", "DifferentTask")}[case]
        data[key] = value
        atomic_json(flag, data)
    elif case in ("wrong_gain", "wrong_task"):
        result_path = path.parent / json.loads(flag.read_text(encoding="utf-8"))["artifacts"]["summary"]
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if case == "wrong_gain":
            data["configuration"]["closed_loop_gain_v_per_v"] = 999
        else:
            data["task_id"] = "DifferentTask"
        atomic_json(result_path, data)
    return code


if __name__ == "__main__":
    if "--check" in sys.argv:
        worker.load_modules()
        print("OFFLINE fixture dependencies OK")
    else:
        raise SystemExit(run(sys.argv[sys.argv.index("--request") + 1]))
