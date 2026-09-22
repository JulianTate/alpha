"""Bounded, cacheable LLM interpretation requests; never authoritative numerics."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .registry import canonical_hash, now


def ensure_interpretation_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS research_interpretations(
        request_id TEXT PRIMARY KEY, request_hash TEXT UNIQUE NOT NULL,
        input_json TEXT NOT NULL, instruction TEXT NOT NULL,
        token_budget INTEGER NOT NULL, status TEXT NOT NULL,
        output_json TEXT, created_at TEXT NOT NULL, completed_at TEXT,
        manual_review_required INTEGER NOT NULL, numerical_authority INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_research_interpretations_hash
        ON research_interpretations(request_hash);
    """)


def prepare_interpretation(
    connection: sqlite3.Connection,
    *,
    subject: str,
    evidence: dict[str, Any],
    instruction: str,
    token_budget: int = 1000,
) -> dict[str, Any]:
    """Create or reuse a deterministic interpretation request.

    The request is cacheable and descriptive. It does not call a provider, score a
    strategy, calculate an outcome, authorize promotion, or authorize execution.
    """
    if not subject.strip() or not instruction.strip():
        raise ValueError("subject and instruction are required")
    if token_budget < 1 or token_budget > 100_000:
        raise ValueError("token_budget must be between 1 and 100000")
    body = {"subject": subject, "evidence": evidence, "instruction": instruction}
    digest = canonical_hash(body)
    request_id = f"INT-{digest[:16].upper()}"
    existing = connection.execute(
        "SELECT status,token_budget,output_json FROM research_interpretations WHERE request_hash=?",
        (digest,),
    ).fetchone()
    if existing:
        return {
            "request_id": request_id, "request_hash": digest, "status": "CACHED",
            "token_budget": existing[1], "output": json.loads(existing[2]) if existing[2] else None,
            "manual_review_required": True, "numerical_authority": False,
        }
    connection.execute(
        "INSERT INTO research_interpretations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, digest, json.dumps(body, sort_keys=True), instruction,
         token_budget, "PENDING", None, now(), None, 1, 0),
    )
    return {
        "request_id": request_id, "request_hash": digest, "status": "PENDING",
        "token_budget": token_budget, "input": body,
        "manual_review_required": True, "numerical_authority": False,
    }


def record_interpretation(
    connection: sqlite3.Connection, request_id: str, output: dict[str, Any]
) -> dict[str, Any]:
    """Persist provider output as untrusted descriptive text/data for review."""
    row = connection.execute(
        "SELECT request_hash,status FROM research_interpretations WHERE request_id=?", (request_id,)
    ).fetchone()
    if not row:
        raise ValueError("interpretation request not found")
    if row[1] == "COMPLETED":
        raise ValueError("interpretation output is immutable")
    connection.execute(
        "UPDATE research_interpretations SET status='COMPLETED',output_json=?,completed_at=? WHERE request_id=?",
        (json.dumps(output, sort_keys=True), now(), request_id),
    )
    return {
        "request_id": request_id, "request_hash": row[0], "status": "COMPLETED",
        "output": output, "manual_review_required": True, "numerical_authority": False,
    }
