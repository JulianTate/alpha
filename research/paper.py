"""Paper-only candidate and monitoring workflow.

This module creates reviewable candidates and records manual observations. It
never submits broker orders or represents a candidate as a live position.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_paper_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS paper_candidates(
        candidate_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, strategy TEXT NOT NULL,
        direction TEXT NOT NULL, signal_timestamp TEXT NOT NULL, entry_reference REAL,
        stop_price REAL, target_price REAL, rationale_json TEXT NOT NULL,
        source_run_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS paper_observations(
        id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES paper_candidates(candidate_id),
        observed_at TEXT NOT NULL, observed_price REAL, action TEXT NOT NULL,
        manual_fill_price REAL, notes TEXT, created_at TEXT NOT NULL
    );
    """)


def create_candidate(connection: sqlite3.Connection, result: dict, *, source_run_id: str | None = None) -> dict:
    if result.get("direction") not in {"BUY", "SELL"}:
        raise ValueError("only actionable scanner directions can become paper candidates")
    if result.get("confidence_band") not in {"RESEARCH_CANDIDATE", "WEAK_OR_MIXED"}:
        raise ValueError("insufficient-evidence results cannot become paper candidates")
    body = {"ticker": result["ticker"].upper(), "strategy": "scanner-consensus-v1", "direction": result["direction"], "signal_timestamp": result["timestamp"], "entry_reference": result.get("entry_price"), "stop_price": result.get("stop_price"), "target_price": result.get("target_price"), "rationale": result.get("signals", []), "warnings": result.get("warnings", [])}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    candidate_id = f"PAPER-{digest[:16].upper()}"
    connection.execute("INSERT OR IGNORE INTO paper_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (candidate_id, body["ticker"], body["strategy"], body["direction"], body["signal_timestamp"], body["entry_reference"], body["stop_price"], body["target_price"], json.dumps({"signals": body["rationale"], "warnings": body["warnings"]}, sort_keys=True), source_run_id, "PENDING_REVIEW", _now()))
    return {"candidate_id": candidate_id, "status": "PENDING_REVIEW", **body}


def record_observation(connection: sqlite3.Connection, candidate_id: str, action: str, observed_price: float | None = None, manual_fill_price: float | None = None, notes: str = "") -> dict:
    allowed = {"REVIEWED", "MANUAL_ENTRY", "MANUAL_EXIT", "REJECTED", "EXPIRED"}
    if action not in allowed:
        raise ValueError(f"invalid paper observation action: {action}")
    if not connection.execute("SELECT 1 FROM paper_candidates WHERE candidate_id=?", (candidate_id,)).fetchone():
        raise ValueError("paper candidate not found")
    connection.execute("INSERT INTO paper_observations(candidate_id,observed_at,observed_price,action,manual_fill_price,notes,created_at) VALUES(?,?,?,?,?,?,?)", (candidate_id, _now(), observed_price, action, manual_fill_price, notes, _now()))
    next_status = {"REVIEWED": "REVIEWED", "MANUAL_ENTRY": "OPEN_MANUAL", "MANUAL_EXIT": "CLOSED_MANUAL", "REJECTED": "REJECTED", "EXPIRED": "EXPIRED"}[action]
    connection.execute("UPDATE paper_candidates SET status=? WHERE candidate_id=?", (next_status, candidate_id))
    return {"candidate_id": candidate_id, "status": next_status, "action": action}


def paper_report(connection: sqlite3.Connection) -> dict:
    candidates = [dict(row) for row in connection.execute("SELECT candidate_id,ticker,direction,signal_timestamp,entry_reference,stop_price,target_price,status,created_at FROM paper_candidates ORDER BY created_at DESC")]
    observations = [dict(row) for row in connection.execute("SELECT candidate_id,observed_at,action,observed_price,manual_fill_price,notes FROM paper_observations ORDER BY observed_at DESC")]
    return {"paper_only": True, "live_orders": False, "candidates": candidates, "observations": observations, "counts": {"candidates": len(candidates), "observations": len(observations), "open_manual": sum(row["status"] == "OPEN_MANUAL" for row in candidates)}}
