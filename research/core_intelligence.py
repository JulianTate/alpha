"""Separated Alpha Core / ISA intelligence records.

These records provide long-term research context only. They are not tactical
paper candidates, signals, orders, or execution authorizations.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

CORE_LAYERS = {"ISA", "CORE"}


def _hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_core_intelligence_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""
    CREATE TABLE IF NOT EXISTS core_intelligence_records(
        record_id TEXT PRIMARY KEY, layer TEXT NOT NULL, subject TEXT NOT NULL,
        as_of TEXT NOT NULL, objective TEXT NOT NULL DEFAULT 'GENERAL_RESEARCH',
        thesis TEXT NOT NULL, context_json TEXT NOT NULL DEFAULT '{}',
        evidence_json TEXT NOT NULL, definition_hash TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(core_intelligence_records)")}
    if "objective" not in columns:
        connection.execute("ALTER TABLE core_intelligence_records ADD COLUMN objective TEXT NOT NULL DEFAULT 'GENERAL_RESEARCH'")
    if "context_json" not in columns:
        connection.execute("ALTER TABLE core_intelligence_records ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'")


def record_core_intelligence(
    connection: sqlite3.Connection, *, layer: str, subject: str, as_of: str,
    thesis: str, objective: str = "GENERAL_RESEARCH",
    context: dict[str, Any] | None = None, evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an immutable informational record, never a trade instruction."""
    layer = layer.upper().strip()
    if layer not in CORE_LAYERS:
        raise ValueError(f"layer must be one of {sorted(CORE_LAYERS)}")
    if not subject.strip() or not as_of.strip() or not thesis.strip() or not objective.strip():
        raise ValueError("subject, as_of, objective, and thesis are required")
    body = {
        "layer": layer, "subject": subject.strip(), "as_of": as_of.strip(),
        "objective": objective.strip().upper(), "thesis": thesis.strip(),
        "context": context or {}, "evidence": evidence or {},
    }
    digest = _hash(body)
    record_id = f"CORE-{digest[:16].upper()}"
    existing = connection.execute(
        "SELECT definition_hash FROM core_intelligence_records WHERE record_id=?", (record_id,)
    ).fetchone()
    if existing:
        if existing[0] != digest:
            raise ValueError("immutable core record conflict")
        return {"record_id": record_id, **body, "status": "RECORDED", "immutable": True,
                "live_execution": False, "manual_review_required": True}
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """INSERT INTO core_intelligence_records
        (record_id, layer, subject, as_of, objective, thesis, context_json,
         evidence_json, definition_hash, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (record_id, layer, body["subject"], body["as_of"], body["objective"], body["thesis"],
         json.dumps(body["context"], sort_keys=True), json.dumps(body["evidence"], sort_keys=True),
         digest, now),
    )
    return {"record_id": record_id, **body, "status": "RECORDED", "immutable": True,
            "live_execution": False, "manual_review_required": True}


def list_core_intelligence(connection: sqlite3.Connection, layer: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT record_id,layer,subject,as_of,objective,thesis,context_json,evidence_json,definition_hash,created_at FROM core_intelligence_records"
    params: tuple[Any, ...] = ()
    if layer:
        layer = layer.upper().strip()
        if layer not in CORE_LAYERS:
            raise ValueError(f"layer must be one of {sorted(CORE_LAYERS)}")
        query += " WHERE layer=?"
        params = (layer,)
    query += " ORDER BY created_at, record_id"
    return [{"record_id": r[0], "layer": r[1], "subject": r[2], "as_of": r[3],
             "objective": r[4], "thesis": r[5], "context": json.loads(r[6]),
             "evidence": json.loads(r[7]), "definition_hash": r[8], "created_at": r[9],
             "live_execution": False, "manual_review_required": True}
            for r in connection.execute(query, params).fetchall()]
