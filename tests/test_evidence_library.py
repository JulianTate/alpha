import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.evidence_library import (
    EvidenceRecord,
    ensure_evidence_tables,
    list_evidence,
    register_builtin_evidence,
    register_evidence,
)


class EvidenceLibraryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        ensure_evidence_tables(self.connection)

    def test_builtin_records_are_versioned_and_idempotent(self):
        first = register_builtin_evidence(self.connection)
        second = register_builtin_evidence(self.connection)
        self.assertEqual(len(first), 8)
        self.assertEqual([item["definition_hash"] for item in first], [item["definition_hash"] for item in second])
        self.assertEqual(len(list_evidence(self.connection)), 8)
        self.assertTrue(all(item["implementation_status"] == "EVIDENCE_LIBRARY" for item in first))

    def test_reusing_a_version_with_changed_definition_is_rejected(self):
        record = EvidenceRecord(
            "TEST", "Test", "test-v1", "research", ("source",), "definition",
            ("prices",), (5,), ("limitation",), ("cost",), ("failure",),
        )
        register_evidence(self.connection, record)
        changed = EvidenceRecord(
            "TEST", "Test", "test-v1", "research", ("source",), "changed",
            ("prices",), (5,), ("limitation",), ("cost",), ("failure",),
        )
        with self.assertRaises(ValueError):
            register_evidence(self.connection, changed)


if __name__ == "__main__":
    unittest.main()
