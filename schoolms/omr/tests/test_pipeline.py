"""Unit tests for OMR decision logic (no image I/O)."""

from __future__ import annotations

from django.test import SimpleTestCase

from omr.pipeline import _decide_option_scores, _inner_roi_rect


class OmrPipelineLogicTests(SimpleTestCase):
    def test_decide_blank_when_all_low(self):
        ans, status, _, _ = _decide_option_scores(
            {"A": 0.02, "B": 0.01, "C": 0.03},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "blank")
        self.assertEqual(ans, "blank")

    def test_decide_multiple_when_two_strong(self):
        ans, status, _, _ = _decide_option_scores(
            {"A": 0.18, "B": 0.17, "C": 0.02},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "multiple")
        self.assertEqual(ans, "multiple")

    def test_decide_uncertain_when_gap_small(self):
        ans, status, _, _ = _decide_option_scores(
            {"A": 0.12, "B": 0.11, "C": 0.02},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "uncertain")
        self.assertEqual(ans, "uncertain")

    def test_decide_detected_clear_winner(self):
        ans, status, level, _ = _decide_option_scores(
            {"A": 0.02, "B": 0.14, "C": 0.03},
            min_mark=0.08,
            strong_mark=0.15,
            min_gap=0.05,
        )
        self.assertEqual(status, "detected")
        self.assertEqual(ans, "B")
        self.assertIn(level, ("high", "medium"))

    def test_inner_roi_clamps(self):
        x, y, w, h = _inner_roi_rect(10, 10, 40, 40, 0.5, 100, 100)
        self.assertEqual(w, 20)
        self.assertEqual(h, 20)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
