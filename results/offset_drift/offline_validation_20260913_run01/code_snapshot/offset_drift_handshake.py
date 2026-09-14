"""File messages shared by independent temperature and DMM processes (no I/O drivers)."""
import hashlib
import json
import os
from pathlib import Path
import re
import time

SCHEMA_VERSION = 1
TARGETS = (-40.0, 27.0, 125.0)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32) or attempt == 4:
                raise
            time.sleep(.05)


def read_request(path):
    data = Path(path).read_bytes()
    request = json.loads(data)
    if request.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported DMM request schema")
    for key in ("run_id", "job_id"):
        if not re.fullmatch(r"[0-9a-f]{32}", str(request.get(key, ""))):
            raise ValueError(f"Invalid {key}")
    stage = request.get("stage_index")
    if type(stage) is not int or stage not in (1, 2, 3):
        raise ValueError("Invalid stage index")
    if request.get("target_c") != TARGETS[stage - 1]:
        raise ValueError("Stage target mismatch")
    if type(request["dmm"].get("readings")) is not int or request["dmm"]["readings"] < 2:
        raise ValueError("DMM readings must be an integer >= 2")
    return request, hashlib.sha256(data).hexdigest()


def capture_arguments(request, folder):
    """Use the existing capture CLI, one fresh task and one TDMS per temperature."""
    config = request["dmm"]
    args = ["--task-id", "offset", "--runs", "1", "--output-dir", str(Path(folder) / "data")]
    for key, option in (("readings", "--readings"), ("gain", "--gain"),
                        ("range_v", "--range"), ("nplc", "--nplc"),
                        ("terminals", "--terminals"), ("input_impedance", "--input-impedance"),
                        ("settling_delay", "--settling-delay"), ("discard_readings", "--discard-readings"),
                        ("inter_reading_delay", "--inter-reading-delay"), ("timeout", "--timeout")):
        args.extend((option, str(config[key])))
    if config.get("resource"):
        args.extend(("--resource", config["resource"]))
    return args
