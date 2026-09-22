import contextlib
import io
import json
import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.provenance import (ensure_provenance_tables, list_reconciliation_reports,
                                  list_retrieval_completeness, record_membership, record_retrieval,
                                  record_reconciliation_report, record_retrieval_completeness,
                                  record_update_summary, build_dataset_provenance_view)


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_provenance_tables(self.db)

    def test_retrieval_is_deterministic_and_immutable(self):
        args = dict(provider="fixture", symbol="abc", requested_start="2026-01-01", requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00+00:00", response_status="OK", row_count=2, source_snapshot_hash="snap-1", metadata={"http_status": 200})
        first = record_retrieval(self.db, **args)
        second = record_retrieval(self.db, **args)
        self.assertEqual(first["retrieval_hash"], second["retrieval_hash"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM provider_retrieval_evidence").fetchone()[0], 1)

    def test_retrieval_completeness_reports_missing_and_covered_symbols(self):
        record_retrieval(self.db, provider="fixture", symbol="ABC", requested_start="2026-01-01",
                         requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00+00:00",
                         response_status="OK", row_count=2)
        result = record_retrieval_completeness(self.db, dataset_id="DS-1", provider="fixture",
                                               requested_start="2026-01-01", requested_end="2026-01-02",
                                               expected_symbols=["ABC", "MISSING"], update_run_id="UPD-1")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual({item["symbol"]: item["status"] for item in result["items"]},
                         {"ABC": "COVERED", "MISSING": "NO_EVIDENCE"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retrieval_completeness_reports").fetchone()[0], 1)
        self.assertEqual(list_retrieval_completeness(self.db, dataset_id="DS-1")[0]["update_run_id"], "UPD-1")

    def test_retrieval_completeness_detects_conflicting_snapshots(self):
        common = dict(provider="fixture", symbol="ABC", requested_start="2026-01-01",
                      requested_end="2026-01-02", row_count=2)
        record_retrieval(self.db, retrieved_at="2026-01-03T00:00:00+00:00",
                         response_status="OK", source_snapshot_hash="snap-1", **common)
        record_retrieval(self.db, retrieved_at="2026-01-04T00:00:00+00:00",
                         response_status="OK", source_snapshot_hash="snap-2", **common)
        result = record_retrieval_completeness(self.db, dataset_id="DS-1", provider="fixture",
                                               requested_start="2026-01-01", requested_end="2026-01-02",
                                               expected_symbols=["ABC"])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["items"][0]["status"], "CONFLICT")

    def test_reconciliation_report_is_persisted_and_idempotent(self):
        run = record_update_summary(self.db, provider="fixture", requested_start="2026-01-01",
                                    requested_end="2026-01-02", universe=["ABC"],
                                    results=[{"symbol": "ABC", "status": "DATA_BLOCKED"}],
                                    status="DATA_BLOCKED")
        first = record_reconciliation_report(self.db, run["run_id"])
        second = record_reconciliation_report(self.db, run["run_id"])
        self.assertEqual(first["report_hash"], second["report_hash"])
        reports = list_reconciliation_reports(self.db, run_id=run["run_id"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["status"], "RECONCILIATION_INCOMPLETE")

    def test_reconcile_update_run_reports_missing_evidence(self):
        run = record_update_summary(self.db, provider="fixture", requested_start="2026-01-01",
                                    requested_end="2026-01-02", universe=["ABC"],
                                    results=[{"symbol": "ABC", "status": "DATA_BLOCKED"}],
                                    status="DATA_BLOCKED")
        from ingestion.provenance import reconcile_update_run
        result = reconcile_update_run(self.db, run["run_id"])
        self.assertEqual(result["status"], "RECONCILIATION_INCOMPLETE")
        self.assertEqual(result["items"][0]["evidence_status"], "NO_EVIDENCE")

    def test_reconcile_update_run_reports_present_evidence(self):
        run = record_update_summary(self.db, provider="fixture", requested_start="2026-01-01",
                                    requested_end="2026-01-02", universe=["ABC"],
                                    results=[{"symbol": "ABC", "status": "DATA_READY"}],
                                    status="DATA_READY")
        record_retrieval(self.db, provider="fixture", symbol="ABC", requested_start="2026-01-01",
                         requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00+00:00",
                         response_status="OK", row_count=2)
        from ingestion.provenance import reconcile_update_run
        result = reconcile_update_run(self.db, run["run_id"])
        self.assertEqual(result["status"], "RECONCILED")
        self.assertEqual(result["items"][0]["evidence_status"], "PRESENT")

    def test_list_retrieval_completeness_filters_dataset(self):
        record_retrieval_completeness(self.db, dataset_id="DS-1", provider="fixture",
                                      requested_start="2026-01-01", requested_end="2026-01-02",
                                      expected_symbols=["ABC"])
        record_retrieval_completeness(self.db, dataset_id="DS-2", provider="fixture",
                                      requested_start="2026-01-01", requested_end="2026-01-02",
                                      expected_symbols=["XYZ"])
        reports = list_retrieval_completeness(self.db, dataset_id="DS-1")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["dataset_id"], "DS-1")

    def test_cli_reconciliation_report_unknown_run_returns_structured_not_found(self):
        import alpha
        original_argv = sys.argv
        output = io.StringIO()
        try:
            sys.argv = ['alpha.py', 'reconciliation-report', '--run-id', 'UPD-NOTFOUND']
            with contextlib.redirect_stdout(output):
                alpha.cli()
        finally:
            sys.argv = original_argv
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'NOT_FOUND')
        self.assertEqual(result['run_id'], 'UPD-NOTFOUND')

    def test_cli_reconcile_unknown_run_returns_structured_not_found(self):
        import alpha
        original_argv = sys.argv
        output = io.StringIO()
        try:
            sys.argv = ['alpha.py', 'reconcile-update-run', '--run-id', 'UPD-NOTFOUND']
            with contextlib.redirect_stdout(output):
                alpha.cli()
        finally:
            sys.argv = original_argv
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'NOT_FOUND')
        self.assertEqual(result['run_id'], 'UPD-NOTFOUND')

    def test_cli_retrieval_completeness_reports_no_evidence(self):
        import alpha
        original_argv = sys.argv
        output = io.StringIO()
        try:
            sys.argv = ['alpha.py', 'retrieval-completeness', '--dataset', 'DS-CLI',
                        '--provider', 'fixture', '--symbol', 'ABC', '--start', '2026-01-01',
                        '--end', '2026-01-02']
            with contextlib.redirect_stdout(output):
                alpha.cli()
        finally:
            sys.argv = original_argv
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['items'][0]['status'], 'NO_EVIDENCE')

    def test_update_summary_persists_blocked_results(self):
        result = record_update_summary(self.db, provider="fixture", requested_start="2026-01-01",
                                       requested_end="2026-01-02", universe=["abc"],
                                       results=[{"symbol": "ABC", "status": "DATA_BLOCKED"}],
                                       status="DATA_BLOCKED")
        self.assertTrue(result["run_id"].startswith("UPD-"))
        self.assertEqual(self.db.execute("SELECT status FROM data_update_run_summaries").fetchone()[0], "DATA_BLOCKED")

    def test_dataset_provenance_view_is_explicitly_incomplete_when_components_are_missing(self):
        view = build_dataset_provenance_view(self.db, "DS-MISSING")
        self.assertEqual(view["status"], "INCOMPLETE")
        self.assertEqual(view["component_status"]["dataset_contract"], "UNRESOLVED")
        self.assertTrue(view["manual_review_required"])
        self.assertFalse(view["numerical_authority"])
        self.assertFalse(view["live_execution"])

    def test_dataset_provenance_view_joins_local_components_without_authority(self):
        from ingestion.dataset_contract import register_dataset_contract
        register_dataset_contract(self.db, {
            "dataset_id": "DS-JOIN", "universe_definition": ["ABC"],
            "as_of_policy": "point-in-time", "corporate_action_policy": "explicit",
            "survivorship_policy": "frozen", "source_snapshot_hash": "snap-1",
            "quality_status": "VALID",
        })
        record_retrieval(self.db, provider="fixture", symbol="ABC", requested_start="2026-01-01",
                         requested_end="2026-01-02", retrieved_at="2026-01-03T00:00:00+00:00",
                         response_status="OK", row_count=2, source_snapshot_hash="snap-1")
        run = record_update_summary(self.db, provider="fixture", requested_start="2026-01-01",
                                    requested_end="2026-01-02", universe=["ABC"],
                                    results=[{"symbol": "ABC", "status": "DATA_READY"}], status="DATA_READY")
        record_retrieval_completeness(self.db, dataset_id="DS-JOIN", provider="fixture",
                                      requested_start="2026-01-01", requested_end="2026-01-02",
                                      expected_symbols=["ABC"], update_run_id=run["run_id"])
        record_membership(self.db, dataset_id="DS-JOIN", symbol="ABC", valid_from="2026-01-01",
                          valid_to=None, inclusion_basis="frozen", source_snapshot_hash="snap-1")
        view = build_dataset_provenance_view(self.db, "DS-JOIN")
        self.assertEqual(view["status"], "RESOLVED")
        self.assertEqual(view["component_status"], {"dataset_contract": "RESOLVED",
                         "retrieval_completeness": "RESOLVED", "update_runs": "RESOLVED",
                         "universe_membership": "RESOLVED"})
        self.assertFalse(view["numerical_authority"])

    def test_membership_normalizes_symbol_and_is_idempotent(self):
        args = dict(dataset_id="DS-1", symbol="aapl", valid_from="2026-01-01", valid_to=None, inclusion_basis="frozen pilot universe", source_snapshot_hash="snap-1")
        first = record_membership(self.db, **args)
        second = record_membership(self.db, **args)
        self.assertEqual(first["membership_hash"], second["membership_hash"])
        self.assertEqual(first["symbol"], "AAPL")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM universe_membership_evidence").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
