import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.core_intelligence import ensure_core_intelligence_tables, record_core_intelligence, list_core_intelligence


class CoreIntelligenceTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_core_intelligence_tables(self.db)

    def test_records_are_separate_and_non_executable(self):
        result = record_core_intelligence(self.db, layer="ISA", subject="ABC", as_of="2026-09-21",
                                          objective="RETIREMENT_CORE", thesis="Long-term research context",
                                          context={"holding_horizon": "long_term"}, evidence={"source": "manual"})
        self.assertEqual(result["status"], "RECORDED")
        self.assertFalse(result["live_execution"])
        self.assertTrue(result["manual_review_required"])
        self.assertEqual(result["objective"], "RETIREMENT_CORE")
        self.assertEqual(result["context"]["holding_horizon"], "long_term")
        self.assertEqual(list_core_intelligence(self.db, "ISA")[0]["layer"], "ISA")
        self.assertEqual(list_core_intelligence(self.db, "CORE"), [])

    def test_idempotent_and_invalid_layer_rejected(self):
        kwargs = dict(layer="CORE", subject="ABC", as_of="2026-09-21", objective="CORE_RESEARCH", thesis="Context")
        first = record_core_intelligence(self.db, **kwargs)
        second = record_core_intelligence(self.db, **kwargs)
        self.assertEqual(first["record_id"], second["record_id"])
        with self.assertRaises(ValueError):
            record_core_intelligence(self.db, layer="TACTICAL", subject="ABC", as_of="2026-09-21", thesis="No")


if __name__ == "__main__":
    unittest.main()
