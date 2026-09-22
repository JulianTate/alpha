import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.paper import ensure_paper_tables, create_candidate, record_observation
from research.paper_review import ensure_paper_review_tables, record_operator_review, evaluate_paper_observation_gate


class PaperReviewTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_paper_tables(self.db)
        ensure_paper_review_tables(self.db)
        self.candidate = create_candidate(self.db, {
            "ticker": "ABC", "direction": "BUY", "confidence_band": "RESEARCH_CANDIDATE",
            "timestamp": "2026-01-01T00:00:00+00:00", "entry_price": 100,
            "signals": [], "warnings": []
        })
        self.candidate_id = self.candidate["candidate_id"]

    def test_gate_blocks_without_review_and_observation(self):
        result = evaluate_paper_observation_gate(self.db, self.candidate_id)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["decision"], "BLOCKED_OR_INSUFFICIENT_OBSERVATION")
        self.assertFalse(result["live_execution"])

    def test_approved_review_and_observation_are_required(self):
        record_operator_review(self.db, self.candidate_id, decision="APPROVE_PAPER",
                               reviewer="operator", rationale="Evidence reviewed.", evidence={"source": "manual"})
        blocked = evaluate_paper_observation_gate(self.db, self.candidate_id)
        self.assertFalse(blocked["eligible"])
        record_observation(self.db, self.candidate_id, "REVIEWED", observed_price=100)
        result = evaluate_paper_observation_gate(self.db, self.candidate_id)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["manual_execution_required"])

    def test_review_is_immutable_and_input_is_validated(self):
        first = record_operator_review(self.db, self.candidate_id, decision="DEFER",
                                       reviewer="operator", rationale="Need more data.")
        second = record_operator_review(self.db, self.candidate_id, decision="DEFER",
                                        reviewer="operator", rationale="Need more data.")
        self.assertEqual(first["review_id"], second["review_id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM operator_reviews").fetchone()[0], 1)
        with self.assertRaises(ValueError):
            record_operator_review(self.db, self.candidate_id, decision="APPROVE_PAPER", reviewer="", rationale="x")
        with self.assertRaises(ValueError):
            evaluate_paper_observation_gate(self.db, self.candidate_id, minimum_observations=0)


if __name__ == "__main__":
    unittest.main()
