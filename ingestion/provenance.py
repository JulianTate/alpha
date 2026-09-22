"""Immutable provider-retrieval and point-in-time universe evidence."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from research.registry import canonical_hash, now


def ensure_provenance_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS provider_retrieval_evidence(
        retrieval_id TEXT PRIMARY KEY, retrieval_hash TEXT UNIQUE NOT NULL,
        provider TEXT NOT NULL, symbol TEXT NOT NULL, requested_start TEXT NOT NULL,
        requested_end TEXT NOT NULL, retrieved_at TEXT NOT NULL,
        response_status TEXT NOT NULL, row_count INTEGER NOT NULL,
        source_snapshot_hash TEXT, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS universe_membership_evidence(
        membership_id TEXT PRIMARY KEY, membership_hash TEXT UNIQUE NOT NULL,
        dataset_id TEXT NOT NULL, symbol TEXT NOT NULL, valid_from TEXT NOT NULL,
        valid_to TEXT, inclusion_basis TEXT NOT NULL, source_snapshot_hash TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(dataset_id,symbol,valid_from)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS data_update_run_summaries(
        run_id TEXT PRIMARY KEY, run_hash TEXT UNIQUE NOT NULL, provider TEXT NOT NULL,
        requested_start TEXT NOT NULL, requested_end TEXT NOT NULL,
        universe_json TEXT NOT NULL, results_json TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS update_reconciliation_reports(
        report_id TEXT PRIMARY KEY, report_hash TEXT UNIQUE NOT NULL,
        run_id TEXT NOT NULL, result_json TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS retrieval_completeness_reports(
        report_id TEXT PRIMARY KEY, report_hash TEXT UNIQUE NOT NULL,
        dataset_id TEXT NOT NULL, provider TEXT NOT NULL, requested_start TEXT NOT NULL,
        requested_end TEXT NOT NULL, expected_symbols_json TEXT NOT NULL,
        items_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
        update_run_id TEXT
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(retrieval_completeness_reports)")}
    if "update_run_id" not in columns:
        connection.execute("ALTER TABLE retrieval_completeness_reports ADD COLUMN update_run_id TEXT")


def record_retrieval(connection: sqlite3.Connection, *, provider: str, symbol: str,
                     requested_start: str, requested_end: str, retrieved_at: str,
                     response_status: str, row_count: int,
                     source_snapshot_hash: str | None = None,
                     metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"provider": provider, "symbol": symbol.upper(), "requested_start": requested_start,
            "requested_end": requested_end, "retrieved_at": retrieved_at,
            "response_status": response_status, "row_count": int(row_count),
            "source_snapshot_hash": source_snapshot_hash, "metadata": metadata or {}}
    digest = canonical_hash(body)
    result = {"retrieval_id": f"RET-{digest[:16].upper()}", "retrieval_hash": digest, **body}
    ensure_provenance_tables(connection)
    existing = connection.execute("SELECT retrieval_hash FROM provider_retrieval_evidence WHERE retrieval_id=?", (result["retrieval_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError("retrieval evidence changed for existing retrieval ID")
    connection.execute("INSERT OR IGNORE INTO provider_retrieval_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (result["retrieval_id"], digest, body["provider"], body["symbol"], body["requested_start"], body["requested_end"], body["retrieved_at"], body["response_status"], body["row_count"], source_snapshot_hash, json.dumps(body["metadata"], sort_keys=True), now()))
    return result


def record_update_summary(connection: sqlite3.Connection, *, provider: str,
                          requested_start: str, requested_end: str,
                          universe: list[str], results: list[dict[str, Any]],
                          status: str) -> dict[str, Any]:
    body = {"provider": provider, "requested_start": requested_start, "requested_end": requested_end,
            "universe": sorted({str(symbol).upper() for symbol in universe}), "results": results, "status": status}
    digest = canonical_hash(body)
    result = {"run_id": f"UPD-{digest[:16].upper()}", "run_hash": digest, **body}
    ensure_provenance_tables(connection)
    connection.execute("INSERT OR IGNORE INTO data_update_run_summaries VALUES(?,?,?,?,?,?,?,?,?)",
        (result["run_id"], digest, provider, requested_start, requested_end,
         json.dumps(body["universe"], sort_keys=True), json.dumps(results, sort_keys=True), status, now()))
    return result


def reconcile_update_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """Compare an update summary with persisted provider-response evidence."""
    ensure_provenance_tables(connection)
    run = connection.execute("""SELECT run_id, provider, requested_start, requested_end,
                               universe_json, results_json, status
                               FROM data_update_run_summaries WHERE run_id=?""", (run_id,)).fetchone()
    if not run:
        raise KeyError(f"unknown update run: {run_id}")
    expected = sorted({str(symbol).upper() for symbol in json.loads(run[4])})
    result_rows = {str(item.get("symbol", "")).upper(): item for item in json.loads(run[5])}
    items = []
    for symbol in expected:
        evidence = connection.execute("""SELECT retrieval_id, response_status, row_count
            FROM provider_retrieval_evidence WHERE provider=? AND symbol=?
            AND requested_start=? AND requested_end=? ORDER BY retrieval_id""",
            (run[1], symbol, run[2], run[3])).fetchall()
        reported = result_rows.get(symbol)
        evidence_status = "NO_EVIDENCE" if not evidence else ("CONFLICT" if len({row[1] for row in evidence}) > 1 else "PRESENT")
        items.append({"symbol": symbol, "reported_status": reported.get("status") if reported else "MISSING_FROM_SUMMARY",
                      "evidence_status": evidence_status, "retrieval_ids": [row[0] for row in evidence]})
    extra = sorted(set(result_rows) - set(expected))
    status = "RECONCILED" if not extra and all(item["evidence_status"] == "PRESENT" for item in items) else "RECONCILIATION_INCOMPLETE"
    return {"run_id": run[0], "provider": run[1], "requested_start": run[2], "requested_end": run[3],
            "run_status": run[6], "status": status, "items": items, "extra_result_symbols": extra,
            "guardrails": ["No missing provider evidence is inferred", "No response is repaired or substituted"]}


def record_reconciliation_report(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    result = reconcile_update_run(connection, run_id)
    body = {"run_id": run_id, "result": result, "status": result["status"]}
    digest = canonical_hash(body)
    report = {"report_id": f"URR-{digest[:16].upper()}", "report_hash": digest, **body}
    ensure_provenance_tables(connection)
    connection.execute("INSERT OR IGNORE INTO update_reconciliation_reports VALUES(?,?,?,?,?,?)",
                       (report["report_id"], digest, run_id, json.dumps(result, sort_keys=True), report["status"], now()))
    return report


def list_reconciliation_reports(connection: sqlite3.Connection, *, run_id: str | None = None) -> list[dict[str, Any]]:
    ensure_provenance_tables(connection)
    query = "SELECT report_id, report_hash, run_id, result_json, status, created_at FROM update_reconciliation_reports"
    params: tuple[Any, ...] = ()
    if run_id is not None:
        query += " WHERE run_id=?"
        params = (run_id,)
    query += " ORDER BY created_at, report_id"
    return [{"report_id": row[0], "report_hash": row[1], "run_id": row[2],
             "result": json.loads(row[3]), "status": row[4], "created_at": row[5]}
            for row in connection.execute(query, params).fetchall()]


def list_retrieval_completeness(connection: sqlite3.Connection, *, dataset_id: str | None = None) -> list[dict[str, Any]]:
    ensure_provenance_tables(connection)
    query = "SELECT report_id, report_hash, dataset_id, provider, requested_start, requested_end, expected_symbols_json, items_json, status, created_at, update_run_id FROM retrieval_completeness_reports"
    params: tuple[Any, ...] = ()
    if dataset_id is not None:
        query += " WHERE dataset_id=?"
        params = (dataset_id,)
    query += " ORDER BY created_at, report_id"
    rows = connection.execute(query, params).fetchall()
    return [{"report_id": row[0], "report_hash": row[1], "dataset_id": row[2], "provider": row[3],
             "requested_start": row[4], "requested_end": row[5],
             "expected_symbols": json.loads(row[6]), "items": json.loads(row[7]),
             "status": row[8], "created_at": row[9], "update_run_id": row[10]} for row in rows]


def record_retrieval_completeness(connection: sqlite3.Connection, *, dataset_id: str,
                                  provider: str, requested_start: str,
                                  requested_end: str, expected_symbols: list[str],
                                  update_run_id: str | None = None) -> dict[str, Any]:
    """Persist an immutable expected-versus-observed retrieval report.

    Missing evidence is reported explicitly as NO_EVIDENCE; it is not repaired
    or silently treated as provider coverage.
    """
    ensure_provenance_tables(connection)
    symbols = sorted({str(symbol).upper() for symbol in expected_symbols})
    items = []
    for symbol in symbols:
        rows = connection.execute("""SELECT retrieval_id, response_status, row_count,
                   source_snapshot_hash FROM provider_retrieval_evidence
                   WHERE provider=? AND symbol=? AND requested_start=? AND requested_end=?
                   ORDER BY retrieval_id""", (provider, symbol, requested_start, requested_end)).fetchall()
        if not rows:
            items.append({"symbol": symbol, "status": "NO_EVIDENCE", "retrieval_ids": []})
            continue
        statuses = sorted({str(row[1]) for row in rows})
        snapshots = sorted({str(row[3]) for row in rows if row[3] is not None})
        total_rows = sum(int(row[2]) for row in rows)
        conflicting = len(rows) > 1 and (len(snapshots) > 1 or len(statuses) > 1)
        item_status = "CONFLICT" if conflicting else ("COVERED" if any(status == "OK" and int(row[2]) > 0 for row in rows for status in [row[1]]) else "INCOMPLETE")
        items.append({"symbol": symbol, "status": item_status, "retrieval_ids": [row[0] for row in rows],
                      "response_statuses": statuses, "source_snapshot_hashes": snapshots, "observed_rows": total_rows})
    status = "READY" if items and all(item["status"] == "COVERED" for item in items) else "INCOMPLETE"
    body = {"dataset_id": dataset_id, "provider": provider, "requested_start": requested_start,
            "requested_end": requested_end, "expected_symbols": symbols, "items": items,
            "status": status, "update_run_id": update_run_id}
    digest = canonical_hash(body)
    result = {"report_id": f"RCR-{digest[:16].upper()}", "report_hash": digest, **body}
    connection.execute("INSERT OR IGNORE INTO retrieval_completeness_reports VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (result["report_id"], digest, dataset_id, provider, requested_start, requested_end,
         json.dumps(symbols, sort_keys=True), json.dumps(items, sort_keys=True), status, now(), update_run_id))
    return result


def build_dataset_provenance_view(connection: sqlite3.Connection, dataset_id: str) -> dict[str, Any]:
    """Join local dataset, retrieval, update, and membership provenance descriptively.

    The view exposes missing or incomplete components; it never treats a partial
    join as valid evidence and grants no numerical or execution authority.
    """
    if not str(dataset_id).strip():
        raise ValueError("dataset_id is required")
    ensure_provenance_tables(connection)
    from ingestion.dataset_contract import ensure_dataset_contract_tables
    ensure_dataset_contract_tables(connection)
    contract = connection.execute(
        "SELECT contract_hash, universe_json, quality_status, source_snapshot_hash "
        "FROM dataset_reconstruction_records WHERE dataset_id=?", (dataset_id,)
    ).fetchone()
    reports = list_retrieval_completeness(connection, dataset_id=dataset_id)
    memberships = connection.execute(
        "SELECT membership_id, membership_hash, symbol, valid_from, valid_to "
        "FROM universe_membership_evidence WHERE dataset_id=? ORDER BY symbol, valid_from, membership_id",
        (dataset_id,),
    ).fetchall()
    run_ids = sorted({report["update_run_id"] for report in reports if report["update_run_id"]})
    runs = []
    for run_id in run_ids:
        row = connection.execute(
            "SELECT run_id, run_hash, status FROM data_update_run_summaries WHERE run_id=?", (run_id,)
        ).fetchone()
        runs.append({"run_id": run_id, "run_hash": row[1], "status": row[2]} if row else
                    {"run_id": run_id, "status": "UNRESOLVED"})
    component_status = {
        "dataset_contract": "RESOLVED" if contract else "UNRESOLVED",
        "retrieval_completeness": "RESOLVED" if reports else "UNRESOLVED",
        "update_runs": "RESOLVED" if all(item["status"] != "UNRESOLVED" for item in runs) else "UNRESOLVED",
        "universe_membership": "RESOLVED" if memberships else "UNRESOLVED",
    }
    status = "RESOLVED" if all(value == "RESOLVED" for value in component_status.values()) else "INCOMPLETE"
    return {
        "dataset_id": dataset_id, "status": status, "component_status": component_status,
        "dataset_contract": ({"contract_hash": contract[0], "quality_status": contract[2],
                               "source_snapshot_hash": contract[3], "universe": json.loads(contract[1])}
                              if contract else None),
        "retrieval_completeness_reports": reports,
        "update_runs": runs,
        "universe_memberships": [{"membership_id": row[0], "membership_hash": row[1],
                                  "symbol": row[2], "valid_from": row[3], "valid_to": row[4]}
                                 for row in memberships],
        "manual_review_required": True, "numerical_authority": False, "live_execution": False,
    }


def record_membership(connection: sqlite3.Connection, *, dataset_id: str, symbol: str,
                      valid_from: str, valid_to: str | None, inclusion_basis: str,
                      source_snapshot_hash: str) -> dict[str, Any]:
    body = {"dataset_id": dataset_id, "symbol": symbol.upper(), "valid_from": valid_from,
            "valid_to": valid_to, "inclusion_basis": inclusion_basis,
            "source_snapshot_hash": source_snapshot_hash}
    digest = canonical_hash(body)
    result = {"membership_id": f"MEM-{digest[:16].upper()}", "membership_hash": digest, **body}
    ensure_provenance_tables(connection)
    existing = connection.execute("SELECT membership_hash FROM universe_membership_evidence WHERE membership_id=?", (result["membership_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError("universe membership evidence changed for existing membership ID")
    connection.execute("INSERT OR IGNORE INTO universe_membership_evidence VALUES(?,?,?,?,?,?,?,?,?)",
        (result["membership_id"], digest, dataset_id, body["symbol"], valid_from, valid_to, inclusion_basis, source_snapshot_hash, now()))
    return result
