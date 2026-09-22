"""Bridge manual paper observations into prediction outcome records."""
from __future__ import annotations

import sqlite3

from .registry import now
from .scorecards import ensure_scorecard_tables, record_outcome


def ensure_paper_outcome_tables(connection: sqlite3.Connection) -> None:
    ensure_scorecard_tables(connection)
    connection.execute("""CREATE TABLE IF NOT EXISTS prediction_paper_links(
        prediction_id TEXT PRIMARY KEY REFERENCES predictions(prediction_id),
        candidate_id TEXT NOT NULL REFERENCES paper_candidates(candidate_id),
        linked_at TEXT NOT NULL
    )""")


def link_prediction_to_candidate(connection: sqlite3.Connection, prediction_id: str, candidate_id: str) -> dict:
    """Link one prediction to one paper candidate without changing either record."""
    ensure_paper_outcome_tables(connection)
    if not connection.execute("SELECT 1 FROM predictions WHERE prediction_id=?", (prediction_id,)).fetchone():
        raise ValueError(f"prediction not found: {prediction_id}")
    if not connection.execute("SELECT 1 FROM paper_candidates WHERE candidate_id=?", (candidate_id,)).fetchone():
        raise ValueError(f"paper candidate not found: {candidate_id}")
    existing = connection.execute("SELECT candidate_id FROM prediction_paper_links WHERE prediction_id=?", (prediction_id,)).fetchone()
    if existing and existing[0] != candidate_id:
        raise ValueError(f"prediction is already linked to a different candidate: {prediction_id}")
    connection.execute("INSERT OR IGNORE INTO prediction_paper_links VALUES(?,?,?)", (prediction_id, candidate_id, now()))
    return {"prediction_id": prediction_id, "candidate_id": candidate_id}


def record_paper_prediction_outcome(connection: sqlite3.Connection, prediction_id: str, candidate_id: str, realized_label: int, realized_return: float | None = None) -> dict:
    """Persist an explicitly observed manual/paper outcome; never infer one."""
    link_prediction_to_candidate(connection, prediction_id, candidate_id)
    record_outcome(connection, prediction_id, realized_label, realized_return)
    return {"prediction_id": prediction_id, "candidate_id": candidate_id, "realized_label": realized_label, "realized_return": realized_return, "source": "manual_paper_observation"}
