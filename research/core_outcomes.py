"""Explicit manual outcome observations for Core/ISA intelligence records."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_core_outcome_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""
    CREATE TABLE IF NOT EXISTS core_intelligence_outcomes(
        outcome_id TEXT PRIMARY KEY, record_id TEXT NOT NULL,
        observed_at TEXT NOT NULL, outcome_type TEXT NOT NULL,
        value REAL, source TEXT NOT NULL, notes TEXT NOT NULL,
        provenance_json TEXT NOT NULL DEFAULT '{}',
        definition_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
    )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(core_intelligence_outcomes)")}
    if "provenance_json" not in columns:
        connection.execute("ALTER TABLE core_intelligence_outcomes ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'")


def record_core_outcome(connection: sqlite3.Connection, *, record_id: str, observed_at: str,
                        outcome_type: str, value: float | None = None,
                        source: str = "manual", notes: str = "",
                        provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist an explicitly observed Core/ISA outcome; never infer or forecast one."""
    ensure_core_outcome_tables(connection)
    if not connection.execute("SELECT 1 FROM core_intelligence_records WHERE record_id=?", (record_id,)).fetchone():
        raise ValueError(f"core intelligence record not found: {record_id}")
    if not observed_at.strip() or not outcome_type.strip() or not source.strip():
        raise ValueError("observed_at, outcome_type, and source are required")
    if value is not None and not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    body = {"record_id": record_id, "observed_at": observed_at.strip(),
            "outcome_type": outcome_type.strip().upper(), "value": value,
            "source": source.strip(), "notes": notes.strip(), "provenance": provenance or {}}
    digest = _hash(body)
    outcome_id = f"COREOUT-{digest[:16].upper()}"
    existing = connection.execute("SELECT definition_hash FROM core_intelligence_outcomes WHERE outcome_id=?", (outcome_id,)).fetchone()
    if existing:
        if existing[0] != digest:
            raise ValueError("immutable core outcome conflict")
    else:
        connection.execute("""INSERT INTO core_intelligence_outcomes
            (outcome_id, record_id, observed_at, outcome_type, value, source, notes,
             provenance_json, definition_hash, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (outcome_id, record_id, body["observed_at"], body["outcome_type"], body["value"],
             body["source"], body["notes"], json.dumps(body["provenance"], sort_keys=True), digest,
             datetime.now(timezone.utc).isoformat()))
    return {"outcome_id": outcome_id, **body, "status": "OBSERVED",
            "inferred_outcome": False, "manual_review_required": True, "live_execution": False}


def compare_core_outcomes(connection: sqlite3.Connection, record_id: str | None = None,
                          observation_start: str | None = None, observation_end: str | None = None) -> dict[str, Any]:
    if observation_start and observation_end and observation_start > observation_end:
        raise ValueError("observation_start must not be after observation_end")
    record_clauses, record_params = ["1=1"], []
    outcome_clauses, outcome_params = ["o.record_id=r.record_id"], []
    if record_id:
        record_clauses.append("r.record_id=?"); record_params.append(record_id)
    if observation_start:
        outcome_clauses.append("o.observed_at>=?"); outcome_params.append(observation_start)
    if observation_end:
        outcome_clauses.append("o.observed_at<=?"); outcome_params.append(observation_end)
    rows = connection.execute(f"""SELECT r.record_id, r.layer, r.subject, r.objective,
        o.outcome_id, o.observed_at, o.outcome_type, o.value, o.source, o.provenance_json
        FROM core_intelligence_records r LEFT JOIN core_intelligence_outcomes o
        ON {' AND '.join(outcome_clauses)}
        WHERE {' AND '.join(record_clauses)}
        ORDER BY r.record_id, o.outcome_id""", outcome_params + record_params).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for rid, layer, subject, objective, oid, observed_at, outcome_type, value, source, provenance_json in rows:
        item = grouped.setdefault(rid, {"record_id": rid, "layer": layer, "subject": subject,
            "objective": objective, "outcomes": []})
        if oid:
            item["outcomes"].append({"outcome_id": oid, "observed_at": observed_at,
                "outcome_type": outcome_type, "value": value, "source": source,
                "provenance": json.loads(provenance_json)})
    records = list(grouped.values())
    for item in records:
        item["status"] = "OBSERVED" if item["outcomes"] else "MISSING_OBSERVATION"
    complete = bool(records) and all(x["outcomes"] for x in records)
    return {"status": "COMPLETE" if complete else "INCOMPLETE_OBSERVATIONS",
            "observation_start": observation_start, "observation_end": observation_end,
            "records": records, "inferred_outcomes": False, "manual_review_required": True,
            "live_execution": False}
