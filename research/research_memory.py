"""Deterministic, searchable research memory with explicit provenance."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .registry import canonical_hash, now

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def ensure_research_memory_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS research_memory_records(
        record_id TEXT PRIMARY KEY, record_hash TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL, record_type TEXT NOT NULL,
        as_of TEXT NOT NULL, source_refs_json TEXT NOT NULL,
        tags_json TEXT NOT NULL, created_at TEXT NOT NULL,
        manual_review_required INTEGER NOT NULL, numerical_authority INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_research_memory_type_asof
        ON research_memory_records(record_type, as_of);
    CREATE TABLE IF NOT EXISTS research_memory_provenance_links(
        link_id TEXT PRIMARY KEY, link_hash TEXT UNIQUE NOT NULL,
        record_id TEXT NOT NULL, reference_type TEXT NOT NULL,
        reference_id TEXT NOT NULL, relation TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(record_id, reference_type, reference_id, relation)
    );
    CREATE INDEX IF NOT EXISTS ix_research_memory_links_record
        ON research_memory_provenance_links(record_id);
    """)


def record_memory(
    connection: sqlite3.Connection, *, title: str, body: str,
    record_type: str, as_of: str, source_refs: list[str] | tuple[str, ...] = (),
    tags: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Persist an immutable, descriptive research note with source references."""
    if not title.strip() or not body.strip() or not record_type.strip() or not as_of.strip():
        raise ValueError("title, body, record_type, and as_of are required")
    refs = sorted({str(ref).strip() for ref in source_refs if str(ref).strip()})
    normalized_tags = sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()})
    definition = {"title": title.strip(), "body": body.strip(), "record_type": record_type.strip(),
                  "as_of": as_of.strip(), "source_refs": refs, "tags": normalized_tags}
    digest = canonical_hash(definition)
    result = {"record_id": f"MEM-{digest[:16].upper()}", "record_hash": digest, **definition,
              "manual_review_required": True, "numerical_authority": False}
    existing = connection.execute("SELECT record_hash FROM research_memory_records WHERE record_id=?", (result["record_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError("research memory record changed for existing record ID")
    connection.execute("INSERT OR IGNORE INTO research_memory_records VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (result["record_id"], digest, result["title"], result["body"], result["record_type"],
         result["as_of"], json.dumps(refs), json.dumps(normalized_tags), now(), 1, 0))
    return result


def link_memory_provenance(
    connection: sqlite3.Connection, *, record_id: str, reference_type: str,
    reference_id: str, relation: str = "supports",
) -> dict[str, Any]:
    """Persist an immutable typed link to an existing provenance/evidence ID."""
    values = {"record_id": record_id.strip(), "reference_type": reference_type.strip(),
              "reference_id": reference_id.strip(), "relation": relation.strip()}
    if not all(values.values()):
        raise ValueError("record_id, reference_type, reference_id, and relation are required")
    if not connection.execute("SELECT 1 FROM research_memory_records WHERE record_id=?", (values["record_id"],)).fetchone():
        raise KeyError(f"unknown research memory record: {values['record_id']}")
    digest = canonical_hash(values)
    result = {"link_id": f"MLK-{digest[:16].upper()}", "link_hash": digest, **values}
    existing = connection.execute("SELECT link_hash FROM research_memory_provenance_links WHERE link_id=?", (result["link_id"],)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError("research memory provenance link changed for existing link ID")
    connection.execute("INSERT OR IGNORE INTO research_memory_provenance_links VALUES(?,?,?,?,?,?,?)",
                       (result["link_id"], digest, values["record_id"], values["reference_type"],
                        values["reference_id"], values["relation"], now()))
    return result


def list_memory_provenance_links(connection: sqlite3.Connection, record_id: str) -> list[dict[str, Any]]:
    ensure_research_memory_tables(connection)
    rows = connection.execute("""SELECT link_id,link_hash,record_id,reference_type,reference_id,relation,created_at
        FROM research_memory_provenance_links WHERE record_id=? ORDER BY reference_type, reference_id, relation, link_id""", (record_id,)).fetchall()
    return [{"link_id": row[0], "link_hash": row[1], "record_id": row[2], "reference_type": row[3],
             "reference_id": row[4], "relation": row[5], "created_at": row[6]} for row in rows]


_REFERENCE_TABLES = {
    "provider_retrieval": ("provider_retrieval_evidence", "retrieval_id"),
    "universe_membership": ("universe_membership_evidence", "membership_id"),
    "update_run": ("data_update_run_summaries", "run_id"),
    "reconciliation_report": ("update_reconciliation_reports", "report_id"),
    "retrieval_completeness": ("retrieval_completeness_reports", "report_id"),
}


def validate_memory_provenance_links(connection: sqlite3.Connection, record_id: str) -> list[dict[str, Any]]:
    """Resolve supported links against local immutable provenance tables.

    Validation is descriptive only: unresolved or unsupported references remain
    visible and never become numerical or execution authority.
    """
    links = list_memory_provenance_links(connection, record_id)
    result = []
    for link in links:
        mapping = _REFERENCE_TABLES.get(link["reference_type"])
        if mapping is None:
            status = "UNSUPPORTED"
        else:
            table, id_column = mapping
            row = connection.execute(
                f"SELECT 1 FROM {table} WHERE {id_column}=?", (link["reference_id"],)
            ).fetchone()
            status = "RESOLVED" if row else "UNRESOLVED"
        result.append({**link, "validation_status": status,
                       "manual_review_required": True, "numerical_authority": False,
                       "live_execution": False})
    return result


def search_memory(
    connection: sqlite3.Connection, query: str, *, limit: int = 20,
    record_type: str | None = None, as_of: str | None = None,
    tags: list[str] | tuple[str, ...] = (), include_provenance: bool = False,
) -> list[dict[str, Any]]:
    """Search persisted text with deterministic token ranking and exact filters.

    This is structured retrieval, not semantic inference: filters are exact,
    ordering is stable, and the result remains descriptive and review-only.
    """
    if not query.strip():
        raise ValueError("query is required")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    normalized_type = record_type.strip() if record_type is not None else None
    normalized_as_of = as_of.strip() if as_of is not None else None
    wanted_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
    wanted = _tokens(query)
    rows = connection.execute("SELECT record_id,record_hash,title,body,record_type,as_of,source_refs_json,tags_json,created_at FROM research_memory_records").fetchall()
    results = []
    for row in rows:
        row_tags = set(json.loads(row[7]))
        if normalized_type is not None and row[4] != normalized_type:
            continue
        if normalized_as_of is not None and row[5] != normalized_as_of:
            continue
        if wanted_tags and not wanted_tags.issubset(row_tags):
            continue
        haystack = " ".join([row[2], row[3], row[4], row[5], " ".join(row_tags)])
        overlap = len(wanted & _tokens(haystack))
        if overlap:
            item = {"record_id": row[0], "record_hash": row[1], "title": row[2], "body": row[3],
                    "record_type": row[4], "as_of": row[5], "source_refs": json.loads(row[6]),
                    "tags": sorted(row_tags), "created_at": row[8], "match_count": overlap,
                    "manual_review_required": True, "numerical_authority": False}
            if include_provenance:
                try:
                    provenance = validate_memory_provenance_links(connection, row[0])
                except sqlite3.OperationalError:
                    # A missing local provenance table is unresolved evidence,
                    # never a reason to infer that a link is valid.
                    provenance = [{"validation_status": "UNRESOLVED",
                                   "manual_review_required": True,
                                   "numerical_authority": False,
                                   "live_execution": False}]
                statuses = [entry["validation_status"] for entry in provenance]
                item["provenance"] = provenance
                item["provenance_summary"] = {
                    "link_count": len(provenance),
                    "resolved_count": statuses.count("RESOLVED"),
                    "unresolved_count": statuses.count("UNRESOLVED"),
                    "unsupported_count": statuses.count("UNSUPPORTED"),
                    "overall_status": "RESOLVED" if statuses and all(status == "RESOLVED" for status in statuses)
                                      else "INCOMPLETE",
                    "manual_review_required": True,
                    "numerical_authority": False,
                    "live_execution": False,
                }
            results.append(item)
    return sorted(results, key=lambda item: (-item["match_count"], item["as_of"], item["record_id"]))[:limit]
