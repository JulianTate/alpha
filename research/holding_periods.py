"""Deterministic holding-period diagnostics for research-only comparisons.

The caller supplies point-in-time entries and observed future prices. This module
never fills missing horizons, infers liquidity, or authorizes promotion.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from .backtest import CostModel, simulate_trade


def compare_holding_periods(rows: Iterable[Mapping], horizons: Iterable[int], *,
                            quantity: float = 1.0, cost: CostModel = CostModel(),
                            minimum_observations: int = 20) -> dict:
    """Compare explicit buy-and-hold horizons after costs and participation limits.

    Each row must contain ``entry_price`` and ``exit_prices`` keyed by horizon;
    ``average_volume`` is required when a participation constraint is assessed.
    Missing or malformed observations are excluded and reported, never repaired.
    """
    horizons = tuple(sorted(set(int(h) for h in horizons)))
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    observations = {h: [] for h in horizons}
    excluded = {h: {"missing": 0, "malformed": 0, "liquidity_blocked": 0} for h in horizons}
    for row in rows:
        try:
            entry = float(row["entry_price"])
            volume = row.get("average_volume")
            volume = None if volume is None else float(volume)
            exits = row["exit_prices"]
            if not isinstance(exits, Mapping):
                raise TypeError("exit_prices must be a mapping")
        except (KeyError, TypeError, ValueError):
            for h in horizons: excluded[h]["malformed"] += 1
            continue
        for h in horizons:
            if str(h) in exits: exit_value = exits[str(h)]
            elif h in exits: exit_value = exits[h]
            else:
                excluded[h]["missing"] += 1
                continue
            try:
                exit_price = float(exit_value)
                if entry <= 0 or exit_price <= 0: raise ValueError
                result = simulate_trade("HOLDING-PERIOD", quantity, entry, exit_price, h,
                                        average_volume=volume, cost=cost)
            except ValueError as exc:
                if "liquidity" in str(exc): excluded[h]["liquidity_blocked"] += 1
                else: excluded[h]["malformed"] += 1
                continue
            observations[h].append(result)
    summaries = {}
    for h in horizons:
        results = observations[h]
        if len(results) < minimum_observations:
            summaries[str(h)] = {"status": "INSUFFICIENT_DATA", "observations": len(results),
                                 "minimum_observations": minimum_observations,
                                 "excluded": excluded[h]}
            continue
        net = sum(r.net_pnl for r in results)
        capital_time = sum(r.capital_time_days for r in results)
        summaries[str(h)] = {"status": "COMPLETE", "observations": len(results),
                             "minimum_observations": minimum_observations,
                             "net_pnl": net, "total_cost": sum(r.total_cost for r in results),
                             "win_rate": sum(r.net_pnl > 0 for r in results) / len(results),
                             "net_return_per_capital_day": net / capital_time if capital_time else 0.0,
                             "excluded": excluded[h]}
    return {"status": "COMPLETE" if any(v["status"] == "COMPLETE" for v in summaries.values()) else "INSUFFICIENT_DATA",
            "horizons": summaries, "quantity": quantity,
            "cost_model": {"fee_bps": cost.fee_bps, "half_spread_bps": cost.half_spread_bps,
                           "slippage_bps": cost.slippage_bps, "latency_bps": cost.latency_bps,
                           "max_participation": cost.max_participation}}
