"""Deterministic regime diagnostics and portfolio concentration controls."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def classify_regime(*, trend_return: float | None, volatility: float | None, trend_threshold: float = 0.0, high_volatility: float = 0.03) -> str:
    if trend_return is None or volatility is None:
        return "UNRESOLVED"
    if volatility >= high_volatility:
        return "HIGH_VOLATILITY_UP" if trend_return > trend_threshold else "HIGH_VOLATILITY_DOWN"
    return "LOW_VOLATILITY_UP" if trend_return > trend_threshold else "LOW_VOLATILITY_DOWN"


def concentration_report(positions: Iterable[dict[str, Any]], *, max_position_weight: float = 0.20, max_sector_weight: float = 0.35) -> dict[str, Any]:
    rows = [dict(item) for item in positions]
    total = sum(max(0.0, float(item.get("weight", 0.0))) for item in rows)
    if total <= 0:
        return {"status": "INSUFFICIENT_EVIDENCE", "total_weight": 0.0, "position_checks": [], "sector_checks": [], "violations": ["no positive position weights"]}
    sectors = defaultdict(float)
    position_checks = []
    for item in rows:
        weight = max(0.0, float(item.get("weight", 0.0))) / total
        ticker = str(item.get("ticker", "")).upper()
        sector = str(item.get("sector", "UNCLASSIFIED"))
        sectors[sector] += weight
        position_checks.append({"ticker": ticker, "weight": weight, "within_limit": weight <= max_position_weight})
    sector_checks = [{"sector": sector, "weight": weight, "within_limit": weight <= max_sector_weight} for sector, weight in sorted(sectors.items())]
    violations = [f"position:{x['ticker']}" for x in position_checks if not x["within_limit"]] + [f"sector:{x['sector']}" for x in sector_checks if not x["within_limit"]]
    return {"status": "PASS" if not violations else "BLOCKED", "total_weight": total, "position_checks": position_checks, "sector_checks": sector_checks, "violations": violations, "limits": {"max_position_weight": max_position_weight, "max_sector_weight": max_sector_weight}, "manual_review_required": True}
