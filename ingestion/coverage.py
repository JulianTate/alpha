"""Deterministic point-in-time coverage and freshness diagnostics."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable


def _parse(value: str) -> datetime:
    text = str(value)
    if len(text) == 10:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def assess_coverage(rows: Iterable[dict[str, Any]], *, symbols: Iterable[str],
                    requested_start: str, requested_end: str,
                    as_of: str | None = None, max_age_days: int | None = None) -> dict[str, Any]:
    """Report observed coverage; never fills gaps or substitutes observations.

    ``as_of`` and ``max_age_days`` are optional freshness controls. They are
    explicit because a daily market calendar cannot be inferred safely here.
    """
    universe = sorted({str(symbol).upper() for symbol in symbols})
    start, end = _parse(requested_start), _parse(requested_end)
    grouped: dict[str, list[datetime]] = {symbol: [] for symbol in universe}
    invalid_rows: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("ticker", row.get("symbol", ""))).upper()
        timestamp = row.get("market_timestamp", row.get("timestamp"))
        if symbol not in grouped or not timestamp:
            invalid_rows.append({"symbol": symbol, "timestamp": timestamp, "reason": "unknown_symbol_or_missing_timestamp"})
            continue
        try:
            grouped[symbol].append(_parse(str(timestamp)))
        except ValueError:
            invalid_rows.append({"symbol": symbol, "timestamp": timestamp, "reason": "invalid_timestamp"})
    items = []
    reference = _parse(as_of) if as_of else None
    for symbol in universe:
        timestamps = sorted(grouped[symbol])
        in_range = [stamp for stamp in timestamps if start <= stamp <= end]
        latest = max(in_range) if in_range else None
        earliest = min(in_range) if in_range else None
        status = "MISSING" if not in_range else ("COVERED" if earliest <= start and latest >= end else "PARTIAL")
        age_days = None
        if reference and latest:
            age_days = (reference - latest).total_seconds() / 86400
            if age_days < 0:
                status = "INVALID_FUTURE_OBSERVATION"
            elif max_age_days is not None and age_days > max_age_days:
                status = "STALE"
        items.append({"symbol": symbol, "status": status, "observed_rows": len(in_range),
                      "observed_start": earliest.isoformat() if earliest else None,
                      "observed_end": latest.isoformat() if latest else None,
                      "age_days": age_days})
    blocked = [item for item in items if item["status"] != "COVERED"]
    return {
        "schema_version": 1, "status": "READY" if universe and not blocked else "DATA_INCOMPLETE",
        "requested_start": requested_start, "requested_end": requested_end,
        "as_of": as_of, "max_age_days": max_age_days, "universe": universe,
        "items": items, "invalid_rows": invalid_rows,
        "summary": {"symbols": len(universe), "covered": len(items) - len(blocked), "blocked": len(blocked), "invalid_rows": len(invalid_rows)},
        "guardrails": ["No interpolation", "No provider substitution", "No inferred market calendar", "Missing and stale observations remain explicit"],
    }
