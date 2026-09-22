"""Optional OpenBB bridge for Alpha.

OpenBB is deliberately optional: Alpha remains runnable with its validated
Tiingo/SEC/FRED/GDELT adapters and standard-library core. This module only
normalizes OpenBB results into Alpha-shaped observations; callers must still
run Alpha validation and create/freeze datasets before research use.

No credentials are accepted as arguments or persisted here. Provider
configuration belongs to OpenBB's own environment/configuration boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class OpenBBCapability:
    provider: str = "openbb"
    integration: str = "optional-adapter"
    point_in_time: str = "caller-must-verify-per-provider"
    raw_snapshot_required: bool = True
    alpha_validation_required: bool = True


CAPABILITY = OpenBBCapability()


def availability() -> dict:
    """Report whether the optional package is importable without importing it at module load."""
    try:
        import openbb  # type: ignore  # noqa: F401
    except ImportError:
        return {"status": "not_installed", "provider": "openbb", "install_required": True}
    return {"status": "available", "provider": "openbb", "install_required": False}


def _value(item: Any, *names: str) -> Any:
    if isinstance(item, dict):
        for name in names:
            if name in item and item[name] is not None:
                return item[name]
    for name in names:
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return result.isoformat()
    text = str(value)
    if not text:
        return None
    return text if "T" in text else f"{text}T00:00:00+00:00"


def normalize_price_rows(items: Iterable[Any], *, source: str = "openbb") -> list[dict]:
    """Convert OpenBB provider output to canonical Alpha OHLCV rows.

    This function does not repair missing fields or sort rows. Alpha's normal
    validation is intentionally the next step.
    """
    rows = []
    for item in items:
        timestamp = _iso(_value(item, "date", "timestamp", "datetime", "time"))
        rows.append({
            "market_timestamp": timestamp,
            "open": _value(item, "open", "Open"),
            "high": _value(item, "high", "High"),
            "low": _value(item, "low", "Low"),
            "close": _value(item, "close", "Close", "adj_close", "adjusted_close"),
            "volume": _value(item, "volume", "Volume"),
            "source": source,
        })
    return rows


def normalize_news_rows(items: Iterable[Any], *, source: str = "openbb") -> list[dict]:
    """Convert provider news records to discovery metadata without copying article bodies."""
    rows = []
    for item in items:
        rows.append({
            "title": _value(item, "title", "headline"),
            "url": _value(item, "url", "link"),
            "source": source,
            "published_at": _iso(_value(item, "published", "published_at", "date", "datetime")),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def guarded_result(items: Iterable[Any], *, kind: str, source: str = "openbb") -> dict:
    """Return normalized data with explicit integration gates for callers/reports."""
    normalized = normalize_price_rows(items, source=source) if kind == "prices" else normalize_news_rows(items, source=source)
    return {
        "status": "UNVALIDATED",
        "provider": "openbb",
        "kind": kind,
        "rows": normalized,
        "gates": ["alpha_validate_rows", "persist_raw_snapshot", "record_provenance", "verify_point_in_time", "freeze_dataset_before_research"],
    }
