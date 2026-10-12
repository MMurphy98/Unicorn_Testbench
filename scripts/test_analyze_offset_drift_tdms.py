"""Numerical checks for offline TDMS offset-versus-temperature analysis."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
import analyze_offset_drift_tdms as analysis


class DriftTests(unittest.TestCase):
    def test_exact_linear_curve_and_unsorted_temperatures(self):
        x = np.array([125., -40., 27.])
        result = analysis.drift_metrics(x, 5 + 2 * x)
        self.assertAlmostEqual(result['box_drift_nv_per_c'], 2)
        self.assertAlmostEqual(result['linear_fit_slope_nv_per_c'], 2)
        self.assertAlmostEqual(result['endpoint_slope_nv_per_c'], 2)
        self.assertAlmostEqual(result['linear_fit_offset_at_27_nv'], 59)
        self.assertAlmostEqual(result['linear_fit_max_abs_residual_nv'], 0)

    def test_negative_and_constant_offset_curves(self):
        x = np.array([-40., 27., 125.])
        negative = analysis.drift_metrics(x, 4 - 3 * x)
        self.assertAlmostEqual(negative['box_drift_nv_per_c'], 3)
        self.assertAlmostEqual(negative['linear_fit_slope_nv_per_c'], -3)
        flat = analysis.drift_metrics(x, [7, 7, 7])
        self.assertEqual(flat['box_drift_nv_per_c'], 0)
        self.assertEqual(flat['linear_fit_slope_nv_per_c'], 0)
        self.assertIsNone(flat['linear_fit_r_squared'])

    def test_intermediate_extremum_is_included_in_box_drift(self):
        x, y = [-40, 27, 125], [-23, -44, -24]
        result = analysis.drift_metrics(x, y)
        self.assertAlmostEqual(result['box_drift_nv_per_c'], 21 / 165)
        self.assertAlmostEqual(result['endpoint_slope_nv_per_c'], -1 / 165)
        self.assertAlmostEqual(result['linear_fit_slope_nv_per_c'], np.polyfit(x, y, 1)[0])
        self.assertAlmostEqual(result['segment_slopes'][0]['slope_nv_per_c'], -21 / 67)
        self.assertAlmostEqual(result['segment_slopes'][1]['slope_nv_per_c'], 20 / 98)

    def test_invalid_pairs_do_not_produce_a_drift_value(self):
        for x, y in (([1], [2]), ([1, 1], [2, 3]), ([1, 2], [3]), ([1, 2], [3, np.nan])):
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                analysis.drift_metrics(x, y)

    def test_task_identity_preserves_chip_condition_date_and_negative_temperature(self):
        result = analysis.parse_task_id('RevB_Chip_3_wiShield_Gmx_default_OSC_default_Vsup_pm6V_-40C_20260914')
        self.assertEqual(result['chip'], 3)
        self.assertEqual(result['temperature_c'], -40)
        self.assertEqual(result['date'], '20260914')
        self.assertEqual(result['device_id'], 'RevB_Chip_3_wiShield_Gmx_default_OSC_default_Vsup_pm6V')
        for invalid in ('offset', 'RevB_Chip_3_x_50C_20260914', 'RevB_Chip_3_x_27C_20260230'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                analysis.parse_task_id(invalid)

    def test_gain_scaling_and_time_windows_use_actual_reading_times(self):
        task_id = 'RevB_Chip_1_test_27C_20260914'
        record = SimpleNamespace(readings_v=np.array([10., 20., 30., 40.]) * 1e-9 * 1001,
            elapsed_s=np.array([0., 1., 2., 3.]), gain=1001., run_number=6,
            acquisition_start_utc=datetime(2026, 9, 14, tzinfo=timezone.utc), path=Path('test.tdms'))
        point = analysis.point_statistics(record, analysis.parse_task_id(task_id),
                    {'task_id': task_id, 'acquisition_duration_s': 3.1}, 1.)
        self.assertAlmostEqual(point['input_offset_mean_nv'], 25)
        self.assertAlmostEqual(point['input_offset_sample_std_nv'], np.std([10, 20, 30, 40], ddof=1))
        self.assertAlmostEqual(point['first_window_mean_nv'], 15)
        self.assertAlmostEqual(point['last_window_mean_nv'], 35)
        self.assertAlmostEqual(point['last_minus_first_window_mean_nv'], 20)
        self.assertEqual(point['last_window_count'], 2)
        self.assertAlmostEqual(point['time_linear_slope_nv_per_min'], 600)


if __name__ == '__main__':
    unittest.main()
