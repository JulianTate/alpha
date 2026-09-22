"""Deterministic out-of-sample prediction scorecards and calibration diagnostics.

This module records observed labels separately from prediction creation. It does
not promote strategies or imply profitability; callers must supply a declared,
locked evaluation sample.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .predictions import ensure_prediction_tables
from .registry import canonical_hash, now


CALIBRATION_BIN_COUNT = 5


def ensure_scorecard_tables(connection: sqlite3.Connection) -> None:
    ensure_prediction_tables(connection)
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS prediction_outcomes(
        prediction_id TEXT PRIMARY KEY REFERENCES predictions(prediction_id),
        realized_label INTEGER NOT NULL CHECK(realized_label IN (0,1)),
        realized_return REAL,
        observed_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS prediction_scorecards(
        scorecard_id TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        experiment_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        sample_count INTEGER NOT NULL,
        accuracy REAL NOT NULL,
        brier_score REAL NOT NULL,
        calibration_json TEXT NOT NULL,
        definition_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        evaluation_scope TEXT NOT NULL DEFAULT 'OOS',
        status TEXT NOT NULL DEFAULT 'COMPLETE',
        expected_minimum INTEGER NOT NULL DEFAULT 1,
        expected_max_as_of TEXT,
        expected_min_as_of TEXT,
        expected_model_versions_json TEXT NOT NULL DEFAULT '[]',
        expected_calibration_error REAL,
        max_calibration_error REAL
    );
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(prediction_scorecards)")}
    migrations = {
        "evaluation_scope": "TEXT NOT NULL DEFAULT 'OOS'",
        "status": "TEXT NOT NULL DEFAULT 'COMPLETE'",
        "expected_minimum": "INTEGER NOT NULL DEFAULT 1",
        "expected_max_as_of": "TEXT",
        "expected_min_as_of": "TEXT",
        "expected_model_versions_json": "TEXT NOT NULL DEFAULT '[]'",
        "expected_calibration_error": "REAL",
        "max_calibration_error": "REAL",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE prediction_scorecards ADD COLUMN {name} {definition}")


def record_outcome(connection: sqlite3.Connection, prediction_id: str, realized_label: int, realized_return: float | None = None) -> None:
    ensure_scorecard_tables(connection)
    if realized_label not in (0, 1):
        raise ValueError("realized_label must be 0 or 1")
    if not connection.execute("SELECT 1 FROM predictions WHERE prediction_id=?", (prediction_id,)).fetchone():
        raise ValueError(f"prediction not found: {prediction_id}")
    existing = connection.execute("SELECT realized_label,realized_return FROM prediction_outcomes WHERE prediction_id=?", (prediction_id,)).fetchone()
    if existing and (existing[0] != realized_label or existing[1] != realized_return):
        raise ValueError(f"prediction outcome already exists with a different label: {prediction_id}")
    connection.execute("INSERT OR IGNORE INTO prediction_outcomes VALUES(?,?,?,?)", (prediction_id, realized_label, realized_return, now()))


def _calibration(observations: list[tuple[str, float, int]]) -> tuple[dict[str, dict[str, float | int]], float, float]:
    bins = {str(index): {"count": 0, "predicted_mean": 0.0, "observed_rate": 0.0, "absolute_error": 0.0} for index in range(CALIBRATION_BIN_COUNT)}
    for _, probability, label in observations:
        bucket = min(CALIBRATION_BIN_COUNT - 1, int(probability * CALIBRATION_BIN_COUNT))
        item = bins[str(bucket)]
        item["count"] += 1
        item["predicted_mean"] += probability
        item["observed_rate"] += label
    nonempty: list[tuple[int, float]] = []
    for item in bins.values():
        if item["count"]:
            item["predicted_mean"] = round(float(item["predicted_mean"]) / int(item["count"]), 8)
            item["observed_rate"] = round(float(item["observed_rate"]) / int(item["count"]), 8)
            item["absolute_error"] = round(abs(float(item["predicted_mean"]) - float(item["observed_rate"])), 8)
            nonempty.append((int(item["count"]), float(item["absolute_error"])))
    total = sum(count for count, _ in nonempty)
    ece = sum(count * error for count, error in nonempty) / total if total else 0.0
    maximum = max((error for _, error in nonempty), default=0.0)
    return bins, round(ece, 8), round(maximum, 8)


def build_scorecard(
    connection: sqlite3.Connection,
    experiment_id: str,
    dataset_id: str,
    *,
    scorecard_id: str | None = None,
    evaluation_scope: str = "OOS",
    minimum_observations: int = 1,
    min_as_of: str | None = None,
    max_as_of: str | None = None,
    model_versions: list[str] | None = None,
) -> dict[str, Any]:
    """Build an immutable scorecard from a declared, locked evaluation sample.

    Predictions outside the optional as-of range or model-version set are not
    silently included. Fewer than ``minimum_observations`` yields an explicit
    INSUFFICIENT_DATA result and is still persisted for auditability.
    """
    ensure_scorecard_tables(connection)
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be at least 1")
    scope = evaluation_scope.strip().upper()
    if not scope:
        raise ValueError("evaluation_scope must not be empty")
    clauses = ["p.experiment_id=?", "p.dataset_id=?"]
    params: list[Any] = [experiment_id, dataset_id]
    if min_as_of is not None:
        clauses.append("p.as_of>=?"); params.append(min_as_of)
    if max_as_of is not None:
        clauses.append("p.as_of<=?"); params.append(max_as_of)
    if model_versions:
        placeholders = ",".join("?" for _ in model_versions)
        clauses.append(f"p.model_version IN ({placeholders})"); params.extend(sorted(set(model_versions)))
    rows = connection.execute(f"""SELECT p.prediction_id,p.direction,p.score,p.as_of,p.model_version,o.realized_label
        FROM predictions p JOIN prediction_outcomes o ON o.prediction_id=p.prediction_id
        WHERE {' AND '.join(clauses)} ORDER BY p.prediction_id""", params).fetchall()
    observations: list[tuple[str, float, int]] = []
    selected_metadata: list[tuple[str, str, str]] = []
    for prediction_id, direction, score, as_of, model_version, label in rows:
        probability = float(score) if direction.upper() in ("LONG", "BUY", "UP") else 1.0 - float(score)
        probability = min(1.0, max(0.0, probability))
        observations.append((prediction_id, probability, int(label)))
        selected_metadata.append((prediction_id, as_of, model_version))
    bins, ece, max_error = _calibration(observations)
    sample_count = len(observations)
    status = "COMPLETE" if sample_count >= minimum_observations else "INSUFFICIENT_DATA"
    prediction_ids = [item[0] for item in observations]
    definition = {
        "experiment_id": experiment_id, "dataset_id": dataset_id, "evaluation_scope": scope,
        "minimum_observations": minimum_observations, "min_as_of": min_as_of, "max_as_of": max_as_of,
        "model_versions": sorted(set(model_versions or [])), "prediction_ids": prediction_ids,
        "calibration_bins": bins, "status": status,
    }
    digest = canonical_hash(definition)
    result = {
        "scorecard_id": scorecard_id or f"SCORE-{digest[:16].upper()}", "definition_hash": digest,
        "experiment_id": experiment_id, "dataset_id": dataset_id, "evaluation_scope": scope,
        "status": status, "expected_minimum": minimum_observations, "sample_count": sample_count,
        "accuracy": round(sum((probability >= 0.5) == bool(label) for _, probability, label in observations) / sample_count, 8) if observations else 0.0,
        "brier_score": round(sum((probability - label) ** 2 for _, probability, label in observations) / sample_count, 8) if observations else 0.0,
        "calibration": bins, "expected_calibration_error": ece, "max_calibration_error": max_error,
    }
    existing = connection.execute("SELECT definition_hash FROM prediction_scorecards WHERE scorecard_id=?", (result["scorecard_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"scorecard id already exists with a different definition: {result['scorecard_id']}")
    connection.execute("""INSERT OR IGNORE INTO prediction_scorecards
        (scorecard_id,definition_hash,experiment_id,dataset_id,sample_count,accuracy,brier_score,
         calibration_json,definition_json,created_at,evaluation_scope,status,expected_minimum,
         expected_max_as_of,expected_min_as_of,expected_model_versions_json,expected_calibration_error,max_calibration_error)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        result["scorecard_id"], digest, experiment_id, dataset_id, sample_count, result["accuracy"], result["brier_score"],
        json.dumps(bins, sort_keys=True), json.dumps(definition, sort_keys=True), now(), scope, status, minimum_observations,
        max_as_of, min_as_of, json.dumps(sorted(set(model_versions or []))), ece, max_error))
    return result


def get_scorecard(connection: sqlite3.Connection, scorecard_id: str) -> dict[str, Any] | None:
    ensure_scorecard_tables(connection)
    row = connection.execute("SELECT * FROM prediction_scorecards WHERE scorecard_id=?", (scorecard_id,)).fetchone()
    if not row:
        return None
    columns = [item[0] for item in connection.execute("SELECT * FROM prediction_scorecards LIMIT 0").description]
    result = dict(zip(columns, row))
    for field in ("calibration_json", "definition_json", "expected_model_versions_json"):
        key = field.removesuffix("_json")
        result[key] = json.loads(result.pop(field))
    return result


def list_scorecards(connection: sqlite3.Connection, experiment_id: str | None = None, dataset_id: str | None = None) -> list[dict[str, Any]]:
    ensure_scorecard_tables(connection)
    clauses: list[str] = []
    params: list[Any] = []
    if experiment_id is not None:
        clauses.append("experiment_id=?"); params.append(experiment_id)
    if dataset_id is not None:
        clauses.append("dataset_id=?"); params.append(dataset_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    ids = connection.execute(f"SELECT scorecard_id FROM prediction_scorecards{where} ORDER BY scorecard_id", params).fetchall()
    return [get_scorecard(connection, row[0]) for row in ids]
