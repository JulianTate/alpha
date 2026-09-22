"""Champion/challenger shadow validation over paper observations.

This compares declared prediction records with observed paper outcomes. It does
not select a live champion or authorize execution.
"""
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from .registry import canonical_hash, now


def ensure_shadow_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS shadow_validation_runs(
        run_id TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        champion_version TEXT NOT NULL,
        challenger_version TEXT NOT NULL,
        sample_count INTEGER NOT NULL,
        champion_accuracy REAL NOT NULL,
        challenger_accuracy REAL NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def _brier(rows: list[dict[str, Any]], field: str) -> float:
    return round(sum((row[field] - row["realized_label"]) ** 2 for row in rows) / len(rows), 8)


def compare_champion_challenger(connection: sqlite3.Connection, *, champion_version: str,
                                 challenger_version: str, observations: list[dict[str, Any]],
                                 run_id: str | None = None) -> dict[str, Any]:
    """Compare fixed predictions on the same observed sample.

    Each observation requires champion_probability, challenger_probability, and
    realized_label. Duplicate sample keys are rejected so the comparison is
    explicitly paired and cannot silently overweight one observation.
    """
    if not champion_version.strip() or not challenger_version.strip():
        raise ValueError("champion and challenger versions are required")
    if champion_version == challenger_version:
        raise ValueError("champion and challenger versions must differ")
    if not observations:
        raise ValueError("shadow validation requires observations")
    normalized = []
    keys = set()
    for index, row in enumerate(observations):
        try:
            label = int(row["realized_label"])
            champion = float(row["champion_probability"])
            challenger = float(row["challenger_probability"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid shadow observation {index}: {exc}") from exc
        key = str(row.get("key", index))
        if key in keys:
            raise ValueError(f"duplicate shadow observation key: {key}")
        keys.add(key)
        if not all(math.isfinite(value) for value in (champion, challenger)):
            raise ValueError(f"non-finite probability in shadow observation {index}")
        if label not in (0, 1) or not 0 <= champion <= 1 or not 0 <= challenger <= 1:
            raise ValueError(f"invalid probability or label in shadow observation {index}")
        normalized.append({"key": key, "realized_label": label, "champion_probability": champion, "challenger_probability": challenger})
    champion_accuracy = sum((row["champion_probability"] >= .5) == bool(row["realized_label"]) for row in normalized) / len(normalized)
    challenger_accuracy = sum((row["challenger_probability"] >= .5) == bool(row["realized_label"]) for row in normalized) / len(normalized)
    normalized.sort(key=lambda row: row["key"])
    definition = {"champion_version": champion_version, "challenger_version": challenger_version, "observations": normalized}
    digest = canonical_hash(definition)
    decision = "CHALLENGER_OUTPERFORMS_DESCRIPTIVELY" if challenger_accuracy > champion_accuracy else "NO_CHALLENGER_ADVANTAGE_SHOWN"
    result = {"run_id": run_id or f"SHADOW-{digest[:16].upper()}", "definition_hash": digest, "champion_version": champion_version, "challenger_version": challenger_version, "sample_count": len(normalized), "paired_sample": True, "champion_accuracy": round(champion_accuracy, 8), "challenger_accuracy": round(challenger_accuracy, 8), "champion_brier": _brier(normalized, "champion_probability"), "challenger_brier": _brier(normalized, "challenger_probability"), "decision": decision, "promotion_authorized": False, "live_execution": False, "manual_review_required": True}
    ensure_shadow_tables(connection)
    existing = connection.execute("SELECT definition_hash FROM shadow_validation_runs WHERE run_id=?", (result["run_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"shadow run already exists with a different definition: {result['run_id']}")
    connection.execute("INSERT OR IGNORE INTO shadow_validation_runs VALUES(?,?,?,?,?,?,?,?,?)", (result["run_id"], digest, champion_version, challenger_version, len(normalized), result["champion_accuracy"], result["challenger_accuracy"], json.dumps({**result, "observations": normalized}, sort_keys=True), now()))
    return result
