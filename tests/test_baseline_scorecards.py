import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.baseline_scorecards import build_baseline_scorecard, build_baseline_suite


class BaselineScorecardTest(unittest.TestCase):
    def test_baseline_is_deterministic_and_marked_comparative_only(self):
        rows = [
            {"timestamp": "2026-01-01", "net_return": 0.02, "cost_included": True},
            {"timestamp": "2026-01-02", "net_return": -0.01, "cost_included": True},
        ]
        first = build_baseline_scorecard(rows, dataset_id="DS-001")
        second = build_baseline_scorecard(list(reversed(rows)), dataset_id="DS-001")
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(first["sample_count"], 2)
        self.assertTrue(first["comparative_only"])
        self.assertTrue(first["costs_included"])

    def test_baseline_suite_is_deterministic_cost_aware_and_explicit(self):
        rows = [
            {"timestamp": "2026-01-01", "asset_return": 0.02, "benchmark_return": 0.01, "factor_return": 0.015, "technical_return": 0.018},
            {"timestamp": "2026-01-02", "asset_return": -0.01, "benchmark_return": -0.005, "factor_return": -0.004, "technical_return": -0.008},
        ]
        first = build_baseline_suite(rows, dataset_id="DS-001", cost_bps=5, minimum_observations=2)
        second = build_baseline_suite(list(reversed(rows)), dataset_id="DS-001", cost_bps=5, minimum_observations=2)
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(first["status"], "COMPLETE")
        self.assertTrue(first["comparative_only"])
        self.assertEqual(first["scorecards"]["TECHNICAL"]["cost_bps"], 5)

    def test_missing_suite_series_is_insufficient_not_fabricated(self):
        result = build_baseline_suite([{"timestamp": "2026-01-01", "asset_return": 0.01}], dataset_id="DS-001", cost_bps=5, minimum_observations=2)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["scorecards"]["FACTOR"]["status"], "INSUFFICIENT_DATA")

    def test_missing_returns_are_blocked(self):
        with self.assertRaises(ValueError):
            build_baseline_scorecard([{"timestamp": "2026-01-01"}], dataset_id="DS-001")


if __name__ == "__main__":
    unittest.main()
