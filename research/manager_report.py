"""Operator-facing reports for deterministic research-manager recovery state."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .research_manager import ensure_manager_tables


def recovery_report(connection: sqlite3.Connection) -> dict[str, Any]:
    """Summarize persisted jobs and actionable recovery state without executing jobs."""
    ensure_manager_tables(connection)
    rows = connection.execute("""SELECT job_id,definition_json,state,attempt,checkpoint_json,last_error,created_at,updated_at
        FROM research_manager_jobs ORDER BY updated_at DESC,job_id""").fetchall()
    jobs = []
    for row in rows:
        definition = json.loads(row[1])
        checkpoint = json.loads(row[4])
        completed = checkpoint.get("completed_steps", [])
        steps = definition.get("steps", [])
        jobs.append({
            "job_id": row[0], "campaign_id": definition.get("campaign_id"),
            "experiment_id": definition.get("experiment_id"), "dataset_id": definition.get("dataset_id"),
            "state": row[2], "attempt": row[3], "completed_steps": completed,
            "remaining_steps": [step for step in steps if step not in completed],
            "last_error": row[5], "updated_at": row[7],
            "action_required": row[2] in {"FAILED", "PAUSED"},
        })
    counts = {state: sum(job["state"] == state for job in jobs) for state in ("PLANNED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED")}
    return {
        "schema_version": 1,
        "jobs": jobs,
        "counts": counts,
        "action_required_jobs": [job["job_id"] for job in jobs if job["action_required"]],
        "execution_performed": False,
        "limitations": ["Report is observational; it does not retry or resume jobs.", "Operator review remains required for failures and paused work."],
    }
