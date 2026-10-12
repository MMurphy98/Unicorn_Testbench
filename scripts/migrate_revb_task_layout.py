#!/usr/bin/env python3
"""Migrate the selected RevB records into portable task directories.

The default is a read-only plan. --apply moves retained records, preserving a
SHA-256 manifest. --remove-excluded separately opts into the explicit deletion
list agreed for the 2026-10-12 cleanup. No instrument modules are imported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "Unicorn_CSA_RevB-COB"
NOISE_TASKS = [
    "RevB_Chip_1_wiShield_Gmx_1p2_OSC_default_Vsup_pm6V",
    "RevB_Chip_1_wiShield_Gmx_4b1111_OSC_default_Vsup_pm6V",
    "RevB_Chip_1_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
    "RevB_Chip_1_wiShield_Gmx_max_OSC_default_Vsup_pm6V",
    "RevB_Chip_2_wiShield_Gmx_4b1001_OSC_default_Vsup_pm6V",
    "RevB_Chip_2_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
    "RevB_Chip_2_wiShield_Gmx_max_OSC_default_Vsup_pm6V",
    "RevB_Chip_3_wiShield_Gmx_default_OSC_default_Vsup_pm12V",
    "RevB_Chip_3_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
    "RevB_Chip_3_wiShield_Gmx_max_OSC_default_Vsup_pm12V",
    "RevB_Chip_3_wiShield_Gmx_max_OSC_default_Vsup_pm6V",
    "RevB_Chip_4_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
    "RevB_Chip_5_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_if_missing(source, destination):
    if not destination.exists():
        shutil.copy2(source, destination)


def planned_moves():
    moves = []
    for task in NOISE_TASKS:
        for category in ("data", "spectra", "results"):
            moves.append((PROJECT / category / task, PROJECT / "tasks" / task / category))
    for chip in (1, 2, 3):
        moves.append((ROOT / "results/offset_drift" / f"chip{chip}_gain1001_20260918_run01",
                      PROJECT / "tasks" / f"Offset_Chip_{chip}_Gain1001_20260918" / "provenance/legacy_run"))
    for category in ("data", "results"):
        moves.append((PROJECT / category / "demo", PROJECT / "demo" / category))
    for name in ("chip1_vs_chip3_20260918_run01", "chip1_chip3_dmm_combined_20260919_run01"):
        moves.append((ROOT / "results/offset_drift" / name, PROJECT / "comparisons/offset_drift_20260918" / name))
    return moves


def excluded_paths():
    # This explicit set never selects newly acquired tasks by wildcard.
    old_offset = [
        "DMM7510_short_100mV_10NPLC_drfit",
        "Offset_RevB_Chip_1_woShield_Gmx_default_OSC_default_Vsup_pm6V_night_Gain101",
        "Offset_RevB_Chip_5_wiShield_Gmx_default_OSC_default_Vsup_pm6V",
        "Offset_RevB_Chip_5_wiShield_Gmx_default_OSC_default_Vsup_pm6V_night",
        "Offset_RevB_Chip_5_wiShield_Gmx_default_OSC_default_Vsup_pm6V_night_Gain1001",
        "Offset_RevB_Chip_5_woShield_Gmx_default_OSC_default_Vsup_pm6V_night",
    ] + [f"Offset_RevB_Chip_{chip}_wiShield_Gmx_default_OSC_default_Vsup_pm6V_20260909" for chip in range(1, 6)]
    return ([PROJECT / category / task for task in old_offset for category in ("data", "results")]
            + [ROOT / "results/offset_drift", ROOT / "results/thermal_stream",
               ROOT / "docs/test-reports/2026/09/2026-09-09-T-20260909-01.md",
               ROOT / "docs/test-reports/2026/09/2026-09-13-T-20260911-01.md",
               ROOT / "docs/test-reports/2026/09/2026-09-14-T-20260911-01.md"])


def task_metadata(task, measurement_type, chip, status):
    return {"schema_version": 1, "task_id": task, "measurement_type": measurement_type,
            "chip": chip, "acquisition_status": status, "layout_version": 1,
            "data_directory": "data", "spectra_directory": "spectra", "results_directory": "results"}


def apply_migration(remove_excluded):
    moves = planned_moves()
    # Detect conflicting destinations before any mutation; a rerun skips complete moves.
    for source, destination in moves:
        if source.exists() and destination.exists():
            raise FileExistsError(f"Both migration source and destination exist: {source} -> {destination}")
    manifest_path = PROJECT / "migration_20261012.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {"schema_version": 1, "moves": [], "removed": []})
    for source, destination in moves:
        if not source.exists():
            if not destination.exists() and source.name != "demo":
                raise FileNotFoundError(source)
            continue
        files = [{"source": str(p.relative_to(ROOT)),
                  "destination": str((destination / p.relative_to(source)).relative_to(ROOT)),
                  "bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in sorted(source.rglob("*")) if p.is_file()]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        manifest["moves"].extend(files)
        write_json(manifest_path, manifest)
        print(f"Moved {source.relative_to(ROOT)} ({len(files)} files)", flush=True)

    for task in NOISE_TASKS:
        directory = PROJECT / "tasks" / task
        chip = int(task.split("_Chip_")[1].split("_")[0])
        meta = task_metadata(task, "noise", chip, "completed")
        meta.update(expected_runs=100, expected_run_count=100, gain_v_per_v=1001.0,
                    sample_rate_hz=50000.0, sample_count_each=1100000)
        if not (directory / "task.json").exists():
            write_json(directory / "task.json", meta)
    for chip in (1, 2, 3):
        task = f"Offset_Chip_{chip}_Gain1001_20260918"
        directory = PROJECT / "tasks" / task
        legacy = directory / "provenance/legacy_run"
        meta = task_metadata(task, "offset_drift", chip, "failed" if chip == 2 else "completed")
        meta.update(legacy_run_path="provenance/legacy_run", gain_v_per_v=1001.0,
                    target_temperatures_c=[-40, 27, 125], expected_readings_each=1000,
                    actual_reading_count=0 if chip == 2 else 3000,
                    test_date="2026-09-18", retention_note="Retain failed first-stage evidence" if chip == 2 else "")
        for category in ("data", "spectra", "results", "logs"):
            (directory / category).mkdir(exist_ok=True)
        for stage in sorted((legacy / "dmm").glob("stage_*")):
            data = directory / "data" / stage.name
            data.mkdir(exist_ok=True)
            for path in (stage / "data").glob("*/*.tdms"):
                copy_if_missing(path, data / path.name)
            if (stage / "partial_readings.csv").is_file():
                copy_if_missing(stage / "partial_readings.csv", data / "partial_readings.csv")
            result = directory / "results" / stage.name
            for path in (stage / "results").glob("*/*"):
                if path.is_file():
                    result.mkdir(exist_ok=True)
                    copy_if_missing(path, result / path.name)
            if (stage / "worker.log").is_file():
                copy_if_missing(stage / "worker.log", directory / "logs" / f"{stage.name}_worker.log")
        copy_if_missing(legacy / "temperature.csv", directory / "data/temperature.csv")
        for name in ("offset_drift_summary.json", "offset_vs_temperature.csv", "offset_vs_temperature.png", "temperature_curve.png"):
            if (legacy / name).is_file():
                copy_if_missing(legacy / name, directory / "results" / name)
        for path in legacy.glob("*.jsonl"):
            copy_if_missing(path, directory / "logs" / path.name)
        for suffix in (".json", "_wire.jsonl"):
            preflight = ROOT / "results/offset_drift" / f"chip{chip}_gain1001_20260918_run01_preflight{suffix}"
            if preflight.is_file():
                copy_if_missing(preflight, legacy / f"external_preflight{suffix}")
        if not (directory / "task.json").exists():
            write_json(directory / "task.json", meta)

    if remove_excluded:
        snapshot = ROOT / "legacy/source_snapshot_20261012/source_sha256.json"
        if not snapshot.is_file():
            raise RuntimeError("Preserve the original source snapshot before deleting excluded records")
        for path in excluded_paths():
            if not path.exists(): continue
            manifest["removed"].append({"path": str(path.relative_to(ROOT)),
                                        "files": sum(p.is_file() for p in path.rglob("*")) if path.is_dir() else 1})
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
        # Empty legacy namespace folders are removed; no unknown content is deleted.
        for path in (PROJECT / "data/DUT_RevB_with_PMU", PROJECT / "data", PROJECT / "spectra"):
            if path.is_dir() and not any(path.iterdir()): path.rmdir()
        write_json(manifest_path, manifest)
    print(f"Migration manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove-excluded", action="store_true")
    args = parser.parse_args()
    if args.remove_excluded and not args.apply:
        parser.error("--remove-excluded requires --apply")
    if args.apply:
        apply_migration(args.remove_excluded)
    else:
        print(json.dumps({"moves": [{"source": str(a.relative_to(ROOT)), "destination": str(b.relative_to(ROOT))}
                                     for a, b in planned_moves()],
                          "excluded_if_requested": [str(p.relative_to(ROOT)) for p in excluded_paths()]}, indent=2))


if __name__ == "__main__":
    main()
