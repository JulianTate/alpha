"""Deterministic comparative baseline scorecards.

Baselines are context diagnostics, never profitability or promotion evidence.
Inputs must be sourced from a frozen, point-in-time dataset. Missing baseline
series remain explicit as INSUFFICIENT_DATA rather than being repaired.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .registry import canonical_hash


BASELINE_NAMES = ("RANDOM", "BUY_AND_HOLD", "FACTOR", "TECHNICAL")


def _score(returns: list[float], *, dataset_id: str, benchmark_name: str, cost_bps: float, source_field: str, minimum_observations: int) -> dict[str, Any]:
    definition = {
        "schema_version": 2, "dataset_id": dataset_id, "benchmark_name": benchmark_name,
        "source_field": source_field, "cost_bps": cost_bps, "minimum_observations": minimum_observations,
        "returns": [round(value, 12) for value in returns],
    }
    digest = canonical_hash(definition)
    if len(returns) < minimum_observations:
        return {
            "scorecard_id": f"BASE-{digest[:16].upper()}", "definition_hash": digest,
            "dataset_id": dataset_id, "benchmark_name": benchmark_name, "status": "INSUFFICIENT_DATA",
            "sample_count": len(returns), "minimum_observations": minimum_observations,
            "cost_bps": cost_bps, "costs_explicit": True, "comparative_only": True,
            "limitations": ["Insufficient observations; no baseline comparison is valid."],
        }
    cumulative = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        cumulative *= 1.0 + value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, (peak - cumulative) / peak)
    return {
        "scorecard_id": f"BASE-{digest[:16].upper()}", "definition_hash": digest,
        "dataset_id": dataset_id, "benchmark_name": benchmark_name, "status": "COMPLETE",
        "sample_count": len(returns), "minimum_observations": minimum_observations,
        "average_return": sum(returns) / len(returns), "win_rate": sum(value > 0 for value in returns) / len(returns),
        "cumulative_return": cumulative - 1.0, "max_drawdown": max_drawdown,
        "cost_bps": cost_bps, "costs_explicit": True, "comparative_only": True,
        "limitations": ["Baseline diagnostics do not establish an investable edge or profitability.", "Inputs must be sourced from a frozen, point-in-time dataset."],
    }


def build_baseline_suite(rows: Iterable[dict[str, Any]], *, dataset_id: str, cost_bps: float, minimum_observations: int = 20, random_seed: str = "RANDOM-V1") -> dict[str, Any]:
    """Build fixed random, benchmark, factor, and technical diagnostics.

    ``cost_bps`` and ``random_seed`` are mandatory reproducibility inputs. Each
    optional series is independently assessed; absent or malformed fields yield
    an explicit insufficient-data scorecard. Random is a deterministic signed
    null using a hash of the seed and observation timestamp.
    """
    if cost_bps < 0 or minimum_observations < 1 or not random_seed:
        raise ValueError("cost_bps must be non-negative, minimum_observations positive, and random_seed non-empty")
    observations = sorted((dict(row) for row in rows), key=lambda row: str(row.get("timestamp", row.get("as_of", ""))))
    fee = float(cost_bps) / 10000.0
    series: dict[str, list[float]] = {name: [] for name in BASELINE_NAMES}
    required = {"BUY_AND_HOLD": "benchmark_return", "FACTOR": "factor_return", "TECHNICAL": "technical_return"}
    for row in observations:
        timestamp = str(row.get("timestamp", row.get("as_of", "")))
        for name, field in required.items():
            value = row.get(field)
            if isinstance(value, (int, float)) and value == value:
                series[name].append(float(value) - fee)
        asset = row.get("asset_return")
        if isinstance(asset, (int, float)) and asset == asset:
            digest = hashlib.sha256(f"{random_seed}|{timestamp}".encode()).digest()
            sign = 1.0 if digest[0] % 2 else -1.0
            series["RANDOM"].append(sign * abs(float(asset)) - fee)
    scorecards = {}
    fields = {"RANDOM": "asset_return", **required}
    for name in BASELINE_NAMES:
        scorecards[name] = _score(series[name], dataset_id=dataset_id, benchmark_name=name, cost_bps=cost_bps, source_field=fields[name], minimum_observations=minimum_observations)
    definition = {"schema_version": 1, "dataset_id": dataset_id, "cost_bps": cost_bps, "minimum_observations": minimum_observations, "random_seed": random_seed, "scorecard_hashes": {name: scorecards[name]["definition_hash"] for name in BASELINE_NAMES}}
    return {"dataset_id": dataset_id, "status": "COMPLETE" if all(item["status"] == "COMPLETE" for item in scorecards.values()) else "INSUFFICIENT_DATA", "cost_bps": cost_bps, "random_seed": random_seed, "comparative_only": True, "definition_hash": canonical_hash(definition), "scorecards": scorecards}


def build_baseline_scorecard(rows: Iterable[dict[str, Any]], *, dataset_id: str, benchmark_name: str = "BUY_AND_HOLD") -> dict[str, Any]:
    """Backward-compatible single benchmark diagnostic for already net returns."""
    observations = sorted((dict(row) for row in rows), key=lambda row: str(row.get("timestamp", row.get("as_of", ""))))
    if not observations:
        raise ValueError("baseline requires observations from a frozen dataset")
    returns = []
    for row in observations:
        if row.get("net_return") is None:
            raise ValueError("baseline observations require net_return")
        returns.append(float(row["net_return"]))
    result = _score(returns, dataset_id=dataset_id, benchmark_name=benchmark_name, cost_bps=0.0, source_field="net_return", minimum_observations=1)
    result["costs_included"] = all("cost_included" in row for row in observations)
    return result
