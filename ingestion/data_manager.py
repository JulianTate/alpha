"""Bounded data-management planning for Alpha.

The manager plans and records data work; it never repairs, substitutes, or
claims coverage that is not present. Network acquisition remains explicit via
Alpha's existing provider adapters.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from .coverage import assess_coverage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_manager_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS data_manager_runs(
        run_id TEXT PRIMARY KEY, provider TEXT NOT NULL, requested_start TEXT NOT NULL,
        requested_end TEXT NOT NULL, universe_json TEXT NOT NULL, plan_json TEXT NOT NULL,
        plan_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
    )""")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _query_bound(value: str, *, end: bool = False) -> str:
    # Stored market timestamps are UTC ISO timestamps; date-only requests cover
    # the complete UTC day rather than being truncated at midnight.
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value + ("T23:59:59.999999+00:00" if end else "T00:00:00+00:00")
    return value


def plan_update(connection: sqlite3.Connection, *, symbols: list[str] | None = None,
                start: str, end: str, provider: str = "tiingo") -> dict:
    """Return a deterministic acquisition plan from canonical stored rows."""
    ensure_manager_tables(connection)
    if symbols is None:
        symbols = [r[0] for r in connection.execute("SELECT ticker FROM companies WHERE active=1 ORDER BY ticker")]
    universe = sorted({str(s).upper() for s in symbols})
    query_start, query_end = _query_bound(start), _query_bound(end, end=True)
    start_day, end_day = start[:10], end[:10]
    items = []
    for symbol in universe:
        rows = connection.execute("""SELECT p.market_timestamp
          FROM prices p JOIN securities s ON s.id=p.security_id
          WHERE s.ticker=? AND substr(p.market_timestamp,1,10)>=? AND substr(p.market_timestamp,1,10)<=?
          ORDER BY p.market_timestamp""", (symbol, start_day, end_day)).fetchall()
        timestamps = [row[0] for row in rows]
        first, last, count = (timestamps[0], timestamps[-1], len(timestamps)) if timestamps else (None, None, 0)
        diagnostic = assess_coverage(
            [{"symbol": symbol, "market_timestamp": timestamp} for timestamp in timestamps],
            symbols=[symbol], requested_start=start, requested_end=end,
        )
        status = diagnostic["items"][0]["status"]
        items.append({"symbol": symbol, "status": status, "stored_start": first,
                      "stored_end": last, "stored_rows": count,
                      "requested_start": start, "requested_end": end,
                      "coverage_diagnostic": diagnostic["items"][0],
                      "action": "FETCH_AND_VALIDATE" if status != "COVERED" else "NO_ACTION"})
    blocked = [x for x in items if x["status"] != "COVERED"]
    status = "READY" if universe and not blocked else ("DATA_BLOCKED" if not universe else "DATA_INCOMPLETE")
    plan = {"schema_version": 1, "provider": provider, "requested_start": start,
            "requested_end": end, "universe": universe, "items": items, "status": status,
            "guardrails": ["No provider substitution", "No interpolation or repair", "Validate before persistence", "Freeze only after complete validation"],
            "summary": {"symbols": len(items), "covered": len(items) - len(blocked), "incomplete": len(blocked)}}
    plan_hash = _digest(plan)
    run_id = "DM-" + plan_hash[:16].upper()
    connection.execute("INSERT OR REPLACE INTO data_manager_runs VALUES(?,?,?,?,?,?,?,?,?)",
                       (run_id, provider, start, end, json.dumps(universe), json.dumps(plan, sort_keys=True), plan_hash, status, _now()))
    plan["run_id"] = run_id
    plan["plan_hash"] = plan_hash
    return plan
