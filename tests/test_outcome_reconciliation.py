import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.paper import ensure_paper_tables, create_candidate
from research.predictions import Prediction, ensure_prediction_tables, persist_prediction
from research.paper_outcomes import ensure_paper_outcome_tables, link_prediction_to_candidate, record_paper_prediction_outcome
from research.outcome_reconciliation import ensure_outcome_reconciliation_tables, reconcile_paper_outcomes


class OutcomeReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_paper_tables(self.db)
        ensure_prediction_tables(self.db)
        ensure_paper_outcome_tables(self.db)
        ensure_outcome_reconciliation_tables(self.db)
        persist_prediction(self.db, Prediction("PRED-1", "EXP-1", "DS-1", "ABC", "2026-01-01T00:00:00+00:00", 5, "LONG", .7, "model-v1", "features-v1"))
        self.candidate = create_candidate(self.db, {"ticker": "ABC", "direction": "BUY", "confidence_band": "RESEARCH_CANDIDATE", "timestamp": "2026-01-01T00:00:00+00:00", "entry_price": 100, "signals": [], "warnings": []})
        self.cid = self.candidate["candidate_id"]
        link_prediction_to_candidate(self.db, "PRED-1", self.cid)

    def test_missing_observation_is_explicit(self):
        result = reconcile_paper_outcomes(self.db)
        self.assertEqual(result["status"], "INCOMPLETE_OBSERVATIONS")
        self.assertEqual(result["missing_count"], 1)
        self.assertFalse(result["inferred_outcomes"])
        self.assertFalse(result["live_execution"])

    def test_observed_outcome_is_complete_and_deterministic(self):
        record_paper_prediction_outcome(self.db, "PRED-1", self.cid, 1, .04)
        first = reconcile_paper_outcomes(self.db, candidate_id=self.cid)
        second = reconcile_paper_outcomes(self.db, candidate_id=self.cid)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(first["observed_count"], 1)
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM outcome_reconciliation_runs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
