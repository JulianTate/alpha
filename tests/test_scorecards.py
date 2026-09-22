import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.predictions import Prediction, ensure_prediction_tables, persist_prediction
from research.scorecards import (build_scorecard, ensure_scorecard_tables, get_scorecard,
                                  list_scorecards, record_outcome)


class ScorecardTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        ensure_scorecard_tables(self.connection)
        for number, score in enumerate((0.8, 0.6, 0.2), 1):
            persist_prediction(self.connection, Prediction(
                f"PRED-{number}", "EXP-001", "DS-001", "ABC", f"2026-01-0{number}T00:00:00+00:00",
                5, "LONG", score, "model-v1", "features-v1",
            ))
        record_outcome(self.connection, "PRED-1", 1)
        record_outcome(self.connection, "PRED-2", 0)
        record_outcome(self.connection, "PRED-3", 0)

    def test_scorecard_is_deterministic_and_calibrated(self):
        first = build_scorecard(self.connection, "EXP-001", "DS-001")
        second = build_scorecard(self.connection, "EXP-001", "DS-001")
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(first["sample_count"], 3)
        self.assertAlmostEqual(first["accuracy"], 2 / 3)
        self.assertIn("0", first["calibration"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM prediction_scorecards").fetchone()[0], 1)

    def test_declared_oos_scope_and_calibration_error_are_persisted(self):
        result = build_scorecard(self.connection, "EXP-001", "DS-001", evaluation_scope="locked-oos", minimum_observations=3, min_as_of="2026-01-01", max_as_of="2026-12-31", model_versions=["model-v1"])
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["evaluation_scope"], "LOCKED-OOS")
        self.assertGreaterEqual(result["expected_calibration_error"], 0.0)
        stored = get_scorecard(self.connection, result["scorecard_id"])
        self.assertEqual(stored["status"], "COMPLETE")
        self.assertEqual(stored["expected_model_versions"], ["model-v1"])
        self.assertEqual(len(list_scorecards(self.connection, experiment_id="EXP-001")), 1)

    def test_insufficient_oos_sample_is_explicit_and_immutable(self):
        result = build_scorecard(self.connection, "EXP-001", "DS-001", minimum_observations=4)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["sample_count"], 3)
        with self.assertRaises(ValueError):
            build_scorecard(self.connection, "EXP-001", "DS-001", scorecard_id=result["scorecard_id"], minimum_observations=2)

    def test_outcome_cannot_be_silently_changed(self):
        with self.assertRaises(ValueError):
            record_outcome(self.connection, "PRED-1", 0)


if __name__ == "__main__":
    unittest.main()
