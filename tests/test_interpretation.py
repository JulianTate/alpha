import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.interpretation import ensure_interpretation_tables, prepare_interpretation, record_interpretation


class InterpretationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_interpretation_tables(self.db)

    def test_requests_are_deterministically_cached_and_non_authoritative(self):
        args = dict(subject="event result", evidence={"result": "descriptive"}, instruction="summarize caveats", token_budget=250)
        first = prepare_interpretation(self.db, **args)
        second = prepare_interpretation(self.db, **args)
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertEqual(second["status"], "CACHED")
        self.assertTrue(first["manual_review_required"])
        self.assertFalse(first["numerical_authority"])

    def test_output_is_immutable_and_budget_is_bounded(self):
        request = prepare_interpretation(self.db, subject="s", evidence={}, instruction="i", token_budget=1)
        completed = record_interpretation(self.db, request["request_id"], {"summary": "untrusted"})
        self.assertEqual(completed["status"], "COMPLETED")
        with self.assertRaises(ValueError):
            record_interpretation(self.db, request["request_id"], {"summary": "changed"})
        with self.assertRaises(ValueError):
            prepare_interpretation(self.db, subject="s", evidence={}, instruction="i", token_budget=100001)


if __name__ == "__main__":
    unittest.main()
