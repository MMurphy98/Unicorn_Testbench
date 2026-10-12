"""Regression checks for direct task paths, numerical parity, and failed runs."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
from nptdms import ChannelObject, GroupObject, RootObject, TdmsWriter

import process_tasks as replay


def noise_tdms(path: Path, task_id: str, run: int) -> None:
    rng = np.random.default_rng(run)
    samples = rng.normal(scale=.003, size=4096).astype(np.float64)
    root = RootObject(properties={
        "task_id": task_id, "run_number": run, "tdms_group_name": "Noise",
        "tdms_channel_name": "Voltage", "closed_loop_gain_v_per_v": 1001.,
        "estimated_closed_loop_bandwidth_hz": 500.,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with TdmsWriter(path) as writer:
        writer.write_segment([root, GroupObject("Noise"), ChannelObject(
            "Noise", "Voltage", samples, properties={"wf_increment": 1 / 4096.})])


def offset_tdms(path: Path, task_id: str, values: np.ndarray) -> None:
    properties = {
        "format_version": 1, "measurement_type": "dcv_offset", "task_id": task_id,
        "run_number": 1, "tdms_group_name": "DMM", "dcv_channel_name": "DCV",
        "elapsed_time_channel_name": "ElapsedTime", "reading_count": values.size,
        "closed_loop_gain_v_per_v": 1001., "instrument_manufacturer": "Keithley",
        "instrument_model": "DMM7510", "instrument_serial_number": "fixture",
        "instrument_firmware_revision": "fixture", "terminals": "FRONT",
        "measurement_function": "DCV", "actual_range_v": .1, "autorange_enabled": False,
        "actual_input_impedance_mode": "AUTO", "actual_nplc": 10., "autozero_enabled": True,
        "dmm_averaging_enabled": False, "relative_enabled": False, "line_sync_enabled": True,
        "line_frequency_hz": 50., "acquisition_start_utc": datetime(2026, 9, 18, tzinfo=timezone.utc),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with TdmsWriter(path) as writer:
        writer.write_segment([RootObject(properties=properties), GroupObject("DMM"),
                              ChannelObject("DMM", "DCV", np.asarray(values, dtype=np.float64)),
                              ChannelObject("DMM", "ElapsedTime", np.arange(1, values.size + 1, dtype=np.float64))])


def assert_summary_equal(test: unittest.TestCase, actual: dict, expected: dict) -> None:
    for key in ("spectrum_file_count", "welch_nperseg", "total_welch_segments",
                "frequency_resolution_hz", "targets", "target_distributions"):
        test.assertEqual(actual[key], expected[key], key)


class ReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="unicorn-offline-test-")
        self.root = Path(self.temporary.name)
        self.tasks = self.root / "tasks"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def task(self, task_id: str, measurement: str, status: str = "completed", chip: int = 1) -> Path:
        directory = self.tasks / task_id
        replay.write_json(directory / "task.json", {
            "task_id": task_id, "measurement_type": measurement, "chip": chip,
            "acquisition_status": status, "expected_run_count": 2,
            "legacy_run_path": "provenance/legacy_run",
        })
        return directory

    def test_noise_direct_layout_and_exact_legacy_summary_parity(self) -> None:
        directory = self.task("NoiseFixture", "noise")
        for run in (1, 2):
            noise_tdms(directory / "data" / f"NoiseFixture_{run:04d}.tdms", "NoiseFixture", run)
        with redirect_stdout(io.StringIO()):
            status = replay.process_task(directory, nperseg=512)
        self.assertEqual(status["data_status"], "complete")
        self.assertEqual(status["spectra_created"], 2)
        self.assertFalse((directory / "results" / "NoiseFixture").exists())
        self.assertFalse((directory / "spectra" / "NoiseFixture").exists())
        canonical_summary = replay.read_json(directory / "results" / "NoiseFixture_noise_summary.json")
        # Run the original CLI against its original base/task-ID layout as a reference.
        legacy_root = self.root / "legacy"
        shutil.copytree(directory / "data", legacy_root / "data" / "NoiseFixture")
        analyzer = replay.legacy_module("analyze_dut_revb_pmu_noise.py")
        plotter = replay.legacy_module("plot_dut_revb_pmu_noise.py")
        with redirect_stdout(io.StringIO()):
            analyzer.main(["--task-id", "NoiseFixture", "--data-dir", str(legacy_root / "data"),
                           "--output-dir", str(legacy_root / "spectra"), "--nperseg", "512"])
            plotter.main(["--task-id", "NoiseFixture", "--spectra-dir", str(legacy_root / "spectra"),
                          "--output-dir", str(legacy_root / "results")])
        original_summary = replay.read_json(legacy_root / "results" / "NoiseFixture" / "NoiseFixture_noise_summary.json")
        assert_summary_equal(self, canonical_summary, original_summary)
        for run in (1, 2):
            name = f"NoiseFixture_{run:04d}_spectrum.npz"
            with np.load(directory / "spectra" / name) as canonical, np.load(legacy_root / "spectra" / "NoiseFixture" / name) as original:
                np.testing.assert_array_equal(canonical["frequency_hz"], original["frequency_hz"])
                np.testing.assert_array_equal(canonical["input_psd_v2_per_hz"], original["input_psd_v2_per_hz"])
        before = {path.name: path.stat().st_mtime_ns for path in (directory / "spectra").glob("*.npz")}
        with redirect_stdout(io.StringIO()):
            reused = replay.process_task(directory, nperseg=1024)
        self.assertEqual(reused["spectra_created"], 0)
        self.assertEqual(before, {path.name: path.stat().st_mtime_ns for path in (directory / "spectra").glob("*.npz")})
        self.assertNotIn("niscope", sys.modules)
        self.assertNotIn("pyvisa", sys.modules)

    def test_noise_missing_run_is_incomplete(self) -> None:
        task = {"expected_run_count": 3}
        self.assertEqual(replay.noise_completeness(task, [(1, None), (3, None)],
                                                   [(1, None), (3, None)])[0], "incomplete")
        self.assertEqual(replay.noise_completeness(task, [(1, None), (2, None), (3, None)],
                                                   [(1, None), (2, None)])[0], "incomplete")

    def test_locked_or_acquiring_noise_leaves_task_outputs_untouched(self) -> None:
        directory = self.task("LockedNoise", "noise")
        (directory / "spectra").mkdir()
        (directory / "spectra/existing_spectrum.npz").write_bytes(b"unchanged cached spectrum")
        replay.write_json(directory / "results/processing_status.json", {
            "task_id": directory.name, "processing_status": "completed", "data_status": "complete"})
        (directory / ".acquisition.lock").write_text("field owns task", encoding="utf-8")
        def snapshot():
            return {str(path.relative_to(directory)): path.read_bytes()
                    for path in directory.rglob("*") if path.is_file()}
        before = snapshot()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main(["--task-id", directory.name, "--tasks-root", str(self.tasks)]), 1)
        self.assertEqual(snapshot(), before)
        overview = replay.read_json(self.root / "results/task_overview.json")
        self.assertEqual(overview["tasks"][0]["processing_status"], "waiting")
        self.assertEqual(overview["tasks"][0]["acquisition_status"], "acquiring")
        # Also block active status even if a copied task lacks the lock file.
        (directory / ".acquisition.lock").unlink()
        manifest = replay.load_task(directory)
        manifest["acquisition_status"] = "acquiring"
        replay.write_json(directory / "task.json", manifest)
        before = snapshot()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main(["--all", "--tasks-root", str(self.tasks)]), 1)
        self.assertEqual(snapshot(), before)

    def test_failed_noise_with_all_files_keeps_estimates_but_is_incomplete(self) -> None:
        directory = self.task("FailedNoise", "noise", "failed")
        for run in (1, 2):
            noise_tdms(directory / "data" / f"FailedNoise_{run:04d}.tdms", "FailedNoise", run)
        with redirect_stdout(io.StringIO()):
            status = replay.process_task(directory, nperseg=512)
        self.assertEqual(status["raw_file_count"], 2)
        self.assertEqual(status["spectrum_file_count"], 2)
        self.assertEqual(status["data_status"], "incomplete")
        self.assertEqual(status["acquisition_status"], "failed")
        self.assertGreater(status["noise_1_hz_nv_per_sqrt_hz"], 0)
        self.assertTrue((directory / "results/FailedNoise_noise_summary.json").exists())
        self.assertIn("saved records only", " ".join(status["notes"]))

    def test_cached_noise_rejects_changed_raw_and_mismatched_metadata(self) -> None:
        directory = self.task("CachedFixture", "noise")
        source = directory / "data" / "CachedFixture_0001.tdms"
        spectrum = directory / "spectra" / "CachedFixture_0001_spectrum.npz"
        noise_tdms(source, "CachedFixture", 1)
        spectrum.parent.mkdir()
        analyzer = replay.legacy_module("analyze_dut_revb_pmu_noise.py")
        samples, fs, gain, bandwidth, run, channel = analyzer.read_capture(source, "CachedFixture")
        frequency, psd, segments, resolution = analyzer.calculate_input_psd(samples, fs, gain, 512)
        analyzer.save_spectrum(spectrum, overwrite=False, frequency_hz=frequency, input_psd_v2_per_hz=psd,
                               source_tdms=source, task_id="CachedFixture", run_number=run, channel_name=channel,
                               sample_rate_hz=fs, closed_loop_gain=gain, closed_loop_bandwidth_hz=bandwidth,
                               sample_count=samples.size, nperseg=512, segment_count=segments,
                               frequency_resolution_hz=resolution)
        task = replay.load_task(directory)
        task["raw_file_sha256"] = {source.relative_to(directory).as_posix(): replay.file_sha256(source)}
        replay.validate_cached_noise(analyzer, source, spectrum, directory, task, 1)
        with np.load(spectrum) as archive:
            values = {name: archive[name] for name in archive.files}
        values["source_sample_count"] = np.int64(4095)
        with spectrum.open("wb") as stream:
            np.savez_compressed(stream, **values)
        with self.assertRaisesRegex(ValueError, "source_sample_count"):
            replay.validate_cached_noise(analyzer, source, spectrum, directory, task, 1)
        with source.open("ab") as stream:
            stream.write(b"corrupted raw bytes")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            replay.validate_cached_noise(analyzer, source, spectrum, directory, task, 1)

    def test_swapped_offset_stages_rejected_against_acquisition_evidence(self) -> None:
        directory = self.task("SwappedFixture", "offset_drift")
        legacy = directory / "provenance" / "legacy_run"
        stages = []
        for index, target in enumerate((-40., 125.), start=1):
            source = directory / "data" / f"stage_{index:02d}" / "SwappedFixture_dcv_0001.tdms"
            offset_tdms(source, "SwappedFixture", np.array([.001 * index, .001 * index + 1e-6]))
            original = legacy / "dmm" / f"stage_{index:02d}" / "data" / "SwappedFixture" / source.name
            original.parent.mkdir(parents=True)
            shutil.copy2(source, original)
            stages.append({"index": index, "target_c": target, "status": "completed",
                           "dmm": {"status": "completed", "requested_readings": 2}})
        replay.write_json(legacy / "summary.json", {"settings": {"task_id": "SwappedFixture"},
                          "stages": stages, "sequence_completed": False})
        shutil.copy2(directory / "data/stage_02/SwappedFixture_dcv_0001.tdms",
                     directory / "data/stage_01/SwappedFixture_dcv_0001.tdms")
        with self.assertRaisesRegex(ValueError, "differs from original acquisition evidence"):
            replay.process_task(directory)

    def test_offset_stages_use_raw_data_and_match_original_numerics(self) -> None:
        directory = self.task("OffsetFixture", "offset_drift")
        legacy = directory / "provenance" / "legacy_run"
        stages = []
        temperatures = []
        for index, target in enumerate((-40., 27., 125.), start=1):
            readings = ((1e-6 + target * 1e-8) * 1001. + np.array([-1e-6, 0., 1e-6]))
            offset_tdms(directory / "data" / f"stage_{index:02d}" / "OffsetFixture_dcv_0001.tdms",
                        "OffsetFixture", readings)
            stages.append({"index": index, "target_c": target, "status": "completed", "dmm": {
                "task_id": "OffsetFixture", "status": "completed", "requested_readings": 3,
                "first_reading_at_utc": "2026-09-18T00:00:01+00:00",
                "last_reading_at_utc": "2026-09-18T00:00:03+00:00"}})
            temperatures.append({"stage_index": str(index), "timestamp_utc": "2026-09-18T00:00:02+00:00",
                                 "product_temperature_c": str(target + .2), "in_band": "True"})
        replay.write_json(legacy / "summary.json", {"settings": {"task_id": "OffsetFixture"},
                          "status": "completed", "stages": stages, "sequence_completed": True,
                          "stop_confirmed": True})
        replay.write_csv(legacy / "temperature.csv", list(temperatures[0]), temperatures)
        with redirect_stdout(io.StringIO()):
            status = replay.process_task(directory)
        self.assertEqual(status["data_status"], "complete")
        self.assertEqual(status["valid_reading_count"], 9)
        self.assertAlmostEqual(status["nominal_temperature_linear_slope_uv_per_c"], .01, places=13)
        aggregate = replay.read_json(directory / "results" / "offset_drift_summary.json")
        self.assertEqual([point["temperature_sample_count"] for point in aggregate["points"]], [1, 1, 1])
        self.assertEqual([point["product_temperature_mean_c"] for point in aggregate["points"]], [-39.8, 27.2, 125.2])
        original_root = self.root / "legacy_offset"
        shutil.copytree(directory / "data" / "stage_01", original_root / "data" / "OffsetFixture")
        analyzer = replay.legacy_module("analyze_dmm7510_offset.py")
        with redirect_stdout(io.StringIO()):
            analyzer.main(["--task-id", "OffsetFixture", "--data-dir", str(original_root / "data"),
                           "--output-dir", str(original_root / "results")])
        actual = replay.read_json(directory / "results" / "stage_01" / "OffsetFixture_dcv_offset_summary.json")
        expected = replay.read_json(original_root / "results" / "OffsetFixture" / "OffsetFixture_dcv_offset_summary.json")
        for key in ("total_reading_count", "output_voltage_v", "equivalent_input_offset_v", "configuration"):
            self.assertEqual(actual[key], expected[key], key)

    def test_chip2_failure_preserved_without_fabricated_offset(self) -> None:
        directory = self.task("Offset_Chip_2", "offset_drift", "failed", chip=2)
        replay.write_json(directory / "provenance" / "legacy_run" / "summary.json", {
            "settings": {"task_id": "Offset_Chip_2"}, "status": "failed", "sequence_completed": False,
            "stop_confirmed": True, "stages": [{"index": 1, "target_c": -40., "status": "failed",
                "dmm": {"status": "failed", "completed_readings": 0, "error": "Reading 1 is overrange"}}]})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(replay.main(["--task-id", "Offset_Chip_2", "--tasks-root", str(self.tasks)]), 0)
        summary = replay.read_json(directory / "results" / "offset_drift_summary.json")
        self.assertEqual(summary["data_status"], "failed")
        self.assertEqual(summary["points"], [])
        self.assertEqual(summary["valid_reading_count"], 0)
        self.assertIsNone(summary["nominal_temperature_linear_slope_v_per_c"])
        self.assertFalse((directory / "results" / "offset_vs_temperature.png").exists())
        overview = replay.read_json(self.root / "results" / "task_overview.json")
        self.assertEqual(overview["tasks"][0]["acquisition_status"], "failed")
        self.assertIsNone(overview["tasks"][0]["nominal_temperature_linear_slope_uv_per_c"])

    def test_completed_offset_without_stages_is_incomplete(self) -> None:
        directory = self.task("EmptyOffset", "offset_drift")
        replay.write_json(directory / "provenance" / "legacy_run" / "summary.json", {
            "settings": {"task_id": "EmptyOffset"}, "status": "completed", "sequence_completed": True,
            "stages": []})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(replay.main(["--all", "--tasks-root", str(self.tasks)]), 1)
        self.assertEqual(replay.read_json(directory / "results" / "processing_status.json")["data_status"], "incomplete")

    def test_manifest_identity_and_provenance_cannot_escape_task(self) -> None:
        directory = self.task("SafeTask", "noise")
        manifest = replay.read_json(directory / "task.json")
        manifest["task_id"] = "OtherTask"
        replay.write_json(directory / "task.json", manifest)
        with self.assertRaisesRegex(ValueError, "differs from directory"):
            replay.load_task(directory)
        with self.assertRaisesRegex(ValueError, "inside its task"):
            replay.legacy_run_directory(directory, {"legacy_run_path": "../../outside"})

    def test_standalone_dcv_and_noise_share_overview(self) -> None:
        directory = self.task("RoomOffset", "dcv_offset")
        manifest = replay.load_task(directory)
        manifest["expected_run_count"] = 1
        replay.write_json(directory / "task.json", manifest)
        offset_tdms(directory / "data/RoomOffset_dcv_0001.tdms", "RoomOffset", np.array([.001, .002, .003]))
        self.task("NoiseAwaitingReplay", "noise")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(replay.main(["--task-id", "RoomOffset", "--tasks-root", str(self.tasks)]), 0)
        overview = replay.read_json(self.root / "results/task_overview.json")
        rows = {row["task_id"]: row for row in overview["tasks"]}
        self.assertEqual(rows["RoomOffset"]["data_status"], "complete")
        self.assertEqual(rows["RoomOffset"]["valid_reading_count"], 3)
        self.assertAlmostEqual(rows["RoomOffset"]["input_offset_mean_uv"], .002 / 1001. * 1e6)
        self.assertEqual(rows["NoiseAwaitingReplay"]["processing_status"], "not_processed")

    def test_malformed_manifest_does_not_stop_other_tasks(self) -> None:
        bad = self.tasks / "A_Malformed"
        bad.mkdir(parents=True)
        (bad / "task.json").write_text("{broken", encoding="utf-8")
        good = self.task("B_FailedDcv", "dcv_offset", "failed")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(replay.main(["--all", "--tasks-root", str(self.tasks)]), 1)
        self.assertEqual(replay.read_json(good / "results/processing_status.json")["processing_status"], "completed")
        overview = replay.read_json(self.root / "results/task_overview.json")
        self.assertEqual(overview["task_count"], 2)
        self.assertEqual(overview["tasks"][0]["data_status"], "error")


if __name__ == "__main__":
    unittest.main()
