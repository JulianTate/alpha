"""Provider-neutral, reproducible market-data foundation for Alpha.

This module deliberately rejects bad observations. It never interpolates,
repairs, or invents OHLCV rows. Provider adapters return canonical rows and
this engine validates them before persistence.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    max_history: str
    symbol_limits: str
    request_limits: str
    rate_limits: str
    interval_support: str
    corporate_action_support: str
    adjusted_or_raw_support: str
    point_in_time_support: str
    licensing_and_use_restrictions: str


@dataclass(frozen=True)
class QualityIssue:
    status: str  # VALID, INVALID, UNRESOLVED
    check: str
    detail: str
    timestamp: str | None = None


class MarketDataProvider(Protocol):
    name: str
    capability: ProviderCapability

    def fetch(self, symbol: str, start: str, end: str) -> dict:
        ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_rows(rows: Iterable[dict]) -> list[QualityIssue]:
    """Return issues without changing the supplied observations.

    Repeated timestamps are invalid. If repeated observations also disagree on
    canonical market values, the conflict is reported explicitly rather than
    selecting a provider, averaging values, or silently overwriting a row.
    """
    issues: list[QualityIssue] = []
    previous = None
    seen: set[str] = set()
    seen_values: dict[str, tuple[object, ...]] = {}
    for index, row in enumerate(rows):
        ts = str(row.get("market_timestamp") or row.get("timestamp") or "")
        if not ts:
            issues.append(QualityIssue("INVALID", "missing_timestamp", f"row {index}"))
            continue
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            issues.append(QualityIssue("INVALID", "malformed_timestamp", ts, ts))
            continue
        if ts in seen:
            issues.append(QualityIssue("INVALID", "duplicate_timestamp", ts, ts))
            current_values = tuple(row.get(name) for name in ("open", "high", "low", "close", "volume"))
            if current_values != seen_values.get(ts):
                issues.append(QualityIssue("UNRESOLVED", "conflicting_observation",
                                           f"timestamp {ts} has incompatible canonical values", ts))
        else:
            seen_values[ts] = tuple(row.get(name) for name in ("open", "high", "low", "close", "volume"))
        seen.add(ts)
        if previous is not None and ts <= previous:
            issues.append(QualityIssue("INVALID", "unsorted_timestamp", f"{previous} then {ts}", ts))
        previous = ts
        try:
            close = float(row["close"])
            values = {name: float(row[name]) for name in ("open", "high", "low") if row.get(name) is not None}
            volume = float(row.get("volume") or 0)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(QualityIssue("INVALID", "non_numeric_ohlcv", str(exc), ts))
            continue
        numeric_values = (close, volume, *values.values())
        if not all(math.isfinite(value) for value in numeric_values):
            issues.append(QualityIssue("INVALID", "non_finite_value", "prices and volume must be finite", ts))
            continue
        if close <= 0 or any(value <= 0 for value in values.values()) or volume < 0:
            issues.append(QualityIssue("INVALID", "non_positive_value", "prices must be positive and volume non-negative", ts))
        high, low = values.get("high"), values.get("low")
        if high is not None and low is not None:
            if low > high or ("open" in values and not low <= values["open"] <= high) or not low <= close <= high:
                issues.append(QualityIssue("INVALID", "ohlc_bounds", "low <= open/close <= high failed", ts))
    if not issues:
        issues.append(QualityIssue("VALID", "dataset_integrity", "all supplied rows passed canonical checks"))
    return issues


def freeze_dataset(provider_composition: list[str], rows: list[dict], *, start: str, end: str, adjustment_policy: str) -> dict:
    payload = {"rows": rows, "provider_composition": provider_composition, "start": start, "end": end, "adjustment_policy": adjustment_policy, "schema_version": "market-v1"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"dataset_id": f"DS-{digest[:16].upper()}", "dataset_hash": digest, "dataset_version": "market-v1", "provider_composition": provider_composition, "coverage_start": start, "coverage_end": end, "adjustment_policy": adjustment_policy, "row_count": len(rows), "created_at": utc_now()}


def ensure_data_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS provider_capabilities(provider TEXT PRIMARY KEY, capability_json TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS provider_health(provider TEXT PRIMARY KEY, last_success TEXT, last_failure TEXT, success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, average_latency_ms REAL, observed_coverage TEXT, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS datasets(dataset_id TEXT PRIMARY KEY, dataset_hash TEXT UNIQUE NOT NULL, dataset_version TEXT NOT NULL, provider_composition_json TEXT NOT NULL, coverage_start TEXT, coverage_end TEXT, adjustment_policy TEXT NOT NULL, row_count INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS data_quality_runs(id INTEGER PRIMARY KEY, dataset_id TEXT, source TEXT NOT NULL, status TEXT NOT NULL, issues_json TEXT NOT NULL, checked_at TEXT NOT NULL);
    """)


def record_capability(connection: sqlite3.Connection, capability: ProviderCapability) -> None:
    connection.execute("INSERT OR REPLACE INTO provider_capabilities VALUES(?,?,?)", (capability.provider, json.dumps(asdict(capability), sort_keys=True), utc_now()))


def record_dataset(connection: sqlite3.Connection, metadata: dict, status: str = "FROZEN") -> None:
    connection.execute("INSERT OR IGNORE INTO datasets VALUES(?,?,?,?,?,?,?,?,?,?)", (metadata["dataset_id"], metadata["dataset_hash"], metadata["dataset_version"], json.dumps(metadata["provider_composition"]), metadata["coverage_start"], metadata["coverage_end"], metadata["adjustment_policy"], metadata["row_count"], status, metadata["created_at"]))


def verify_stored_prices(connection: sqlite3.Connection) -> dict:
    rows = [dict(row) for row in connection.execute("SELECT security_id,market_timestamp,open,high,low,close,volume FROM prices ORDER BY security_id,market_timestamp")]
    if not rows:
        issue = QualityIssue("UNRESOLVED", "no_observations", "no canonical market observations are available")
        return {"status": "UNRESOLVED", "row_count": 0, "issues": [asdict(issue)]}
    issues: list[QualityIssue] = []
    security_ids = sorted({row.get("security_id") for row in rows})
    for security_id in security_ids:
        security_rows = [{key: value for key, value in row.items() if key != "security_id"} for row in rows if row.get("security_id") == security_id]
        issues.extend(validate_rows(security_rows))
    invalid = [asdict(issue) for issue in issues if issue.status == "INVALID"]
    unresolved = [asdict(issue) for issue in issues if issue.status == "UNRESOLVED"]
    status = "INVALID" if invalid else ("UNRESOLVED" if unresolved else "VALID")
    return {"status": status, "row_count": len(rows), "security_count": len(security_ids), "issues": [asdict(issue) for issue in issues]}
