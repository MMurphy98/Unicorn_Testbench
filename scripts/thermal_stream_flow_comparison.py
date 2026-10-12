#!/usr/bin/env python3
"""Hardware comparison at 27 C: constant 6, 8, then 6 SCFM; restore 6 and stop."""
import json
from pathlib import Path
import sys

import thermal_stream_temperature_sequence as sequence
from thermal_stream_temperature_run import Client, ProtocolError, ROOT, utc_now

FLOW_VALUES = (60, 80, 60)
EXTRA_FIELDS = ("flow_setpoint_raw", "flow_setpoint_scfm", "flow_output_raw")


class FlowClient(Client):
    FLOW_WRITE_VALUES = frozenset(FLOW_VALUES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_flow = None

    def set_flow(self, raw):
        if raw not in self.FLOW_WRITE_VALUES:
            raise ValueError("This comparison only permits 6 or 8 SCFM")
        if self.coil(10):
            raise ProtocolError("Flow changes require confirmed stopped state")
        self.expected_flow = None
        if self.register(107) != raw:
            self.exchange(6, 107, raw)
        actual = self.register(107)
        if actual != raw:
            raise ProtocolError(f"Flow setpoint readback mismatch: {actual} != {raw}")
        self.expected_flow = raw

    def snapshot(self):
        state = super().snapshot()
        raw = self.register(107)
        state.update(flow_setpoint_raw=raw, flow_setpoint_scfm=raw / 10,
                     flow_output_raw=self.register(109))
        if self.expected_flow is not None and raw != self.expected_flow:
            raise ProtocolError(f"Flow setpoint changed: {raw} != {self.expected_flow}")
        return state


def prepare_stage(client, stage, event):
    raw = FLOW_VALUES[stage["index"] - 1]
    client.set_flow(raw)
    stage["flow_setpoint_scfm"] = raw / 10
    event("flow_setpoint_verified", raw=raw, flow_scfm=raw / 10)
    print(f"FLOW_STAGE={stage['index']} setpoint={raw/10:g} SCFM", flush=True)


def recover(args, path, *, client_factory=FlowClient):
    result = {"started_at_utc": utc_now(), "stop_confirmed": False,
              "flow_restored": False, "restore_flow_scfm": 6.0}
    with path.with_suffix(".wire.jsonl").open("x", encoding="utf-8") as wire:
        client = client_factory(args.host, args.port, args.unit_id, args.timeout, wire)
        try:
            client.connect()
            client.stop_verified()
            result["stop_confirmed"] = True
            client.set_flow(60)
            result["flow_restored"] = True
            result["final_state"] = client.snapshot()
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            client.close()
            result["finished_at_utc"] = utc_now()
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    args = sequence.parse_args(argv)
    if args.output_dir is None:
        raise ValueError("An explicit new --output-dir is required")
    folder = args.output_dir.resolve()
    if folder.exists():
        raise FileExistsError(folder)
    # Resolve plotting support before any device interaction.
    sequence.load_pyplot(args.plot_dependency_dir)
    folder.parent.mkdir(parents=True, exist_ok=True)
    preflight = {"started_at_utc": utc_now(), "read_only": True}
    preflight_path = folder.with_name(folder.name + "_preflight.json")
    with preflight_path.with_suffix(".wire.jsonl").open("x", encoding="utf-8") as wire:
        client = FlowClient(args.host, args.port, args.unit_id, args.timeout, wire)
        try:
            client.connect()
            state = client.snapshot()
            preflight["state"] = state
            if state["running"] or state["defrost_active"] or state["tuning_active"]:
                raise ProtocolError("Expected stopped device without defrost or tuning")
            if state["flow_setpoint_raw"] != 60:
                raise ProtocolError("Expected baseline flow setpoint 6 SCFM; refusing to overwrite changed setup")
        finally:
            client.close()
            preflight_path.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = 1
    try:
        code = sequence.run(args, client_factory=FlowClient,
                            stages=(("ambient", 27.0),) * 3,
                            stage_setup=prepare_stage, extra_fields=EXTRA_FIELDS,
                            snapshot_sources=(Path(__file__),))
    finally:
        cleanup = recover(args, folder.with_name(folder.name + "_recovery.json"))
        print("FLOW_RECOVERY=" + json.dumps(cleanup, ensure_ascii=False), flush=True)
    return 0 if code == 0 and cleanup["stop_confirmed"] and cleanup["flow_restored"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
