import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.research_memory import (
    ensure_research_memory_tables, record_memory, search_memory,
    link_memory_provenance, list_memory_provenance_links,
    validate_memory_provenance_links,
)
from ingestion.provenance import ensure_provenance_tables, record_retrieval



class ResearchMemoryTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_research_memory_tables(self.db)

    def test_immutable_record_and_deterministic_search(self):
        note = record_memory(self.db, title="Momentum caveat", body="Momentum can suffer crashes and crowding.",
                             record_type="literature", as_of="2026-09-21", source_refs=["EVID-MOMENTUM-momentum-v1"], tags=["Factor", "risk"])
        same = record_memory(self.db, title="Momentum caveat", body="Momentum can suffer crashes and crowding.",
                             record_type="literature", as_of="2026-09-21", source_refs=["EVID-MOMENTUM-momentum-v1"], tags=["risk", "factor"])
        self.assertEqual(note["record_id"], same["record_id"])
        results = search_memory(self.db, "momentum crowding")
        self.assertEqual([item["record_id"] for item in results], [note["record_id"]])
        self.assertTrue(results[0]["manual_review_required"])
        self.assertFalse(results[0]["numerical_authority"])

    def test_search_is_bounded_and_missing_query_rejected(self):
        with self.assertRaises(ValueError):
            search_memory(self.db, "", limit=20)
        with self.assertRaises(ValueError):
            search_memory(self.db, "x", limit=101)

    def test_search_supports_exact_structured_filters(self):
        record_memory(self.db, title="Momentum caveat", body="Momentum can suffer crashes.",
                      record_type="literature", as_of="2026-09-21", tags=["factor", "risk"])
        other = record_memory(self.db, title="Momentum implementation", body="Momentum requires costs.",
                              record_type="method", as_of="2026-09-20", tags=["factor", "implementation"])
        results = search_memory(self.db, "momentum", record_type="method", as_of="2026-09-20",
                                tags=["FACTOR", "implementation"])
        self.assertEqual([item["record_id"] for item in results], [other["record_id"]])
        self.assertEqual(results[0]["tags"], ["factor", "implementation"])
        self.assertTrue(results[0]["manual_review_required"])
        self.assertFalse(results[0]["numerical_authority"])

    def test_search_can_include_descriptive_provenance_validation(self):
        ensure_provenance_tables(self.db)
        retrieval = record_retrieval(self.db, provider="test", symbol="ABC", requested_start="2026-01-01",
                                     requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00Z",
                                     response_status="OK", row_count=1)
        note = record_memory(self.db, title="Provider momentum note", body="Momentum evidence requires review.",
                             record_type="provider", as_of="2026-09-21")
        link_memory_provenance(self.db, record_id=note["record_id"], reference_type="provider_retrieval",
                               reference_id=retrieval["retrieval_id"])
        result = search_memory(self.db, "momentum", include_provenance=True)[0]
        self.assertEqual(result["provenance"][0]["validation_status"], "RESOLVED")
        self.assertTrue(result["provenance"][0]["manual_review_required"])
        self.assertFalse(result["provenance"][0]["numerical_authority"])
        self.assertFalse(result["provenance"][0]["live_execution"])
        self.assertEqual(result["provenance_summary"]["overall_status"], "RESOLVED")
        self.assertEqual(result["provenance_summary"]["resolved_count"], 1)

    def test_provenance_summary_is_incomplete_for_unresolved_links(self):
        ensure_provenance_tables(self.db)
        note = record_memory(self.db, title="Unresolved momentum note", body="Momentum evidence is pending.",
                             record_type="provider", as_of="2026-09-21")
        link_memory_provenance(self.db, record_id=note["record_id"], reference_type="provider_retrieval",
                               reference_id="RET-MISSING")
        result = search_memory(self.db, "momentum", include_provenance=True)[0]
        self.assertEqual(result["provenance_summary"]["overall_status"], "INCOMPLETE")
        self.assertEqual(result["provenance_summary"]["unresolved_count"], 1)
        self.assertTrue(result["provenance_summary"]["manual_review_required"])

    def test_typed_provenance_links_are_immutable_and_listed(self):
        note = record_memory(self.db, title="Provider note", body="Observed evidence requires review.",
                             record_type="provider", as_of="2026-09-21", source_refs=["RET-123"])
        link = link_memory_provenance(self.db, record_id=note["record_id"],
                                      reference_type="provider_retrieval", reference_id="RET-123")
        same = link_memory_provenance(self.db, record_id=note["record_id"],
                                      reference_type="provider_retrieval", reference_id="RET-123")
        self.assertEqual(link["link_id"], same["link_id"])
        links = list_memory_provenance_links(self.db, note["record_id"])
        self.assertEqual(links[0]["reference_id"], "RET-123")
        with self.assertRaises(KeyError):
            link_memory_provenance(self.db, record_id="MEM-MISSING", reference_type="evidence", reference_id="E-1")

    def test_local_provenance_validation_is_descriptive(self):
        ensure_provenance_tables(self.db)
        retrieval = record_retrieval(self.db, provider="test", symbol="ABC", requested_start="2026-01-01",
                                     requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00Z",
                                     response_status="OK", row_count=1)
        note = record_memory(self.db, title="Provider note", body="Observed evidence requires review.",
                             record_type="provider", as_of="2026-09-21", source_refs=[retrieval["retrieval_id"]])
        link_memory_provenance(self.db, record_id=note["record_id"], reference_type="provider_retrieval",
                               reference_id=retrieval["retrieval_id"])
        link_memory_provenance(self.db, record_id=note["record_id"], reference_type="provider_retrieval",
                               reference_id="RET-MISSING")
        link_memory_provenance(self.db, record_id=note["record_id"], reference_type="evidence",
                               reference_id="E-1")
        statuses = [item["validation_status"] for item in validate_memory_provenance_links(self.db, note["record_id"])]
        self.assertEqual(sorted(statuses), ["RESOLVED", "UNRESOLVED", "UNSUPPORTED"])
        self.assertTrue(all(item["manual_review_required"] and not item["numerical_authority"] and not item["live_execution"]
                            for item in validate_memory_provenance_links(self.db, note["record_id"])))


if __name__ == "__main__": unittest.main()
