"""Paper-observation gates and immutable operator review records.

This module records human decisions and evaluates whether a paper candidate has
sufficient explicitly observed evidence. It never places orders or authorizes
live execution.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


REVIEW_DECISIONS = {"APPROVE_PAPER", "REJECT", "DEFER"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_paper_review_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS operator_reviews(
        review_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES paper_candidates(candidate_id),
        decision TEXT NOT NULL, reviewer TEXT NOT NULL, rationale TEXT NOT NULL,
        evidence_json TEXT NOT NULL, definition_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS paper_observation_gates(
        gate_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES paper_candidates(candidate_id),
        decision TEXT NOT NULL, observation_count INTEGER NOT NULL, minimum_observations INTEGER NOT NULL,
        review_status TEXT NOT NULL, definition_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
    );
    """)


def record_operator_review(connection: sqlite3.Connection, candidate_id: str, *, decision: str,
                           reviewer: str, rationale: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"invalid operator review decision: {decision}")
    if not reviewer.strip() or not rationale.strip():
        raise ValueError("reviewer and rationale are required")
    if not connection.execute("SELECT 1 FROM paper_candidates WHERE candidate_id=?", (candidate_id,)).fetchone():
        raise ValueError("paper candidate not found")
    evidence = evidence or {}
    body = {"candidate_id": candidate_id, "decision": decision, "reviewer": reviewer.strip(),
            "rationale": rationale.strip(), "evidence": evidence}
    digest = _hash(body)
    review_id = f"REVIEW-{digest[:16].upper()}"
    existing = connection.execute("SELECT definition_hash FROM operator_reviews WHERE review_id=?", (review_id,)).fetchone()
    if existing:
        return {"review_id": review_id, **body, "status": "RECORDED", "immutable": True}
    connection.execute("INSERT INTO operator_reviews VALUES(?,?,?,?,?,?,?,?)",
                       (review_id, candidate_id, decision, body["reviewer"], body["rationale"],
                        json.dumps(evidence, sort_keys=True), digest, _now()))
    return {"review_id": review_id, **body, "status": "RECORDED", "immutable": True}


def evaluate_paper_observation_gate(connection: sqlite3.Connection, candidate_id: str, *,
                                    minimum_observations: int = 1) -> dict[str, Any]:
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be at least 1")
    if not connection.execute("SELECT 1 FROM paper_candidates WHERE candidate_id=?", (candidate_id,)).fetchone():
        raise ValueError("paper candidate not found")
    count = int(connection.execute("SELECT COUNT(*) FROM paper_observations WHERE candidate_id=?", (candidate_id,)).fetchone()[0])
    review = connection.execute("SELECT decision,reviewer FROM operator_reviews WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1", (candidate_id,)).fetchone()
    review_status = review[0] if review else "MISSING"
    checks = [
        {"name": "operator_review", "passed": review_status == "APPROVE_PAPER", "detail": f"latest review is {review_status}"},
        {"name": "observation_count", "passed": count >= minimum_observations, "detail": f"{count} observations; minimum {minimum_observations}"},
    ]
    eligible = all(item["passed"] for item in checks)
    body = {"candidate_id": candidate_id, "decision": "ELIGIBLE_FOR_PAPER_OBSERVATION" if eligible else "BLOCKED_OR_INSUFFICIENT_OBSERVATION",
            "observation_count": count, "minimum_observations": minimum_observations, "review_status": review_status}
    digest = _hash(body)
    gate_id = f"PGATE-{digest[:16].upper()}"
    connection.execute("INSERT OR IGNORE INTO paper_observation_gates VALUES(?,?,?,?,?,?,?,?)",
                       (gate_id, candidate_id, body["decision"], count, minimum_observations, review_status, digest, _now()))
    return {"gate_id": gate_id, **body, "eligible": eligible, "live_execution": False,
            "manual_execution_required": True, "checks": checks}
