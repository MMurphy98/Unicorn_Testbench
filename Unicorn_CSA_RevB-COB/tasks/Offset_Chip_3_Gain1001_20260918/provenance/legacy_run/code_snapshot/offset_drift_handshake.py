"""File messages shared by independent temperature and DMM processes (no I/O drivers)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

SCHEMA_VERSION = 1
TARGETS = (-40.0, 27.0, 125.0)
DEFAULT_TASK_ID = "offset"


def task_id_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError(
            "Task ID must start with a letter or digit and contain only letters, digits, dot, underscore, or hyphen")
    if value.endswith(".") or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value.split(".")[0], re.I):
        raise argparse.ArgumentTypeError("Task ID must be a valid Windows directory name")
    return value


def dmm_artifacts(task_id):
    """Paths relative to a stage directory; preserve the existing DMM file layout."""
    task_id = task_id_value(task_id)
    return {
        "summary": f"results/{task_id}/{task_id}_dcv_offset_summary.json",
        "readings_csv": f"results/{task_id}/{task_id}_dcv_readings.csv",
        "plot": f"results/{task_id}/{task_id}_dcv_offset.png",
        "tdms": f"data/{task_id}/{task_id}_dcv_0001.tdms",
    }


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
    # Original schema-1 jobs omitted task_id and used the name "offset".
    request["task_id"] = task_id_value(request.get("task_id", DEFAULT_TASK_ID))
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
    args = ["--task-id", task_id_value(request.get("task_id", DEFAULT_TASK_ID)),
            "--runs", "1", "--output-dir", str(Path(folder) / "data")]
    for key, option in (("readings", "--readings"), ("gain", "--gain"),
                        ("range_v", "--range"), ("nplc", "--nplc"),
                        ("terminals", "--terminals"), ("input_impedance", "--input-impedance"),
                        ("settling_delay", "--settling-delay"), ("discard_readings", "--discard-readings"),
                        ("inter_reading_delay", "--inter-reading-delay"), ("timeout", "--timeout")):
        args.extend((option, str(config[key])))
    if config.get("resource"):
        args.extend(("--resource", config["resource"]))
    return args
