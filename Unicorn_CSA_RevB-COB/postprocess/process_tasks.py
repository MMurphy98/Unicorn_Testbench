#!/usr/bin/env python3
"""Replay RevB noise and temperature-offset tasks without instrument drivers.

The original analysis modules supply the numerical algorithms. This entry point
only handles the task directory layout, acquisition evidence, and overview.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OVERVIEW_COLUMNS = (
    "task_id", "measurement_type", "chip", "acquisition_status",
    "data_status", "processing_status", "raw_file_count", "spectrum_file_count",
    "valid_reading_count", "offset_stage_count", "noise_1_hz_nv_per_sqrt_hz",
    "noise_1000_hz_nv_per_sqrt_hz", "nominal_temperature_linear_slope_uv_per_c",
    "input_offset_mean_uv", "input_offset_sample_std_uv",
    "task_directory", "notes",
)
INCOMPLETE_ACQUISITION_STATES = {"failed", "aborted", "cancelled", "interrupted"}


class AcquisitionInProgressError(RuntimeError):
    """The field computer still owns this task; its outputs must stay untouched."""


def acquisition_in_progress(task_dir: Path, task: dict) -> bool:
    return ((task_dir / ".acquisition.lock").exists() or
            task.get("acquisition_status") == "acquiring")


def task_id_value(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError("Invalid task ID (use letters, digits, . _ -).")
    return value


def positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("Value must be positive.")
    return result


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                       encoding="utf-8")
    partial.replace(path)


def write_csv(path: Path, columns: tuple[str, ...] | list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


@lru_cache(maxsize=None)
def legacy_module(filename: str) -> Any:
    """Import only the three driver-free analysis modules retained in this repo."""
    allowed = {"analyze_dut_revb_pmu_noise.py", "plot_dut_revb_pmu_noise.py",
               "analyze_dmm7510_offset.py"}
    if filename not in allowed:
        raise ValueError(f"Not an offline analysis module: {filename}")
    name = "unicorn_offline_" + Path(filename).stem
    specification = importlib.util.spec_from_file_location(name, PROJECT_ROOT / filename)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load {filename}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module  # dataclasses resolves the defining module here.
    specification.loader.exec_module(module)
    return module


def load_task(task_dir: Path) -> dict[str, Any]:
    task = read_json(task_dir / "task.json")
    task_id = task_id_value(str(task.get("task_id", task_dir.name)))
    if task_id != task_dir.name:
        raise ValueError(f"Manifest task ID {task_id!r} differs from directory {task_dir.name!r}.")
    if task.get("measurement_type") not in {"noise", "offset_drift", "dcv_offset"}:
        raise ValueError(f"Unsupported measurement_type in {task_dir / 'task.json'}")
    task["task_id"] = task_id
    return task


def legacy_run_directory(task_dir: Path, task: dict) -> Path:
    provenance = task.get("provenance", {})
    relative = task.get("legacy_run_path", provenance.get("legacy_run", "provenance/legacy_run"))
    path = (task_dir / relative).resolve()
    if not path.is_relative_to(task_dir.resolve()):
        raise ValueError("Legacy acquisition evidence must remain inside its task directory.")
    return path


def noise_completeness(task: dict, captures: list, spectra: list) -> tuple[str, list[str]]:
    capture_runs = [number for number, _ in captures]
    spectrum_runs = [number for number, _ in spectra]
    expected_count = int(task.get("expected_run_count", task.get("expected_runs",
                            len(capture_runs) or len(spectrum_runs))))
    if expected_count <= 0:
        return "incomplete", ["No captures or spectra found."]
    expected = list(range(1, expected_count + 1))
    notes = []
    if capture_runs != expected:
        notes.append(f"Raw TDMS runs differ from expected 1..{expected_count}.")
    if spectrum_runs != expected:
        notes.append(f"Spectrum runs differ from expected 1..{expected_count}.")
    return ("complete" if not notes else "incomplete"), notes


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest_hash(task_dir: Path, task: dict, source: Path) -> bool:
    relative = source.relative_to(task_dir).as_posix()
    hashes = task.get("raw_file_sha256", {})
    if relative not in hashes:
        return False
    if file_sha256(source) != hashes[relative]:
        raise ValueError(f"Raw file SHA-256 mismatch: {relative}")
    return True


def validate_cached_noise(analyzer: Any, source: Path, output: Path, task_dir: Path,
                          task: dict, run: int) -> None:
    """Authenticate raw bytes or validate all samples, then check cached metadata."""
    import numpy as np
    task_id = task["task_id"]
    if verify_manifest_hash(task_dir, task, source):
        tdms = analyzer.TdmsFile.read_metadata(source)
        root = dict(tdms.properties)
        if str(analyzer.required_property(root, "task_id", str(source))) != task_id:
            raise ValueError(f"Raw task ID mismatch: {source}")
        group = str(analyzer.required_property(root, "tdms_group_name", str(source)))
        channel_name = str(analyzer.required_property(root, "tdms_channel_name", str(source)))
        channel = tdms[group][channel_name]
        if channel.dtype != np.dtype(np.float64) or len(channel) <= 0:
            raise ValueError(f"Invalid raw sample dtype or length: {source}")
        sample_count = len(channel)
        fs = 1. / analyzer.required_positive_float(dict(channel.properties), "wf_increment", str(source))
        gain = analyzer.required_positive_float(root, "closed_loop_gain_v_per_v", str(source))
        bandwidth = analyzer.required_positive_float(root, "estimated_closed_loop_bandwidth_hz", str(source))
        raw_run = int(analyzer.required_property(root, "run_number", str(source)))
    else:
        samples, fs, gain, bandwidth, raw_run, channel_name = analyzer.read_capture(source, task_id)
        sample_count = samples.size
    if raw_run != run:
        raise ValueError(f"Raw run metadata mismatch: {source}")
    with np.load(output, allow_pickle=False) as archive:
        def scalar(name: str) -> Any:
            if name not in archive.files:
                raise ValueError(f"Cached spectrum missing {name!r}: {output}")
            return archive[name].item()
        expected = {
            "format_version": analyzer.SPECTRUM_FORMAT_VERSION,
            "task_id": task_id, "run_number": run, "channel_name": channel_name,
            "source_sample_count": sample_count, "welch_window": "hann",
            "welch_detrend": "constant", "welch_average": "mean",
        }
        for key, value in expected.items():
            if scalar(key) != value:
                raise ValueError(f"Cached spectrum {key} differs from raw capture: {output}")
        nperseg = int(scalar("welch_nperseg"))
        if nperseg < 2 or nperseg > sample_count:
            raise ValueError(f"Invalid cached Welch segment size: {output}")
        noverlap = nperseg // 2
        segments = 1 + (sample_count - nperseg) // (nperseg - noverlap)
        if scalar("welch_noverlap") != noverlap or scalar("welch_segment_count") != segments:
            raise ValueError(f"Cached Welch segment metadata mismatch: {output}")
        floats = {"sample_rate_hz": fs, "closed_loop_gain_v_per_v": gain,
                  "estimated_closed_loop_bandwidth_hz": bandwidth,
                  "frequency_resolution_hz": fs / nperseg}
        for key, value in floats.items():
            if not np.isclose(scalar(key), value, rtol=1e-12, atol=0.):
                raise ValueError(f"Cached spectrum {key} differs from raw capture: {output}")


def process_noise(task_dir: Path, task: dict, *, recompute_spectra: bool = False,
                  nperseg: int = 262_144) -> dict:
    analyzer = legacy_module("analyze_dut_revb_pmu_noise.py")
    plotter = legacy_module("plot_dut_revb_pmu_noise.py")
    task_id = task["task_id"]
    captures = analyzer.numbered_tdms_files(task_dir / "data", task_id)
    spectra_dir = task_dir / "spectra"
    spectra_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for filename_run, source in captures:
        output = spectra_dir / f"{source.stem}_spectrum.npz"
        if output.exists() and not recompute_spectra:
            validate_cached_noise(analyzer, source, output, task_dir, task, filename_run)
            continue
        verify_manifest_hash(task_dir, task, source)
        samples, fs, gain, bandwidth, run, channel = analyzer.read_capture(source, task_id)
        if run != filename_run:
            raise ValueError(f"TDMS run {run} differs from filename run {filename_run}: {source}")
        frequency, psd, segments, resolution = analyzer.calculate_input_psd(samples, fs, gain, nperseg)
        analyzer.save_spectrum(
            output, overwrite=recompute_spectra, frequency_hz=frequency,
            input_psd_v2_per_hz=psd, source_tdms=source, task_id=task_id,
            run_number=run, channel_name=channel, sample_rate_hz=fs,
            closed_loop_gain=gain, closed_loop_bandwidth_hz=bandwidth,
            sample_count=samples.size, nperseg=nperseg, segment_count=segments,
            frequency_resolution_hz=resolution,
        )
        created += 1
    spectra = plotter.numbered_spectrum_files(spectra_dir, task_id)
    if not spectra:
        raise FileNotFoundError(f"No spectra available for {task_id}.")
    plotter.main(["--task-id", task_id, "--task-dir", str(task_dir)])
    summary = read_json(task_dir / "results" / f"{task_id}_noise_summary.json")
    data_status, notes = noise_completeness(task, captures, spectra)
    if task.get("acquisition_status") in INCOMPLETE_ACQUISITION_STATES:
        data_status = "incomplete"
        notes.append("Acquisition did not complete; estimates cover saved records only.")
    return {
        "task_id": task_id, "measurement_type": "noise", "chip": task.get("chip"),
        "acquisition_status": task.get("acquisition_status", "unknown"),
        "data_status": data_status, "processing_status": "completed",
        "raw_file_count": len(captures), "spectrum_file_count": len(spectra),
        "spectra_created": created, "spectra_reused": len(spectra) - created,
        "noise_1_hz_nv_per_sqrt_hz": summary["targets"]["1_hz"]["smoothed_estimate_asd_nv_per_sqrt_hz"],
        "noise_1000_hz_nv_per_sqrt_hz": summary["targets"]["1000_hz"]["smoothed_estimate_asd_nv_per_sqrt_hz"],
        "summary_file": f"results/{task_id}_noise_summary.json", "notes": notes,
    }


def matched_temperature(stage: dict, temperatures: list[dict]) -> dict:
    job = stage.get("dmm", {})
    first_text, last_text = job.get("first_reading_at_utc"), job.get("last_reading_at_utc")
    if first_text is None or last_text is None:
        matched = []
    else:
        first, last = datetime.fromisoformat(first_text), datetime.fromisoformat(last_text)
        matched = [row for row in temperatures if row["stage_index"] == str(stage["index"])
                   and first <= datetime.fromisoformat(row["timestamp_utc"]) <= last]
    values = [float(row["product_temperature_c"]) for row in matched]
    return {
        "product_temperature_mean_c": statistics.mean(values) if values else None,
        "product_temperature_min_c": min(values) if values else None,
        "product_temperature_max_c": max(values) if values else None,
        "temperature_sample_count": len(values),
        "temperature_out_of_band_samples": sum(row["in_band"].lower() == "false" for row in matched),
        "first_reading_at_utc": first_text, "last_reading_at_utc": last_text,
    }


def process_offset_drift(task_dir: Path, task: dict) -> dict:
    task_id = task["task_id"]
    legacy_dir = legacy_run_directory(task_dir, task)
    acquisition = read_json(legacy_dir / "summary.json")
    acquisition_task = acquisition.get("settings", {}).get("task_id", task_id)
    if acquisition_task != task_id:
        raise ValueError(f"Legacy acquisition task ID {acquisition_task!r} differs from {task_id!r}.")
    temperature_file = legacy_dir / "temperature.csv"
    temperatures = []
    if temperature_file.exists():
        with temperature_file.open(encoding="utf-8", newline="") as stream:
            temperatures = list(csv.DictReader(stream))
    points, stages, notes = [], [], []
    analyzer = None
    raw_count = 0
    seen_stages = set()
    for stage in acquisition.get("stages", []):
        index = int(stage["index"])
        if index not in (1, 2, 3) or index in seen_stages:
            raise ValueError(f"Invalid or duplicate offset stage index: {index}")
        seen_stages.add(index)
        job = stage.get("dmm", {})
        if job.get("task_id", task_id) != task_id:
            raise ValueError(f"Stage {index} acquisition task ID differs from {task_id!r}.")
        stage_result = {
            "stage_index": index, "target_c": stage["target_c"],
            "acquisition_status": job.get("status", stage.get("status", "unknown")),
            "valid_reading_count": 0,
            "error": job.get("error", stage.get("error")),
        }
        if stage.get("status") != "completed" or job.get("status") != "completed":
            notes.append(f"Stage {index} acquisition {stage_result['acquisition_status']}; no offset estimate.")
            stages.append(stage_result)
            continue
        if analyzer is None:
            analyzer = legacy_module("analyze_dmm7510_offset.py")
        data_dir = task_dir / "data" / f"stage_{index:02d}"
        result_dir = task_dir / "results" / f"stage_{index:02d}"
        files = analyzer.numbered_tdms_files(data_dir, task_id)
        raw_count += len(files)
        if not files:
            raise FileNotFoundError(f"Completed acquisition stage {index} has no TDMS: {data_dir}")
        original_dir = legacy_dir / "dmm" / f"stage_{index:02d}" / "data" / task_id
        if (legacy_dir / "dmm").exists() and not original_dir.exists():
            raise FileNotFoundError(f"Stage {index} original acquisition TDMS evidence is missing: {original_dir}")
        if original_dir.exists():
            for _, source in files:
                original = original_dir / source.name
                if not original.exists() or file_sha256(source) != file_sha256(original):
                    raise ValueError(f"Stage {index} raw TDMS differs from original acquisition evidence: {source}")
        for _, source in files:
            verify_manifest_hash(task_dir, task, source)
        analyzer.main(["--task-id", task_id, "--input-directory", str(data_dir),
                       "--result-directory", str(result_dir)])
        data = read_json(result_dir / f"{task_id}_dcv_offset_summary.json")
        count = int(data["total_reading_count"])
        expected = job.get("requested_readings")
        if expected is not None and count != int(expected):
            notes.append(f"Stage {index}: {count} valid readings, {expected} requested.")
        temperature_summary = matched_temperature(stage, temperatures)
        if not temperature_summary["temperature_sample_count"]:
            notes.append(f"Stage {index}: no product-temperature samples in the DMM window.")
        points.append({
            "task_id": task_id, "stage_index": index, "target_c": stage["target_c"],
            "reading_count": count,
            "gain": data["configuration"]["closed_loop_gain_v_per_v"],
            "output_mean_v": data["output_voltage_v"]["mean"],
            "input_offset_mean_v": data["equivalent_input_offset_v"]["mean"],
            "input_offset_sample_std_v": data["equivalent_input_offset_v"]["sample_std"],
            **temperature_summary,
        })
        stage_result["valid_reading_count"] = count
        stage_result["summary_file"] = f"results/stage_{index:02d}/{task_id}_dcv_offset_summary.json"
        stages.append(stage_result)
    sequence_completed = bool(acquisition.get("sequence_completed", False))
    completed = sequence_completed and len(points) == 3 and not notes
    slope = None
    if len(points) == 3:
        xs = [point["target_c"] for point in points]
        ys = [point["input_offset_mean_v"] for point in points]
        xm, ym = statistics.mean(xs), statistics.mean(ys)
        denominator = sum((x - xm) ** 2 for x in xs)
        if denominator <= 0:
            raise ValueError("Offset temperature setpoints must differ.")
        slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denominator
    acquisition_status = task.get("acquisition_status", acquisition.get("status", "unknown"))
    data_status = ("complete" if completed else "failed" if not points and
                   acquisition_status in INCOMPLETE_ACQUISITION_STATES else "incomplete")
    if acquisition_status in INCOMPLETE_ACQUISITION_STATES and points:
        report_status_note = "Acquisition did not complete; estimates cover saved stages only."
        if report_status_note not in notes:
            notes.append(report_status_note)
        data_status = "incomplete"
    report = {
        "format_version": 1, "task_id": task_id,
        "acquisition_status": acquisition_status,
        "data_status": data_status,
        "sequence_completed": sequence_completed,
        "stop_confirmed": bool(acquisition.get("stop_confirmed", False)),
        "valid_reading_count": sum(point["reading_count"] for point in points),
        "points": points, "stages": stages,
        "temperature_window": "Thermal samples between the first and last DMM query-midpoint timestamps; no gap interpolation.",
        "drift_note": "The three-point slope uses nominal setpoints. It is a descriptive linear fit, not a device specification or uncertainty budget.",
        "nominal_temperature_linear_slope_v_per_c": slope,
        "legacy_run_path": legacy_dir.relative_to(task_dir).as_posix(),
        "notes": notes,
    }
    output_dir = task_dir / "results"
    write_json(output_dir / "offset_drift_summary.json", report)
    if points:
        write_csv(output_dir / "offset_vs_temperature.csv", list(points[0]), points)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots(figsize=(8, 5))
        axis.errorbar([point["target_c"] for point in points],
                      [point["input_offset_mean_v"] * 1e6 for point in points],
                      yerr=[point["input_offset_sample_std_v"] * 1e6 for point in points],
                      fmt="o-", capsize=5, color="#2563eb", label="Mean +/- sample standard deviation")
        axis.set_xticks([-40, 27, 125])
        axis.set_xlabel("Nominal product temperature target (C)")
        axis.set_ylabel("Input-referred offset (uV)")
        axis.set_title(f"Offset vs temperature: {len(points)}/3 points")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
        figure.tight_layout()
        path = output_dir / "offset_vs_temperature.png"
        partial = path.with_name(path.stem + ".partial.png")
        figure.savefig(partial, dpi=170)
        partial.replace(path)
        plt.close(figure)
    return {
        "task_id": task_id, "measurement_type": "offset_drift", "chip": task.get("chip"),
        "acquisition_status": report["acquisition_status"], "data_status": report["data_status"],
        "processing_status": "completed", "raw_file_count": raw_count,
        "valid_reading_count": report["valid_reading_count"], "offset_stage_count": len(points),
        "nominal_temperature_linear_slope_uv_per_c": slope * 1e6 if slope is not None else None,
        "summary_file": "results/offset_drift_summary.json", "notes": notes,
    }


def process_dcv_offset(task_dir: Path, task: dict) -> dict:
    analyzer = legacy_module("analyze_dmm7510_offset.py")
    task_id = task["task_id"]
    files = analyzer.numbered_tdms_files(task_dir / "data", task_id)
    acquisition_status = task.get("acquisition_status", "unknown")
    status = {
        "task_id": task_id, "measurement_type": "dcv_offset", "chip": task.get("chip"),
        "acquisition_status": acquisition_status, "processing_status": "completed",
        "raw_file_count": len(files), "valid_reading_count": 0,
        "input_offset_mean_uv": None, "input_offset_sample_std_uv": None, "notes": [],
    }
    if not files:
        if acquisition_status not in INCOMPLETE_ACQUISITION_STATES:
            raise FileNotFoundError(f"No standalone DMM TDMS records in {task_dir / 'data'}")
        status["data_status"] = "failed"
        status["notes"] = ["Acquisition failed; no valid TDMS records and no offset estimate."]
        return status
    for _, source in files:
        verify_manifest_hash(task_dir, task, source)
    analyzer.main(["--task-id", task_id, "--task-dir", str(task_dir)])
    summary_file = f"results/{task_id}_dcv_offset_summary.json"
    summary = read_json(task_dir / summary_file)
    status.update(valid_reading_count=summary["total_reading_count"],
                  input_offset_mean_uv=summary["equivalent_input_offset_v"]["mean"] * 1e6,
                  input_offset_sample_std_uv=summary["equivalent_input_offset_v"]["sample_std"] * 1e6,
                  summary_file=summary_file, data_status="complete")
    runs = [run for run, _ in files]
    expected = int(task.get("expected_run_count", len(files)))
    if runs != list(range(1, expected + 1)):
        status["data_status"] = "incomplete"
        status["notes"].append(f"DMM runs differ from expected 1..{expected}.")
    if acquisition_status in INCOMPLETE_ACQUISITION_STATES:
        status["data_status"] = "incomplete"
        status["notes"].append("Acquisition did not complete; estimates cover saved records only.")
    return status


def process_task(task_dir: Path, *, recompute_spectra: bool = False,
                 nperseg: int = 262_144) -> dict:
    task_dir = task_dir.expanduser().resolve()
    if (task_dir / ".acquisition.lock").exists():
        raise AcquisitionInProgressError(f"Acquisition lock exists; task files left untouched: {task_dir}")
    task = load_task(task_dir)
    if acquisition_in_progress(task_dir, task):
        raise AcquisitionInProgressError(f"Acquisition is still running; task files left untouched: {task_dir}")
    if task["measurement_type"] == "noise":
        status = process_noise(task_dir, task, recompute_spectra=recompute_spectra, nperseg=nperseg)
    elif task["measurement_type"] == "offset_drift":
        status = process_offset_drift(task_dir, task)
    else:
        status = process_dcv_offset(task_dir, task)
    status["task_directory"] = task_dir.name
    status["processed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(task_dir / "results" / "processing_status.json", status)
    return status


def write_overview(tasks_root: Path, overview_dir: Path) -> dict:
    """Include every retained manifest, including tasks not replayed in this call."""
    rows = []
    for manifest in sorted(tasks_root.glob("*/task.json")):
        task_dir = manifest.parent
        try:
            task = load_task(task_dir)
            manifest_error = None
        except (ValueError, OSError) as exc:
            task = {"task_id": task_dir.name, "measurement_type": None}
            manifest_error = str(exc)
        status_path = task_dir / "results" / "processing_status.json"
        row = {"task_id": task["task_id"], "measurement_type": task["measurement_type"],
               "chip": task.get("chip"), "acquisition_status": task.get("acquisition_status", "unknown"),
               "processing_status": "not_processed", "data_status": "not_checked",
               "task_directory": task_dir.name}
        if manifest_error is not None:
            row.update(processing_status="failed", data_status="error", notes=[manifest_error])
        elif acquisition_in_progress(task_dir, task):
            row.update(acquisition_status="acquiring", processing_status="waiting", data_status="not_checked",
                       notes=["Acquisition is in progress; task files left untouched."])
        elif status_path.exists():
            row.update(read_json(status_path))
        rows.append(row)
    overview = {"format_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "task_count": len(rows), "tasks": rows}
    write_json(overview_dir / "task_overview.json", overview)
    csv_rows = [dict(row, notes="; ".join(row.get("notes", []))) for row in rows]
    write_csv(overview_dir / "task_overview.csv", list(OVERVIEW_COLUMNS), csv_rows)
    return overview


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--task-id", type=task_id_value, help="Process one task directory.")
    selection.add_argument("--all", action="store_true", help="Process every task.json under --tasks-root.")
    parser.add_argument("--tasks-root", "--tasks-dir", type=Path, default=PROJECT_ROOT / "tasks")
    parser.add_argument("--overview-dir", type=Path,
                        help="Shared CSV/JSON overview directory (default: sibling results/).")
    parser.add_argument("--recompute-spectra", action="store_true",
                        help="Recalculate noise spectra from TDMS; default: reuse NPZ, calculate missing NPZ.")
    parser.add_argument("--nperseg", type=positive_int, default=262_144,
                        help="Welch segment size for newly calculated spectra (default: 262144).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tasks_root = args.tasks_root.expanduser().resolve()
    overview_dir = args.overview_dir.expanduser().resolve() if args.overview_dir else tasks_root.parent / "results"
    directories = ([tasks_root / args.task_id] if args.task_id else
                   [path.parent for path in sorted(tasks_root.glob("*/task.json"))])
    if not directories:
        print(f"ERROR: No task.json files in {tasks_root}", file=sys.stderr)
        return 1
    failed = False
    for task_dir in directories:
        try:
            status = process_task(task_dir, recompute_spectra=args.recompute_spectra, nperseg=args.nperseg)
            print(f"{task_dir.name}: acquisition={status['acquisition_status']}, data={status['data_status']}")
            failed |= status["data_status"] == "incomplete"
        except AcquisitionInProgressError as exc:
            failed = True
            print(f"WAITING: {task_dir.name}: {exc}", file=sys.stderr)
        except Exception as exc:
            failed = True
            print(f"ERROR: {task_dir.name}: {exc}", file=sys.stderr)
            if task_dir.is_dir():
                try:
                    task = read_json(task_dir / "task.json") if (task_dir / "task.json").exists() else {}
                except (ValueError, OSError):
                    task = {}
                write_json(task_dir / "results" / "processing_status.json", {
                    "task_id": task_dir.name, "measurement_type": task.get("measurement_type"),
                    "chip": task.get("chip"), "acquisition_status": task.get("acquisition_status", "unknown"),
                    "data_status": "error", "processing_status": "failed", "notes": [str(exc)],
                })
    try:
        write_overview(tasks_root, overview_dir)
    except Exception as exc:
        print(f"ERROR writing overview: {exc}", file=sys.stderr)
        return 1
    print(f"Overview: {overview_dir / 'task_overview.csv'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
