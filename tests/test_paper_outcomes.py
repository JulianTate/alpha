import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.paper_outcomes import ensure_paper_outcome_tables, record_paper_prediction_outcome
from research.predictions import Prediction, persist_prediction
from research.paper import ensure_paper_tables, create_candidate


class PaperOutcomesTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_paper_tables(self.db)
        ensure_paper_outcome_tables(self.db)
        persist_prediction(self.db, Prediction("PRED-1", "EXP-1", "DS-1", "ABC", "2026-01-01T00:00:00+00:00", 5, "LONG", .7, "model-v1", "features-v1"))
        self.candidate = create_candidate(self.db, {"ticker": "ABC", "direction": "BUY", "confidence_band": "RESEARCH_CANDIDATE", "timestamp": "2026-01-01T00:00:00+00:00", "entry_price": 100, "signals": [], "warnings": []})

    def test_manual_paper_outcome_is_linked_and_persisted(self):
        result = record_paper_prediction_outcome(self.db, "PRED-1", self.candidate["candidate_id"], 1, .04)
        self.assertEqual(result["source"], "manual_paper_observation")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM prediction_paper_links").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT realized_label FROM prediction_outcomes").fetchone()[0], 1)

    def test_missing_candidate_is_rejected(self):
        with self.assertRaises(ValueError):
            record_paper_prediction_outcome(self.db, "PRED-1", "PAPER-MISSING", 1)


if __name__ == "__main__":
    unittest.main()
