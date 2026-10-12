"""Task paths and acquisition bookkeeping; imports no instrument libraries."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid

BOARD_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BOARD_DIR.parent
DEFAULT_TASKS_ROOT = BOARD_DIR / "tasks"


def task_id_value(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError("task ID accepts letters, digits, dot, underscore and hyphen")
    if value.endswith(".") or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value.split(".")[0], re.I):
        raise argparse.ArgumentTypeError("task ID must be a valid Windows directory name")
    return value


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def readings_value(value: str) -> int:
    parsed = positive_int(value)
    if parsed < 2:
        raise argparse.ArgumentTypeError("at least two readings are required")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a nonnegative integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be nonnegative and finite")
    return parsed


def add_task_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True, type=task_id_value)
    parser.add_argument("--tasks-root", "--tasks-dir", type=Path, default=DEFAULT_TASKS_ROOT,
                        help="Directory containing one folder per task (default: RevB/tasks)")
    parser.add_argument("--chip", type=positive_int, help="Chip number saved in task.json")
    parser.add_argument("--dry-run", action="store_true", help="Print commands; no files, imports or hardware I/O")


def task_path(args: argparse.Namespace) -> Path:
    return args.tasks_root.expanduser().resolve() / args.task_id


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def acquisition_id() -> str:
    return datetime.now(timezone.utc).strftime("acquisition_%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def display_command(command: list[str]) -> str:
    # subprocess receives the list directly; this rendering is informational only.
    return subprocess.list2cmdline(command)


def print_plan(task: Path, commands: list[list[str]]) -> None:
    print(f"Task: {task.name}\nTask directory: {task}\nRaw data: {task / 'data'}")
    for command in commands:
        print(display_command(command))


def require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Acquisition requires the Windows field computer. Use --dry-run here or postprocess on this computer.")


def read_manifest(task: Path) -> dict:
    path = task / "task.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def check_resume_conditions(task: Path, configuration: dict, condition_keys: tuple[str, ...]) -> None:
    """Validate existing raw data before manifest edits or instrument launch."""
    if not any((task / "data").rglob("*.tdms")):
        return
    previous = read_manifest(task).get("acquisition_configuration")
    if not isinstance(previous, dict) or any(key not in previous for key in condition_keys):
        raise ValueError("Existing raw data have unknown acquisition conditions; use a new task ID")
    changed = [key for key in condition_keys if previous[key] != configuration[key]]
    if changed:
        raise ValueError("Existing raw data have different acquisition conditions (" + ", ".join(changed)
                         + "); use a new task ID")


def update_raw_file_hashes(task: Path, manifest: dict) -> None:
    """Hash canonical complete TDMS and retain earlier acquisition digests."""
    digests = manifest.setdefault("raw_file_sha256", {})
    fingerprints = manifest.setdefault("raw_file_fingerprints", {})
    integrity_errors = []
    for path in sorted((task / "data").rglob("*.tdms")):
        if path.name.lower().endswith(".partial.tdms"):
            continue
        relative = path.relative_to(task).as_posix()
        before = path.stat()
        fingerprint = {"size_bytes": before.st_size, "mtime_ns": before.st_mtime_ns}
        if relative in digests and fingerprints.get(relative) == fingerprint:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            integrity_errors.append(f"Raw TDMS changed while hashing: {relative}")
            continue
        measured_digest = digest.hexdigest()
        if relative in digests and digests[relative] != measured_digest:
            integrity_errors.append(f"Existing raw TDMS no longer matches its acquisition SHA-256: {relative}")
            continue
        digests[relative] = measured_digest
        fingerprints[relative] = fingerprint
    if integrity_errors:
        raise RuntimeError("; ".join(integrity_errors))


def prepare_task(task: Path, measurement_type: str, chip: int | None) -> dict:
    value = read_manifest(task)
    if value.get("task_id", task.name) != task.name:
        raise ValueError("task.json has a different task_id")
    if value.get("measurement_type", measurement_type) != measurement_type:
        raise ValueError("task.json describes a different measurement type; use a new task ID")
    if chip is not None and value.get("chip", chip) != chip:
        raise ValueError("task.json describes a different chip; use a new task ID")
    for name in ("data", "spectra", "results", "logs", "provenance"):
        (task / name).mkdir(parents=True, exist_ok=True)
    value.setdefault("schema_version", 1)
    value.setdefault("task_id", task.name)
    value.setdefault("board", "Unicorn_CSA_RevB-COB")
    value.setdefault("measurement_type", measurement_type)
    value.setdefault("created_at_utc", stamp())
    value.setdefault("paths", {name: name for name in ("data", "spectra", "results", "logs", "provenance")})
    if chip is not None:
        value["chip"] = chip
    atomic_json(task / "task.json", value)
    return value


@contextmanager
def acquisition_record(task: Path, *, measurement_type: str, chip: int | None,
                       commands: list[list[str]], sources: list[Path], run_id: str | None = None):
    """Publish failures too, and prevent two wrappers from owning the same task."""
    manifest = prepare_task(task, measurement_type, chip)
    run_id = run_id or acquisition_id()
    lock = task / ".acquisition.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "started_at_utc": stamp(), "run_id": run_id}) + "\n")
    try:
        run_dir = task / "provenance" / run_id
        run_dir.mkdir(exist_ok=False)
        snapshot = run_dir / "code_snapshot"
        snapshot.mkdir()
        digests = {}
        for source in dict.fromkeys(sources):
            content = source.read_bytes()
            name = source.relative_to(REPO_DIR).as_posix() if source.is_relative_to(REPO_DIR) else source.name
            destination = snapshot / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            digests[name] = hashlib.sha256(content).hexdigest()
        record = {"task_id": task.name, "measurement_type": measurement_type,
                  "acquisition_status": "acquiring", "started_at_utc": stamp(),
                  "python_executable": sys.executable, "python_version": sys.version,
                  "commands": commands, "source_sha256": digests, "run_id": run_id,
                  "log": f"logs/{run_id}.log"}
        manifest["acquisition_status"] = "acquiring"
        atomic_json(task / "task.json", manifest)
        atomic_json(run_dir / "acquisition.json", record)
        try:
            yield record, run_dir, task / record["log"]
            record.setdefault("exit_code", 0)
            record["acquisition_status"] = "completed" if record["exit_code"] == 0 else "failed"
        except BaseException as exc:
            record.update(acquisition_status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                          error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            record["finished_at_utc"] = stamp()
            record["completed_tdms_files"] = sum(1 for path in (task / "data").rglob("*.tdms")
                                                  if not path.name.endswith(".partial.tdms"))
            # Read again so callers can add metadata without losing it here.
            manifest = read_manifest(task)
            try:
                update_raw_file_hashes(task, manifest)
            except Exception as exc:
                record.update(acquisition_status="failed", raw_hash_error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                atomic_json(run_dir / "acquisition.json", record)
                manifest["acquisition_status"] = record["acquisition_status"]
                manifest["last_acquisition"] = f"provenance/{run_id}/acquisition.json"
                manifest["updated_at_utc"] = record["finished_at_utc"]
                atomic_json(task / "task.json", manifest)
    finally:
        lock.unlink(missing_ok=True)


def run_logged(command: list[str], log: Path) -> int:
    """Stream diagnostics to the console and a task log without invoking a shell."""
    with log.open("a", encoding="utf-8") as output:
        output.write(f"[{stamp()}] {display_command(command)}\n")
        output.flush()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1)
        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                output.write(line)
                output.flush()
            return process.wait()
        except KeyboardInterrupt:
            # On Windows both console processes receive Ctrl+C. Let the original
            # controller perform STOP and instrument cleanup before we return.
            if os.name != "nt" and process.poll() is None:
                process.send_signal(signal.SIGINT)
            while process.poll() is None:
                try:
                    process.wait(timeout=1)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    continue
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()


def cli(main) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Acquisition interrupted; verified files and failure provenance were retained.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
