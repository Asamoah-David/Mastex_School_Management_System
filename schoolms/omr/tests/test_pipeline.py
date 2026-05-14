"""Unit tests for OMR decision logic (no image I/O)."""

from __future__ import annotations

import unittest

from django.test import SimpleTestCase

from omr.pipeline import (
    CV2_AVAILABLE,
    _decide_option_scores,
    _infer_questions_per_column,
    _inner_roi_rect,
    _partition_regions_by_column,
)

if CV2_AVAILABLE:
    import cv2
    import numpy as np

    from omr.pipeline import (
        _deprint_lighten_bgr,
        _enhance_gray_marginal_capture,
        _refine_column_horizontal_shifts,
        _refine_column_vertical_shifts,
    )


class OmrPipelineLogicTests(SimpleTestCase):
    def test_decide_blank_when_all_low(self):
        ans, status, _, _, _, _ = _decide_option_scores(
            {"A": 0.02, "B": 0.01, "C": 0.03},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "blank")
        self.assertEqual(ans, "blank")

    def test_decide_multiple_when_two_strong(self):
        ans, status, _, _, _, _ = _decide_option_scores(
            {"A": 0.18, "B": 0.17, "C": 0.02},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "multiple")
        self.assertEqual(ans, "multiple")

    def test_decide_uncertain_when_gap_small(self):
        ans, status, _, _, _, _ = _decide_option_scores(
            {"A": 0.12, "B": 0.11, "C": 0.02},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "uncertain")
        self.assertEqual(ans, "uncertain")

    def test_decide_detected_clear_winner(self):
        ans, status, level, _, baseline, lift = _decide_option_scores(
            {"A": 0.02, "B": 0.14, "C": 0.03},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "detected")
        self.assertEqual(ans, "B")
        self.assertIn(level, ("high", "medium"))
        self.assertLess(baseline, 0.05)
        self.assertGreater(lift, 0.1)

    def test_decide_uncertain_when_row_uniform_no_lift(self):
        """Do not pick a letter when every cell on that row is similarly noisy."""
        ans, status, _, _, baseline, lift = _decide_option_scores(
            {"A": 0.088, "B": 0.086, "C": 0.087, "D": 0.085, "E": 0.089},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.04,
            min_lift_from_baseline=0.032,
        )
        self.assertEqual(status, "uncertain")
        self.assertLess(lift, 0.032)

    def test_inner_roi_clamps(self):
        x, y, w, h = _inner_roi_rect(10, 10, 40, 40, 0.5, 100, 100)
        self.assertEqual(w, 20)
        self.assertEqual(h, 20)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_infer_questions_per_column_from_config(self):
        r = [{"question": i, "boxes": {}} for i in range(1, 61)]
        self.assertEqual(_infer_questions_per_column({"questions_per_column": 20}, r), 20)
        self.assertEqual(_infer_questions_per_column({"template_id": "basic_30_ad"}, [{}] * 30), 15)

    def test_partition_regions_by_column(self):
        regions = [
            {"question": 1, "boxes": {}},
            {"question": 21, "boxes": {}},
        ]
        cols = _partition_regions_by_column(regions, 20)
        self.assertEqual(list(cols[0]), [regions[0]])
        self.assertEqual(list(cols[1]), [regions[1]])


@unittest.skipUnless(CV2_AVAILABLE, "OpenCV + numpy required")
class OmrCvPipelineTests(SimpleTestCase):
    def test_deprint_raises_mean_l_on_saturated_magenta(self):
        """High-chroma pixels should get a higher L channel (lighter gray after BGR round-trip)."""
        bgr = np.zeros((40, 40, 3), dtype=np.uint8)
        bgr[:, :] = (255, 0, 255)  # magenta in BGR
        out = _deprint_lighten_bgr(bgr, strength=0.5)
        g0 = float(np.mean(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)))
        g1 = float(np.mean(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)))
        self.assertGreater(g1, g0 + 5.0)

    def test_marginal_enhancement_runs_without_crash(self):
        flat = np.full((80, 80), 118, dtype=np.uint8)
        flat[30:50, 30:50] = 95
        out = _enhance_gray_marginal_capture(flat, {})
        self.assertEqual(out.shape, flat.shape)
        self.assertTrue(np.any(out != flat))
        self.assertGreaterEqual(int(out.min()), 0)
        self.assertLessEqual(int(out.max()), 255)

    def test_column_vertical_shift_returns_bounded_integer(self):
        """Refinement should complete and return dy within the search radius."""
        diff = np.ones((100, 100), dtype=np.uint8) * 50
        regions = [
            {
                "question": 1,
                "boxes": {"A": {"x": 10, "y": 20, "w": 24, "h": 20}},
            }
        ]
        by_col = _partition_regions_by_column(regions, 20)
        shifts = _refine_column_vertical_shifts(diff, by_col, 0.5, 100, 100, dy_max=3)
        self.assertIn(0, shifts)
        self.assertGreaterEqual(shifts[0], -3)
        self.assertLessEqual(shifts[0], 3)

    def test_column_horizontal_shift_returns_bounded_integer(self):
        diff = np.ones((100, 120), dtype=np.uint8) * 50
        regions = [
            {"question": 1, "boxes": {"A": {"x": 10, "y": 20, "w": 24, "h": 20}}},
        ]
        by_col = _partition_regions_by_column(regions, 20)
        col_dy = {0: 0}
        shifts = _refine_column_horizontal_shifts(
            diff, by_col, 0.5, 120, 100, col_dy, dx_max=3
        )
        self.assertIn(0, shifts)
        self.assertGreaterEqual(shifts[0], -3)
        self.assertLessEqual(shifts[0], 3)
