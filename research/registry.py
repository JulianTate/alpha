"""Immutable dataset, campaign, and experiment registry primitives."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

CAMPAIGN_STATES = {"PLANNED", "DATA_READY", "RUNNING", "VALIDATED", "REJECTED", "PROMOTED_TO_PAPER", "FROZEN"}
STRATEGY_GENOME_REQUIRED = {"strategy_name", "family", "parameters", "feature_definition", "signal_definition", "cost_model"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ensure_registry_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS campaigns(
        campaign_id TEXT PRIMARY KEY, definition_hash TEXT UNIQUE NOT NULL,
        state TEXT NOT NULL, definition_json TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS experiments(
        experiment_id TEXT PRIMARY KEY, definition_hash TEXT UNIQUE NOT NULL,
        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
        definition_json TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS research_runs(
        run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
        code_version TEXT, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
        result_json TEXT
    );
    CREATE TABLE IF NOT EXISTS strategy_genomes(
        genome_id TEXT PRIMARY KEY, definition_hash TEXT UNIQUE NOT NULL,
        parent_genome_id TEXT REFERENCES strategy_genomes(genome_id),
        definition_json TEXT NOT NULL, created_at TEXT NOT NULL
    );
    """)


def create_campaign(connection: sqlite3.Connection, definition: dict) -> dict:
    required = {"research_question", "dataset_id", "universe", "train_period", "validation_period", "test_period"}
    missing = required - definition.keys()
    if missing:
        raise ValueError(f"campaign missing required fields: {sorted(missing)}")
    body = dict(definition)
    digest = canonical_hash(body)
    campaign_id = f"CAM-{digest[:16].upper()}"
    timestamp = now()
    connection.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,?)", (campaign_id, digest, "PLANNED", json.dumps(body, sort_keys=True), timestamp, timestamp))
    return {"campaign_id": campaign_id, "definition_hash": digest, "state": "PLANNED"}


def transition_campaign(connection: sqlite3.Connection, campaign_id: str, state: str) -> None:
    if state not in CAMPAIGN_STATES:
        raise ValueError(f"invalid campaign state: {state}")
    row = connection.execute("SELECT state FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if not row:
        raise ValueError("campaign not found")
    connection.execute("UPDATE campaigns SET state=?,updated_at=? WHERE campaign_id=?", (state, now(), campaign_id))


def create_experiment(connection: sqlite3.Connection, campaign_id: str, definition: dict) -> dict:
    if not connection.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone():
        raise ValueError("campaign not found")
    body = dict(definition)
    body["campaign_id"] = campaign_id
    required = {"strategy_version", "parameters", "dataset_id", "cost_model", "slippage_model", "engine_version"}
    missing = required - body.keys()
    if missing:
        raise ValueError(f"experiment missing required fields: {sorted(missing)}")
    digest = canonical_hash(body)
    experiment_id = f"EXP-{digest[:16].upper()}"
    connection.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?)", (experiment_id, digest, campaign_id, json.dumps(body, sort_keys=True), "REGISTERED", None, now()))
    return {"experiment_id": experiment_id, "definition_hash": digest, "campaign_id": campaign_id, "status": "REGISTERED"}


def register_strategy_genome(connection: sqlite3.Connection, definition: dict, parent_genome_id: str | None = None) -> dict:
    """Register an immutable strategy definition and optional parent lineage link."""
    missing = STRATEGY_GENOME_REQUIRED - definition.keys()
    if missing:
        raise ValueError(f"strategy genome missing required fields: {sorted(missing)}")
    if parent_genome_id and not connection.execute("SELECT 1 FROM strategy_genomes WHERE genome_id=?", (parent_genome_id,)).fetchone():
        raise ValueError("parent strategy genome not found")
    body = dict(definition)
    if parent_genome_id:
        body["parent_genome_id"] = parent_genome_id
    digest = canonical_hash(body)
    genome_id = f"GEN-{digest[:16].upper()}"
    existing = connection.execute("SELECT definition_hash,definition_json,parent_genome_id FROM strategy_genomes WHERE genome_id=?", (genome_id,)).fetchone()
    if existing:
        if existing[0] != digest:
            raise ValueError(f"strategy genome already exists with a different definition: {genome_id}")
        return {"genome_id": genome_id, "definition_hash": digest, "parent_genome_id": existing[2], "definition": json.loads(existing[1])}
    connection.execute("INSERT INTO strategy_genomes VALUES(?,?,?,?,?)", (genome_id, digest, parent_genome_id, json.dumps(body, sort_keys=True), now()))
    return {"genome_id": genome_id, "definition_hash": digest, "parent_genome_id": parent_genome_id, "definition": body}


def list_strategy_genomes(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("SELECT genome_id,definition_hash,parent_genome_id,definition_json,created_at FROM strategy_genomes ORDER BY created_at,genome_id").fetchall()
    return [{"genome_id": r[0], "definition_hash": r[1], "parent_genome_id": r[2], "definition": json.loads(r[3]), "created_at": r[4]} for r in rows]


def freeze_dataset_record(connection: sqlite3.Connection, metadata: dict, quality_status: str) -> dict:
    if quality_status != "VALID":
        raise ValueError(f"cannot freeze dataset with quality status {quality_status}")
    connection.execute("UPDATE datasets SET status=? WHERE dataset_id=?", ("FROZEN", metadata["dataset_id"]))
    return {"dataset_id": metadata["dataset_id"], "dataset_hash": metadata["dataset_hash"], "status": "FROZEN"}
