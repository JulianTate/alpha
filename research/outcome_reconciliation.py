"""Deterministic reconciliation of paper candidates, predictions, and outcomes."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .registry import canonical_hash, now


def ensure_outcome_reconciliation_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS outcome_reconciliation_runs(
        run_id TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        candidate_filter TEXT,
        linked_count INTEGER NOT NULL,
        observed_count INTEGER NOT NULL,
        missing_count INTEGER NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def reconcile_paper_outcomes(connection: sqlite3.Connection, *, candidate_id: str | None = None,
                             run_id: str | None = None) -> dict[str, Any]:
    """Report linkage and observation completeness without inferring outcomes."""
    clauses = ["1=1"]
    params: list[Any] = []
    if candidate_id is not None:
        clauses.append("l.candidate_id=?")
        params.append(candidate_id)
    rows = connection.execute(f"""SELECT l.prediction_id, l.candidate_id,
            o.realized_label, o.realized_return
        FROM prediction_paper_links l
        LEFT JOIN prediction_outcomes o ON o.prediction_id=l.prediction_id
        WHERE {' AND '.join(clauses)} ORDER BY l.prediction_id""", params).fetchall()
    records = []
    for prediction_id, linked_candidate_id, label, realized_return in rows:
        records.append({"prediction_id": prediction_id, "candidate_id": linked_candidate_id,
                        "status": "OBSERVED" if label is not None else "MISSING_OBSERVATION",
                        "realized_label": label, "realized_return": realized_return})
    observed = sum(item["status"] == "OBSERVED" for item in records)
    missing = len(records) - observed
    definition = {"candidate_id": candidate_id, "records": records}
    digest = canonical_hash(definition)
    result = {"run_id": run_id or f"RECON-{digest[:16].upper()}", "definition_hash": digest,
              "candidate_filter": candidate_id, "linked_count": len(records),
              "observed_count": observed, "missing_count": missing,
              "status": "COMPLETE" if missing == 0 else "INCOMPLETE_OBSERVATIONS",
              "records": records, "inferred_outcomes": False, "manual_review_required": True,
              "live_execution": False}
    ensure_outcome_reconciliation_tables(connection)
    existing = connection.execute("SELECT definition_hash FROM outcome_reconciliation_runs WHERE run_id=?", (result["run_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"reconciliation run already exists with a different definition: {result['run_id']}")
    connection.execute("INSERT OR IGNORE INTO outcome_reconciliation_runs VALUES(?,?,?,?,?,?,?,?)",
                       (result["run_id"], digest, candidate_id, len(records), observed, missing,
                        json.dumps(result, sort_keys=True), now()))
    return result
