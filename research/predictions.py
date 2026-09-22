"""Deterministic prediction objects and immutable model/version lineage."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .registry import canonical_hash, now


@dataclass(frozen=True)
class ModelVersion:
    """Immutable computational lineage for a model version."""

    model_version: str
    model_family: str
    code_version: str
    feature_definition_hash: str
    training_dataset_id: str
    parameters: dict[str, Any]
    parent_model_version: str | None = None
    status: str = "RESEARCH"

    def body(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.body())

    def as_dict(self) -> dict[str, Any]:
        return self.body() | {"definition_hash": self.definition_hash}


@dataclass(frozen=True)
class Prediction:
    """A model/strategy forecast, not an execution instruction."""

    prediction_id: str
    experiment_id: str
    dataset_id: str
    ticker: str
    as_of: str
    horizon: int
    direction: str
    score: float
    model_version: str
    feature_snapshot_hash: str
    status: str = "UNSCORED"

    def body(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.body())

    def as_dict(self) -> dict[str, Any]:
        return self.body() | {"definition_hash": self.definition_hash}


def ensure_prediction_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""CREATE TABLE IF NOT EXISTS model_versions(
        model_version TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        model_family TEXT NOT NULL,
        code_version TEXT NOT NULL,
        feature_definition_hash TEXT NOT NULL,
        training_dataset_id TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        parent_model_version TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS predictions(
        prediction_id TEXT PRIMARY KEY,
        definition_hash TEXT UNIQUE NOT NULL,
        experiment_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        as_of TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        direction TEXT NOT NULL,
        score REAL NOT NULL,
        model_version TEXT NOT NULL,
        feature_snapshot_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        model_definition_hash TEXT
    );""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(predictions)")}
    if "model_definition_hash" not in columns:
        connection.execute("ALTER TABLE predictions ADD COLUMN model_definition_hash TEXT")


def register_model_version(connection: sqlite3.Connection, model: ModelVersion) -> dict[str, Any]:
    ensure_prediction_tables(connection)
    existing = connection.execute(
        "SELECT definition_hash FROM model_versions WHERE model_version=?", (model.model_version,)
    ).fetchone()
    if existing and existing[0] != model.definition_hash:
        raise ValueError(f"model version already exists with a different definition: {model.model_version}")
    connection.execute(
        """INSERT OR IGNORE INTO model_versions
        (model_version,definition_hash,model_family,code_version,feature_definition_hash,
         training_dataset_id,parameters_json,parent_model_version,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (model.model_version, model.definition_hash, model.model_family, model.code_version,
         model.feature_definition_hash, model.training_dataset_id,
         json.dumps(model.parameters, sort_keys=True, separators=(",", ":")),
         model.parent_model_version, model.status, now()),
    )
    return model.as_dict()


def get_model_version(connection: sqlite3.Connection, model_version: str) -> dict[str, Any] | None:
    ensure_prediction_tables(connection)
    row = connection.execute("SELECT * FROM model_versions WHERE model_version=?", (model_version,)).fetchone()
    if not row:
        return None
    columns = [item[0] for item in connection.execute("SELECT * FROM model_versions LIMIT 0").description]
    result = dict(zip(columns, row))
    result["parameters"] = json.loads(result.pop("parameters_json"))
    return result


def list_model_versions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_prediction_tables(connection)
    rows = connection.execute("SELECT model_version FROM model_versions ORDER BY model_version").fetchall()
    return [get_model_version(connection, row[0]) for row in rows]


def persist_prediction(connection: sqlite3.Connection, prediction: Prediction) -> dict[str, Any]:
    ensure_prediction_tables(connection)
    model = get_model_version(connection, prediction.model_version)
    existing = connection.execute(
        "SELECT definition_hash FROM predictions WHERE prediction_id=?", (prediction.prediction_id,)
    ).fetchone()
    if existing and existing[0] != prediction.definition_hash:
        raise ValueError(f"prediction id already exists with a different definition: {prediction.prediction_id}")
    connection.execute(
        """INSERT OR IGNORE INTO predictions
        (prediction_id,definition_hash,experiment_id,dataset_id,ticker,as_of,horizon,
         direction,score,model_version,feature_snapshot_hash,status,created_at,model_definition_hash)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (prediction.prediction_id, prediction.definition_hash, prediction.experiment_id,
         prediction.dataset_id, prediction.ticker.upper(), prediction.as_of,
         prediction.horizon, prediction.direction, prediction.score, prediction.model_version,
         prediction.feature_snapshot_hash, prediction.status, now(),
         model["definition_hash"] if model else None),
    )
    return prediction.as_dict() | {"model_definition_hash": model["definition_hash"] if model else None}


def get_prediction(connection: sqlite3.Connection, prediction_id: str) -> dict[str, Any] | None:
    ensure_prediction_tables(connection)
    row = connection.execute("SELECT * FROM predictions WHERE prediction_id=?", (prediction_id,)).fetchone()
    if not row:
        return None
    columns = [item[0] for item in connection.execute("SELECT * FROM predictions LIMIT 0").description]
    return dict(zip(columns, row))
