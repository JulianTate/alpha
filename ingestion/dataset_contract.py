"""Point-in-time dataset reconstruction and provenance contracts."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from research.registry import canonical_hash, now


REQUIRED_FIELDS = {
    "dataset_id", "universe_definition", "as_of_policy", "corporate_action_policy",
    "survivorship_policy", "source_snapshot_hash", "quality_status",
}


def ensure_dataset_contract_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS dataset_reconstruction_records(
        dataset_id TEXT PRIMARY KEY,
        contract_hash TEXT UNIQUE NOT NULL,
        universe_json TEXT NOT NULL,
        as_of_policy TEXT NOT NULL,
        corporate_action_policy TEXT NOT NULL,
        survivorship_policy TEXT NOT NULL,
        source_snapshot_hash TEXT NOT NULL,
        quality_status TEXT NOT NULL,
        reconstruction_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def register_dataset_contract(connection: sqlite3.Connection, metadata: dict[str, Any]) -> dict[str, Any]:
    """Register an immutable, explicit reconstruction contract.

    This records assumptions; it does not repair data or assert that a provider
    actually supports point-in-time reconstruction.
    """
    missing = REQUIRED_FIELDS - metadata.keys()
    if missing:
        raise ValueError(f"dataset contract missing required fields: {sorted(missing)}")
    if metadata["quality_status"] != "VALID":
        raise ValueError("dataset contract requires quality_status VALID")
    universe = sorted({str(item).upper() for item in metadata["universe_definition"]})
    if not universe:
        raise ValueError("dataset contract requires a non-empty universe")
    body = {
        "dataset_id": str(metadata["dataset_id"]),
        "universe_definition": universe,
        "as_of_policy": str(metadata["as_of_policy"]),
        "corporate_action_policy": str(metadata["corporate_action_policy"]),
        "survivorship_policy": str(metadata["survivorship_policy"]),
        "source_snapshot_hash": str(metadata["source_snapshot_hash"]),
        "quality_status": str(metadata["quality_status"]),
    }
    for evidence_key in ("capability_report", "coverage_report"):
        if evidence_key in metadata:
            body[evidence_key] = metadata[evidence_key]
    digest = canonical_hash(body)
    ensure_dataset_contract_tables(connection)
    existing = connection.execute(
        "SELECT contract_hash FROM dataset_reconstruction_records WHERE dataset_id=?",
        (body["dataset_id"],),
    ).fetchone()
    if existing and existing[0] != digest:
        raise ValueError(f"dataset contract already exists with a different definition: {body['dataset_id']}")
    connection.execute(
        """INSERT OR IGNORE INTO dataset_reconstruction_records
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (body["dataset_id"], digest, json.dumps(universe), body["as_of_policy"],
         body["corporate_action_policy"], body["survivorship_policy"],
         body["source_snapshot_hash"], body["quality_status"],
         json.dumps(body, sort_keys=True), now()),
    )
    return {**body, "contract_hash": digest}
