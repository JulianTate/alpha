import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.core_intelligence import ensure_core_intelligence_tables, record_core_intelligence
from research.core_outcomes import ensure_core_outcome_tables, record_core_outcome, compare_core_outcomes

class CoreOutcomeTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_core_intelligence_tables(self.db)
        ensure_core_outcome_tables(self.db)
        self.record = record_core_intelligence(self.db, layer="ISA", subject="ABC", as_of="2026-09-21",
            objective="RETIREMENT_CORE", thesis="Context")

    def test_missing_then_observed_without_inference(self):
        missing = compare_core_outcomes(self.db)
        self.assertEqual(missing["status"], "INCOMPLETE_OBSERVATIONS")
        observed = record_core_outcome(self.db, record_id=self.record["record_id"], observed_at="2026-10-01",
            outcome_type="THESIS_REVIEW", value=1.0,
            provenance={"source_id": "manual-review-1", "method": "operator_observation"})
        self.assertFalse(observed["inferred_outcome"])
        self.assertEqual(observed["provenance"]["method"], "operator_observation")
        result = compare_core_outcomes(self.db, observation_start="2026-09-01", observation_end="2026-10-31")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(len(result["records"][0]["outcomes"]), 1)
        self.assertEqual(result["observation_start"], "2026-09-01")

    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):
            compare_core_outcomes(self.db, observation_start="2026-11-01", observation_end="2026-10-01")

    def test_nonfinite_value_rejected(self):
        with self.assertRaises(ValueError):
            record_core_outcome(self.db, record_id=self.record["record_id"], observed_at="2026-10-01",
                outcome_type="REVIEW", value=float("nan"))

if __name__ == "__main__":
    unittest.main()
