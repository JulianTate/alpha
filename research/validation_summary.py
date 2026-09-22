"""Persisted campaign-level validation summaries.

This composes existing diagnostics without converting them into a profitability
claim or an automated promotion decision.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .registry import canonical_hash, now


def ensure_validation_summary_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS campaign_validation_summaries(
        summary_id TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        campaign_id TEXT NOT NULL,
        experiment_id TEXT,
        dataset_id TEXT NOT NULL,
        walk_forward_json TEXT NOT NULL,
        baseline_json TEXT NOT NULL,
        anti_overfitting_json TEXT NOT NULL,
        gate_json TEXT NOT NULL,
        decision TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def persist_validation_summary(connection: sqlite3.Connection, *, campaign_id: str,
                               experiment_id: str | None, dataset_id: str,
                               walk_forward: dict[str, Any], baseline: dict[str, Any],
                               anti_overfitting: dict[str, Any], gate: dict[str, Any],
                               summary_id: str | None = None) -> dict[str, Any]:
    body = {"campaign_id": campaign_id, "experiment_id": experiment_id, "dataset_id": dataset_id,
            "walk_forward": walk_forward, "baseline": baseline,
            "anti_overfitting": anti_overfitting, "gate": gate}
    digest = canonical_hash(body)
    result = {"summary_id": summary_id or f"VAL-{digest[:16].upper()}", "definition_hash": digest,
              "campaign_id": campaign_id, "experiment_id": experiment_id, "dataset_id": dataset_id,
              "decision": gate.get("decision", "UNRESOLVED"), "walk_forward": walk_forward,
              "baseline": baseline, "anti_overfitting": anti_overfitting, "gate": gate}
    ensure_validation_summary_tables(connection)
    existing = connection.execute("SELECT definition_hash FROM campaign_validation_summaries WHERE summary_id=?", (result["summary_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"validation summary already exists with a different definition: {result['summary_id']}")
    connection.execute("""INSERT OR IGNORE INTO campaign_validation_summaries
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (result["summary_id"], digest, campaign_id, experiment_id, dataset_id,
        json.dumps(walk_forward, sort_keys=True), json.dumps(baseline, sort_keys=True),
        json.dumps(anti_overfitting, sort_keys=True), json.dumps(gate, sort_keys=True),
        result["decision"], now()))
    return result
