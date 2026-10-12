"""Offline contracts for field orchestration; no instrument modules are imported."""
import argparse
import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import _common
import capture_noise
import capture_offset
import run_noise_pipeline
import run_offset_drift


class FieldContracts(unittest.TestCase):
    def test_noise_command_passes_parent_task_and_preserves_options(self):
        with tempfile.TemporaryDirectory() as folder:
            args = capture_noise.build_parser().parse_args([
                "--task-id", "Noise_Chip_3", "--tasks-root", folder, "--runs", "7",
                "--sample-rate", "40000", "--samples", "880000", "--gain", "101"])
            command = capture_noise.capture_command(args)
            self.assertEqual(command[command.index("--task-dir") + 1], str(Path(folder).resolve() / "Noise_Chip_3"))
            self.assertNotIn("--output-dir", command)
            self.assertEqual(command[command.index("--runs") + 1], "7")
            self.assertEqual(command[command.index("--gain") + 1], "101.0")
            self.assertEqual(command[command.index("--samples") + 1], "880000")

    def test_dmm_command_keeps_explicit_visa_resource_and_range(self):
        args = capture_offset.build_parser().parse_args([
            "--task-id", "Offset_Chip_1", "--resource", "USB0::DMM::INSTR", "--range", "1", "--readings", "1000"])
        command = capture_offset.capture_command(args)
        self.assertEqual(command[command.index("--resource") + 1], "USB0::DMM::INSTR")
        self.assertEqual(command[command.index("--range") + 1], "1.0")
        self.assertEqual(command[command.index("--readings") + 1], "1000")

    def test_forwarded_commands_are_accepted_by_preserved_capture_parsers(self):
        # Load only the real argument parser/validators from each source file.
        # No instrument import or I/O is needed to test this command boundary.
        for wrapper, filename in ((capture_noise, "capture_dut_revb_pmu_noise.py"),
                                  (capture_offset, "capture_dmm7510_offset.py")):
            with self.subTest(filename=filename):
                source = _common.BOARD_DIR / filename
                tree = ast.parse(source.read_text())
                names = {"parse_args", "positive_int", "positive_float", "task_id_value",
                         "at_least_two_int", "nonnegative_int", "nonnegative_float", "input_impedance_value"}
                parser_code = ast.Module(body=[node for node in tree.body
                                              if (isinstance(node, ast.ImportFrom) and node.module == "__future__")
                                              or (isinstance(node, ast.FunctionDef) and node.name in names)], type_ignores=[])
                namespace = {"argparse": argparse, "Path": Path, "re": re,
                             "np": SimpleNamespace(isfinite=math.isfinite), "DEFAULT_TASK_ID": "default",
                             "__file__": str(source)}
                exec(compile(parser_code, str(source), "exec"), namespace)
                args = wrapper.build_parser().parse_args(["--task-id", "New_Chip_1"])
                forwarded = namespace["parse_args"](wrapper.capture_command(args)[3:])
                self.assertEqual(forwarded.task_id, "New_Chip_1")
                self.assertEqual(forwarded.task_dir, _common.task_path(args))

    def test_all_dry_runs_work_without_hardware_and_leave_no_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("capture_noise.py", "capture_offset.py", "run_noise_pipeline.py", "run_offset_drift.py"):
                with self.subTest(entrypoint=name):
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name(name)),
                                             "--task-id", "Fresh_Chip_1", "--tasks-root", folder, "--dry-run"],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("Fresh_Chip_1", result.stdout)
                    self.assertEqual(list(Path(folder).iterdir()), [])

    def test_offline_pipeline_can_use_a_separate_interpreter(self):
        args = run_noise_pipeline.build_parser().parse_args([
            "--task-id", "Noise_Chip_2", "--process-existing-only", "--postprocess-python", "analysis-python"])
        command = run_noise_pipeline.processing_command(args)
        self.assertEqual(command[0], "analysis-python")
        self.assertIn("process_tasks.py", command[2])
        self.assertNotIn("capture_dut_revb_pmu_noise.py", " ".join(command))

    def test_failed_acquisition_keeps_existing_metadata_and_source_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            task.mkdir()
            (task / "task.json").write_text(json.dumps({"task_id": task.name, "measurement_type": "noise", "chip": 1, "notes": "retain"}))
            with _common.acquisition_record(task, measurement_type="noise", chip=1,
                                            commands=[["fake-capture"]], sources=[Path(__file__)], run_id="test_run") as (record, _, _):
                record["exit_code"] = 1
                (task / "data" / "Noise_Chip_1_0001.partial.tdms").write_bytes(b"interrupted evidence")
            manifest = json.loads((task / "task.json").read_text())
            provenance = json.loads((task / "provenance" / "test_run" / "acquisition.json").read_text())
            self.assertEqual(manifest["notes"], "retain")
            self.assertEqual(manifest["acquisition_status"], "failed")
            self.assertEqual(provenance["completed_tdms_files"], 0)
            self.assertEqual(len(provenance["source_sha256"]), 1)
            self.assertFalse((task / ".acquisition.lock").exists())

    def test_exceptions_mark_acquisition_failed_and_release_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            with self.assertRaisesRegex(RuntimeError, "capture failed"):
                with _common.acquisition_record(task, measurement_type="noise", chip=None,
                                                commands=[], sources=[], run_id="test_error"):
                    raise RuntimeError("capture failed")
            manifest = json.loads((task / "task.json").read_text())
            self.assertEqual(manifest["acquisition_status"], "failed")
            self.assertFalse((task / ".acquisition.lock").exists())

    def test_thermal_publish_preserves_failed_stage_and_legacy_handshake(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Offset_Chip_2"
            legacy = task / "provenance" / "test_run" / "legacy_run"
            stage = legacy / "dmm" / "stage_01"
            stage.mkdir(parents=True)
            done = {"status": "failed", "completed_readings": 0, "error": "overrange"}
            (stage / "dmm_done.json").write_text(json.dumps(done))
            (stage / "partial_readings.csv").write_text("reading_index,output_voltage_v\n")
            (legacy / "temperature.csv").write_text("timestamp_utc,product_temperature_c\n")
            (legacy / "summary.json").write_text('{"sequence_completed": false}')
            index = run_offset_drift.publish_thermal_run(task, legacy)
            self.assertTrue((task / "data" / "stage_01" / "partial_readings.csv").exists())
            self.assertFalse(list((task / "data").rglob("*.tdms")))
            self.assertEqual(json.loads((task / "logs" / "stage_01" / "dmm_done.json").read_text()), done)
            self.assertEqual(json.loads((stage / "dmm_done.json").read_text()), done)
            self.assertEqual(len(index), 4)

    def test_raw_hashes_cover_completed_files_and_reuse_unchanged_digests(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            raw_name = "Noise_Chip_1_0001.tdms"
            relative = "data/" + raw_name
            with _common.acquisition_record(task, measurement_type="noise", chip=1,
                                            commands=[], sources=[], run_id="first_run"):
                (task / "data" / raw_name).write_bytes(b"verified raw")
                (task / "data" / "Noise_Chip_1_0002.partial.tdms").write_bytes(b"incomplete")
            manifest = json.loads((task / "task.json").read_text())
            self.assertEqual(manifest["raw_file_sha256"], {relative: hashlib.sha256(b"verified raw").hexdigest()})
            # Hashing is not repeated when size and modification time match.
            with patch.object(_common.hashlib, "sha256", side_effect=AssertionError("unnecessary rehash")):
                _common.update_raw_file_hashes(task, manifest)
            (task / "data" / raw_name).write_bytes(b"changed verified raw")
            with self.assertRaisesRegex(RuntimeError, "no longer matches"):
                _common.update_raw_file_hashes(task, manifest)
            self.assertEqual(manifest["raw_file_sha256"][relative], hashlib.sha256(b"verified raw").hexdigest())
            (task / "data" / raw_name).write_bytes(b"verified raw")
            _common.update_raw_file_hashes(task, manifest)
            atomic_saved = manifest["raw_file_sha256"][relative]
            with _common.acquisition_record(task, measurement_type="noise", chip=1,
                                            commands=[], sources=[], run_id="second_run"):
                (task / "data" / "Noise_Chip_1_0003.tdms").write_bytes(b"next complete raw")
            saved = json.loads((task / "task.json").read_text())
            self.assertEqual(saved["raw_file_sha256"][relative], atomic_saved)
            self.assertEqual(len(saved["raw_file_sha256"]), 2)

    def test_thermal_raw_data_is_flat_within_each_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Offset_Chip_1"
            legacy = task / "provenance" / "test_run" / "legacy_run"
            raw = legacy / "dmm" / "stage_01" / "data" / task.name
            raw.mkdir(parents=True)
            name = f"{task.name}_dcv_0001.tdms"
            (raw / name).write_bytes(b"verified raw fixture")
            run_offset_drift.publish_thermal_run(task, legacy)
            self.assertEqual((task / "data" / "stage_01" / name).read_bytes(), b"verified raw fixture")
            self.assertFalse((task / "data" / "stage_01" / task.name).exists())
            self.assertEqual((raw / name).read_bytes(), b"verified raw fixture")

    def test_changed_raw_finalization_fails_retains_new_data_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            original = "Noise_Chip_1_0001.tdms"
            added = "Noise_Chip_1_0002.tdms"
            with _common.acquisition_record(task, measurement_type="noise", chip=None,
                                            commands=[], sources=[], run_id="first_run"):
                (task / "data" / original).write_bytes(b"original verified raw")
            with self.assertRaisesRegex(RuntimeError, "no longer matches"):
                with _common.acquisition_record(task, measurement_type="noise", chip=None,
                                                commands=[], sources=[], run_id="second_run"):
                    (task / "data" / original).write_bytes(b"changed existing raw")
                    (task / "data" / added).write_bytes(b"newly acquired raw")
            manifest = json.loads((task / "task.json").read_text())
            record = json.loads((task / "provenance" / "second_run" / "acquisition.json").read_text())
            self.assertEqual(manifest["acquisition_status"], "failed")
            self.assertEqual(record["acquisition_status"], "failed")
            self.assertIn("no longer matches", record["raw_hash_error"])
            self.assertEqual(manifest["raw_file_sha256"]["data/" + original], hashlib.sha256(b"original verified raw").hexdigest())
            self.assertEqual(manifest["raw_file_sha256"]["data/" + added], hashlib.sha256(b"newly acquired raw").hexdigest())
            self.assertEqual((task / "data" / added).read_bytes(), b"newly acquired raw")
            self.assertFalse((task / ".acquisition.lock").exists())

    def test_partial_tdms_not_counted_as_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            (task / "data").mkdir(parents=True)
            for name in ("Noise_Chip_1_0001.tdms", "Noise_Chip_1_0002.partial.tdms", "unrelated.tdms"):
                (task / "data" / name).write_bytes(b"")
            self.assertEqual(capture_noise.completed_count(task, task.name), 1)

    def test_changed_capture_conditions_rejected_before_hardware_or_manifest_edits(self):
        for wrapper, flag, key in ((capture_noise, "--vertical-range", "vertical_range"),
                                   (capture_offset, "--range", "range_v")):
            with self.subTest(wrapper=wrapper.__name__), tempfile.TemporaryDirectory() as folder:
                task = Path(folder) / "Existing_Chip_1"
                (task / "data").mkdir(parents=True)
                (task / "data" / "existing.tdms").write_bytes(b"existing raw")
                old_args = wrapper.build_parser().parse_args(["--task-id", task.name, "--tasks-root", folder])
                config = {name: getattr(old_args, name) for name in wrapper.CONFIGURATION_KEYS}
                original = json.dumps({"task_id": task.name, "acquisition_configuration": config})
                (task / "task.json").write_text(original)
                changed = str(config[key] * 2)
                with patch.object(wrapper, "require_windows", side_effect=AssertionError("hardware gate called")):
                    with self.assertRaisesRegex(ValueError, "different acquisition conditions"):
                        wrapper.main(["--task-id", task.name, "--tasks-root", folder, flag, changed])
                self.assertEqual((task / "task.json").read_text(), original)
                self.assertFalse((task / "provenance").exists())

    def test_unknown_migrated_conditions_are_rejected_even_in_dry_run(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Migrated_Chip_1"
            (task / "data").mkdir(parents=True)
            (task / "data" / "existing.tdms").write_bytes(b"migrated raw")
            for wrapper in (capture_noise, capture_offset, run_noise_pipeline):
                with self.subTest(wrapper=wrapper.__name__), self.assertRaisesRegex(ValueError, "unknown acquisition conditions"):
                    wrapper.main(["--task-id", task.name, "--tasks-root", folder, "--dry-run"])
            self.assertFalse((task / "task.json").exists())

    def test_identical_noise_conditions_resume_with_different_runs_and_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "Noise_Chip_1"
            (task / "data").mkdir(parents=True)
            (task / "data" / "Noise_Chip_1_0001.tdms").write_bytes(b"previous raw")
            args = capture_noise.build_parser().parse_args([
                "--task-id", task.name, "--tasks-root", folder, "--runs", "1", "--timeout", "80"])
            previous = {name: getattr(args, name) for name in capture_noise.CONFIGURATION_KEYS}
            previous.update(runs=100, timeout=40.0)
            (task / "task.json").write_text(json.dumps({"task_id": task.name, "measurement_type": "noise",
                                                        "acquisition_configuration": previous}))

            def fake_capture(command, log):
                (task / "data" / "Noise_Chip_1_0002.tdms").write_bytes(b"new raw")
                return 0

            with patch.object(capture_noise, "require_windows"), patch.object(capture_noise, "run_logged", side_effect=fake_capture), redirect_stdout(io.StringIO()):
                self.assertEqual(capture_noise.capture(args), 0)
            manifest = json.loads((task / "task.json").read_text())
            self.assertEqual(manifest["acquisition_status"], "completed")
            self.assertEqual(manifest["expected_run_count"], 2)
            self.assertEqual(len(manifest["raw_file_sha256"]), 2)

    def test_windows_reserved_task_ids_rejected(self):
        for value in ("CON", "com1.log", "trailing.", "../escape"):
            with self.subTest(value=value), self.assertRaises(Exception):
                _common.task_id_value(value)


if __name__ == "__main__":
    unittest.main()
