import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from cam_icu_logic import calculate_cam_icu, suggest_rass_by_index, OBSERVATION_OPTIONS


class CamIcuLogicTest(unittest.TestCase):
    # ── calculate_cam_icu ──
    def test_positive(self):
        self.assertEqual(calculate_cam_icu(0, True, True, True, False), "POSITIVE")
        self.assertEqual(calculate_cam_icu(0, True, True, False, True), "POSITIVE")

    def test_negative(self):
        self.assertEqual(calculate_cam_icu(0, True, False, True, True), "NEGATIVE")
        self.assertEqual(calculate_cam_icu(0, False, True, True, True), "NEGATIVE")
        self.assertEqual(calculate_cam_icu(0, True, True, False, False), "NEGATIVE")

    def test_gate(self):
        self.assertEqual(calculate_cam_icu(-4), "UNASSESSABLE")
        self.assertEqual(calculate_cam_icu(-5), "UNASSESSABLE")

    def test_rass_minus3_uses_features(self):
        self.assertEqual(calculate_cam_icu(-3, True, True, True, False), "POSITIVE")
        self.assertEqual(calculate_cam_icu(-3, False, True, True, True), "NEGATIVE")

    def test_invalid_rass(self):
        with self.assertRaises(ValueError):
            calculate_cam_icu(5, True, True, True, True)

    def test_missing_features(self):
        with self.assertRaises(ValueError):
            calculate_cam_icu(0, True, True, None, False)

    # ── suggest_rass_by_index ──
    def test_suggest_by_index_scores(self):
        """OBSERVATION_OPTIONS 인덱스와 RASS 점수 매핑 검증"""
        expected = [4, 3, 2, 1, 0, -1, -2, -3, -4, -5]
        for idx, exp_score in enumerate(expected):
            result = suggest_rass_by_index(idx)
            self.assertEqual(result["score"], exp_score, f"index {idx}: expected {exp_score}")
            self.assertEqual(result["status"], "SCORED")

    def test_suggest_invalid_index(self):
        with self.assertRaises(ValueError):
            suggest_rass_by_index(-1)
        with self.assertRaises(ValueError):
            suggest_rass_by_index(10)

    def test_observation_options_count(self):
        self.assertEqual(len(OBSERVATION_OPTIONS), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
