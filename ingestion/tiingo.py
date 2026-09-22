"""Tiingo market-data provider.

Credentials are read only at request time from TIINGO_API_KEY. The key is sent
in an HTTP header and is never included in returned metadata, exceptions,
logs, snapshots, or database records.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from .data_engine import ProviderCapability
from .http import get_json
from .snapshot import save as save_snapshot

BASE_URL = "https://api.tiingo.com"

CAPABILITY = ProviderCapability(
    provider="tiingo",
    max_history="provider/account dependent; measured from metadata and responses",
    symbol_limits="one symbol per historical request; provider endpoint dependent",
    request_limits="account dependent",
    rate_limits="account dependent; HTTP 429 handled by shared client",
    interval_support="daily endpoint implemented; intraday not assumed",
    corporate_action_support="metadata/actions endpoint must be validated per account",
    adjusted_or_raw_support="Tiingo daily endpoint supplies adjusted fields where available; raw fields preserved",
    point_in_time_support="historical observations are available; point-in-time listing universe is not assumed",
    licensing_and_use_restrictions="account/provider terms apply; do not redistribute without verification",
)


def _key() -> str:
    value = os.getenv("TIINGO_API_KEY", "")
    if not value.strip():
        raise RuntimeError("TIINGO_API_KEY is not configured for this process")
    return value.strip()


def _headers() -> dict[str, str]:
    return {"Authorization": f"Token {_key()}", "Accept": "application/json"}


def _date(value: str) -> str:
    if "T" in value:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()


def _canonical(symbol: str, row: dict, retrieved_at: str) -> dict:
    def number(name: str):
        value = row.get(name)
        return float(value) if value is not None else None

    return {
        "timestamp": _date(str(row["date"])),
        "market_timestamp": _date(str(row["date"])),
        "symbol": symbol.upper(),
        "provider_symbol": symbol.upper(),
        "open": number("open"),
        "high": number("high"),
        "low": number("low"),
        "close": number("close"),
        "adjusted_close": number("adjClose"),
        "volume": number("volume") or 0.0,
        "source": "tiingo",
        "retrieved_at": retrieved_at,
    }


def health_check() -> dict:
    started = time.perf_counter()
    try:
        payload, metadata = get_json(f"{BASE_URL}/api/test", headers=_headers(), min_interval=0.0, retries=1)
        return {"provider": "tiingo", "status": "OK", "http_status": metadata.get("http_status"), "latency_ms": round((time.perf_counter() - started) * 1000, 2), "response_shape": type(payload).__name__}
    except Exception as exc:
        return {"provider": "tiingo", "status": "BLOCKED", "error_type": type(exc).__name__, "error": str(exc)[:240], "latency_ms": round((time.perf_counter() - started) * 1000, 2)}


def get_metadata(symbol: str) -> dict:
    payload, _ = get_json(f"{BASE_URL}/tiingo/daily/{quote(symbol.upper())}", headers=_headers(), min_interval=0.0, retries=2)
    if not isinstance(payload, dict):
        raise ValueError("Tiingo metadata response was not an object")
    safe = {key: payload.get(key) for key in ("ticker", "name", "exchangeCode", "description", "startDate", "endDate") if key in payload}
    return safe


def get_history(symbol: str, start: str, end: str) -> dict:
    symbol = symbol.upper()
    url = f"{BASE_URL}/tiingo/daily/{quote(symbol)}/prices?startDate={quote(start)}&endDate={quote(end)}&format=json"
    payload, metadata = get_json(url, headers=_headers(), min_interval=0.0, retries=3, backoff=1.0)
    if not isinstance(payload, list):
        raise ValueError("Tiingo history response was not a list")
    retrieved_at = metadata.get("received_at") or datetime.now(timezone.utc).isoformat()
    rows = [_canonical(symbol, row, retrieved_at) for row in payload]
    snapshot_metadata = dict(metadata)
    snapshot_metadata.pop("authorization", None)
    snapshot_path = save_snapshot("market-tiingo", {"symbol": symbol, "start": start, "end": end, "rows": rows}, snapshot_metadata)
    return {"status": "ok", "provider": "tiingo", "ticker": symbol, "count": len(rows), "rows": rows, "metadata": {"url": url, "received_at": retrieved_at, "http_status": metadata.get("http_status"), "snapshot_path": snapshot_path}}


def get_corporate_actions(symbol: str, start: str, end: str) -> dict:
    url = f"{BASE_URL}/tiingo/daily/{quote(symbol.upper())}/prices?startDate={quote(start)}&endDate={quote(end)}&format=json"
    payload, metadata = get_json(url, headers=_headers(), min_interval=0.0, retries=2)
    actions = []
    for row in payload if isinstance(payload, list) else []:
        if row.get("divCash") not in (None, 0, 0.0):
            actions.append({"type": "DIVIDEND", "date": row.get("date"), "amount": row.get("divCash")})
        if row.get("splitFactor") not in (None, 1, 1.0):
            actions.append({"type": "SPLIT", "date": row.get("date"), "factor": row.get("splitFactor")})
    return {"provider": "tiingo", "ticker": symbol.upper(), "actions": actions, "http_status": metadata.get("http_status")}
