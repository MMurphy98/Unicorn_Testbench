"""Execute the actual RevB notebook with synthetic TDMS in a real Python kernel."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError
import numpy as np

import process_tasks as replay
from test_process_tasks import noise_tdms, offset_tdms


NOTEBOOK = Path(__file__).with_name("postprocess.ipynb")
REPO_ROOT = NOTEBOOK.parents[2]


class NotebookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="unicorn-notebook-test-")
        self.root = Path(self.temporary.name)
        self.tasks = self.root / "copied data with spaces" / "tasks"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def task(self, task_id: str, kind: str, status: str = "completed") -> Path:
        directory = self.tasks / task_id
        replay.write_json(directory / "task.json", {
            "task_id": task_id, "measurement_type": kind, "chip": 1,
            "acquisition_status": status, "expected_run_count": 2,
        })
        return directory

    def execute(self, task_id: str, *, regenerate: bool = False,
                nperseg: int = 512, cwd: Path = REPO_ROOT):
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        nbformat.validate(notebook)
        parameters = next(cell for cell in notebook.cells
                          if "parameters" in cell.metadata.get("tags", []))
        parameters.source = (
            f"TASK_ID = {task_id!r}\nREGENERATE_SPECTRA = {regenerate!r}\n"
            f"TASKS_ROOT = {str(self.tasks)!r}\nWELCH_NPERSEG = {nperseg!r}\n"
        )
        return NotebookClient(
            notebook, timeout=180, kernel_name="python3",
            resources={"metadata": {"path": str(cwd)}},
        ).execute()

    def status(self, directory: Path) -> dict:
        return replay.read_json(directory / "results/processing_status.json")

    def test_noise_generate_reuse_and_force_regenerate_in_notebook(self) -> None:
        directory = self.task("NotebookNoise", "noise")
        for run in (1, 2):
            noise_tdms(directory / "data" / f"NotebookNoise_{run:04d}.tdms",
                       directory.name, run)
        raw_hashes = {p.name: replay.file_sha256(p) for p in (directory / "data").iterdir()}
        first = self.execute(directory.name)
        self.assertEqual(self.status(directory)["spectra_created"], 2)
        images = [output for cell in first.cells for output in cell.get("outputs", [])
                  if "image/png" in output.get("data", {})]
        self.assertEqual(len(images), 2)
        before = {p.name: (p.stat().st_mtime_ns, replay.file_sha256(p))
                  for p in (directory / "spectra").glob("*.npz")}
        self.execute(directory.name, nperseg=1024, cwd=NOTEBOOK.parent)
        self.assertEqual(self.status(directory)["spectra_reused"], 2)
        self.assertEqual(self.status(directory)["spectra_created"], 0)
        self.assertEqual(before, {p.name: (p.stat().st_mtime_ns, replay.file_sha256(p))
                                  for p in (directory / "spectra").glob("*.npz")})
        self.execute(directory.name, regenerate=True, nperseg=1024)
        self.assertEqual(self.status(directory)["spectra_created"], 2)
        self.assertEqual(self.status(directory)["spectra_reused"], 0)
        for p in (directory / "spectra").glob("*.npz"):
            with np.load(p) as spectrum:
                self.assertEqual(spectrum["welch_nperseg"].item(), 1024)
        self.assertEqual(raw_hashes, {p.name: replay.file_sha256(p)
                                     for p in (directory / "data").iterdir()})

    def test_offset_drift_three_temperatures_and_inline_plot(self) -> None:
        directory = self.task("NotebookDrift", "offset_drift")
        stages, temperatures = [], []
        for index, target in enumerate((-40., 27., 125.), 1):
            values = (1e-6 + target * 1e-8) * 1001. + np.array([-1e-6, 0., 1e-6])
            offset_tdms(directory / "data" / f"stage_{index:02d}" /
                        f"{directory.name}_dcv_0001.tdms", directory.name, values)
            stages.append({"index": index, "target_c": target, "status": "completed", "dmm": {
                "task_id": directory.name, "status": "completed", "requested_readings": 3,
                "first_reading_at_utc": "2026-09-18T00:00:01+00:00",
                "last_reading_at_utc": "2026-09-18T00:00:03+00:00"}})
            temperatures.append({"stage_index": str(index),
                                 "timestamp_utc": "2026-09-18T00:00:02+00:00",
                                 "product_temperature_c": str(target + .2), "in_band": "True"})
        legacy = directory / "provenance/legacy_run"
        replay.write_json(legacy / "summary.json", {
            "settings": {"task_id": directory.name}, "status": "completed",
            "sequence_completed": True, "stop_confirmed": True, "stages": stages,
        })
        replay.write_csv(legacy / "temperature.csv", list(temperatures[0]), temperatures)
        executed = self.execute(directory.name, regenerate=True)
        status = self.status(directory)
        self.assertEqual(status["measurement_type"], "offset_drift")
        self.assertEqual(status["valid_reading_count"], 9)
        self.assertAlmostEqual(status["nominal_temperature_linear_slope_uv_per_c"], .01, places=13)
        self.assertFalse((directory / "spectra").exists())
        images = [output for cell in executed.cells for output in cell.get("outputs", [])
                  if "image/png" in output.get("data", {})]
        self.assertEqual(len(images), 1)

    def test_failed_offset_does_not_display_stale_offset_plot(self) -> None:
        directory = self.task("NotebookFailedDrift", "offset_drift", "failed")
        replay.write_json(directory / "provenance/legacy_run/summary.json", {
            "settings": {"task_id": directory.name}, "status": "failed", "sequence_completed": False,
            "stages": [{"index": 1, "target_c": -40., "status": "failed",
                        "dmm": {"status": "failed", "error": "Reading 1 is overrange"}}],
        })
        (directory / "results").mkdir()
        (directory / "results/offset_vs_temperature.png").write_bytes(b"stale plot, do not display")
        executed = self.execute(directory.name, regenerate=True)
        status = self.status(directory)
        self.assertEqual(status["data_status"], "failed")
        self.assertEqual(status["valid_reading_count"], 0)
        self.assertIsNone(status["nominal_temperature_linear_slope_uv_per_c"])
        self.assertFalse(any("image/png" in output.get("data", {})
                             for cell in executed.cells for output in cell.get("outputs", [])))
        self.assertIn("Reading 1 is overrange", json.dumps(executed, ensure_ascii=False))

    def test_force_regeneration_without_raw_data_keeps_cache_untouched(self) -> None:
        directory = self.task("NotebookMissingRaw", "noise")
        (directory / "spectra").mkdir()
        spectrum = directory / "spectra/NotebookMissingRaw_0001_spectrum.npz"
        spectrum.write_bytes(b"existing cached spectrum")
        with self.assertRaisesRegex(CellExecutionError, "原始 TDMS"):
            self.execute(directory.name, regenerate=True)
        self.assertEqual(spectrum.read_bytes(), b"existing cached spectrum")
        self.assertFalse((directory / "results").exists())

    def test_acquiring_task_is_rejected_before_writes(self) -> None:
        directory = self.task("NotebookAcquiring", "noise", "acquiring")
        before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(CellExecutionError, "还在采集"):
            self.execute(directory.name)
        self.assertEqual(before, {p.relative_to(directory): p.read_bytes()
                                  for p in directory.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
