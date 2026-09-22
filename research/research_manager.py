"""Deterministic research-manager retry, resume, and append-only checkpoint state."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from .registry import canonical_hash, now


ALLOWED_STATES = {"PLANNED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"}
ALLOWED_TRANSITIONS = {
    "PLANNED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"PAUSED", "FAILED", "COMPLETED", "CANCELLED"},
    "PAUSED": {"RUNNING", "FAILED", "CANCELLED"},
    "FAILED": {"RUNNING", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def ensure_manager_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS research_manager_jobs(
        job_id TEXT PRIMARY KEY, definition_hash TEXT UNIQUE NOT NULL,
        definition_json TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER NOT NULL,
        checkpoint_json TEXT NOT NULL, last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS research_manager_checkpoints(
        checkpoint_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, sequence INTEGER NOT NULL,
        state TEXT NOT NULL, completed_steps_json TEXT NOT NULL, checkpoint_hash TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(job_id, sequence)
    );
    """)


def create_job(connection: sqlite3.Connection, definition: dict[str, Any]) -> dict[str, Any]:
    required = {"campaign_id", "experiment_id", "dataset_id", "steps"}
    missing = required - definition.keys()
    if missing:
        raise ValueError(f"research job missing required fields: {sorted(missing)}")
    steps = list(definition["steps"])
    if not steps or any(not str(step) for step in steps):
        raise ValueError("research job requires non-empty steps")
    body = {**definition, "steps": [str(step) for step in steps]}
    digest = canonical_hash(body)
    job_id = f"JOB-{digest[:16].upper()}"
    timestamp = now()
    existing = connection.execute("SELECT definition_hash FROM research_manager_jobs WHERE job_id=?", (job_id,)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"research job already exists with a different definition: {job_id}")
    connection.execute("INSERT OR IGNORE INTO research_manager_jobs VALUES(?,?,?,?,?,?,?,?,?)", (job_id, digest, json.dumps(body, sort_keys=True), "PLANNED", 0, json.dumps({"completed_steps": []}), None, timestamp, timestamp))
    return {"job_id": job_id, "definition_hash": digest, "state": "PLANNED", "attempt": 0, "steps": body["steps"]}


def transition_job(connection: sqlite3.Connection, job_id: str, state: str, *, error: str | None = None) -> dict[str, Any]:
    if state not in ALLOWED_STATES:
        raise ValueError(f"invalid research job state: {state}")
    row = connection.execute("SELECT state,attempt,checkpoint_json FROM research_manager_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("research job not found")
    current_state = row[0]
    if state != current_state and state not in ALLOWED_TRANSITIONS[current_state]:
        raise ValueError(f"invalid research job transition: {current_state} -> {state}")
    attempt = int(row[1]) + (1 if state == "RUNNING" and current_state != "RUNNING" else 0)
    connection.execute("UPDATE research_manager_jobs SET state=?,attempt=?,last_error=?,updated_at=? WHERE job_id=?", (state, attempt, error, now(), job_id))
    return {"job_id": job_id, "state": state, "attempt": attempt, "last_error": error}


def _append_checkpoint(connection: sqlite3.Connection, job_id: str, state: str, completed: list[str]) -> None:
    payload = {"job_id": job_id, "sequence": connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM research_manager_checkpoints WHERE job_id=?", (job_id,)).fetchone()[0], "state": state, "completed_steps": completed}
    digest = canonical_hash(payload)
    connection.execute("INSERT INTO research_manager_checkpoints VALUES(?,?,?,?,?,?,?)", (f"CHK-{digest[:16].upper()}", job_id, payload["sequence"], state, json.dumps(completed), digest, now()))


def checkpoint_job(connection: sqlite3.Connection, job_id: str, completed_steps: list[str], *, state: str = "PAUSED") -> dict[str, Any]:
    row = connection.execute("SELECT definition_json FROM research_manager_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("research job not found")
    definition = json.loads(row[0]); allowed = set(definition["steps"]); completed = [str(step) for step in completed_steps]
    if any(step not in allowed for step in completed) or len(set(completed)) != len(completed):
        raise ValueError("checkpoint contains unknown or duplicate steps")
    if state not in {"PAUSED", "COMPLETED"}:
        raise ValueError("checkpoint state must be PAUSED or COMPLETED")
    current = connection.execute("SELECT state,checkpoint_json FROM research_manager_jobs WHERE job_id=?", (job_id,)).fetchone()
    current_state = current[0]
    if state == "PAUSED" and current_state not in {"PLANNED", "RUNNING", "PAUSED"}:
        raise ValueError(f"cannot pause job from state {current_state}")
    if state == "COMPLETED":
        if set(completed) != set(definition["steps"]) or len(completed) != len(definition["steps"]):
            raise ValueError("completed checkpoint must contain every declared step exactly once")
        if current_state not in {"RUNNING", "PAUSED"}:
            raise ValueError(f"cannot complete job from state {current_state}")
    previous = json.loads(current[1]).get("completed_steps", [])
    if any(step not in completed for step in previous):
        raise ValueError("checkpoint cannot remove previously completed steps")
    _append_checkpoint(connection, job_id, state, completed)
    connection.execute("UPDATE research_manager_jobs SET state=?,checkpoint_json=?,updated_at=? WHERE job_id=?", (state, json.dumps({"completed_steps": completed}, sort_keys=True), now(), job_id))
    return {"job_id": job_id, "state": state, "completed_steps": completed, "remaining_steps": [step for step in definition["steps"] if step not in completed]}


def resume_job(connection: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT state,attempt,definition_json,checkpoint_json FROM research_manager_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("research job not found")
    if row[0] not in {"PLANNED", "PAUSED", "FAILED"}:
        raise ValueError(f"job cannot resume from state {row[0]}")
    definition, checkpoint = json.loads(row[2]), json.loads(row[3])
    transition_job(connection, job_id, "RUNNING")
    completed = checkpoint.get("completed_steps", [])
    return {"job_id": job_id, "state": "RUNNING", "attempt": int(row[1]) + 1, "completed_steps": completed, "remaining_steps": [step for step in definition["steps"] if step not in completed]}


def execute_job(connection: sqlite3.Connection, job_id: str, handlers: dict[str, Callable[[], Any]]) -> dict[str, Any]:
    """Execute only unfinished declared steps; persist a checkpoint after each success.

    A handler cannot authorize promotion or execution. Failures remain FAILED and
    are resumable; completed steps are never rerun on a later attempt.
    """
    started = resume_job(connection, job_id)
    completed = list(started["completed_steps"])
    steps = started["remaining_steps"]
    try:
        for step in steps:
            if step not in handlers:
                raise ValueError(f"missing handler for research step: {step}")
            handlers[step]()
            completed.append(step)
            checkpoint_job(connection, job_id, completed, state="PAUSED")
        checkpoint_job(connection, job_id, completed, state="COMPLETED")
        return {"job_id": job_id, "state": "COMPLETED", "attempt": started["attempt"], "completed_steps": completed, "remaining_steps": []}
    except Exception as exc:
        transition_job(connection, job_id, "FAILED", error=str(exc))
        return {"job_id": job_id, "state": "FAILED", "attempt": started["attempt"], "completed_steps": completed, "remaining_steps": [step for step in steps if step not in completed], "last_error": str(exc)}
