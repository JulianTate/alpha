"""Reproducible baseline campaign orchestration.

This module deliberately runs one predeclared strategy configuration. It does
not search parameters, tune on the final OOS period, or promote results to
paper automatically.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone

from .execution import ExecutionConfig, OHLCV, Signal, run_backtest
from .registry import create_campaign, create_experiment, now, transition_campaign
from .strategy_scan import Bar, strategy_signals, _atr
from .walk_forward import declared_fold_contract

BASELINE_STRATEGY = "technical-consensus-v1"
BASELINE_PARAMETERS = {"sma_fast": 20, "sma_slow": 50, "rsi": 14, "ema_fast": 12, "ema_slow": 26, "donchian": 20, "stop_atr": 1.5, "target_atr": 2.5}


def _parse(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _bars(connection: sqlite3.Connection, ticker: str) -> list[Bar]:
    rows = connection.execute("""SELECT p.market_timestamp,p.open,p.high,p.low,p.close,p.volume
        FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies c ON c.id=s.company_id
        WHERE c.ticker=? ORDER BY p.market_timestamp""", (ticker,)).fetchall()
    return [Bar(r[0], float(r[4]), float(r[2] or r[4]), float(r[3] or r[4]), float(r[5] or 0)) for r in rows]


def _execution_bars(bars: list[Bar]) -> list[OHLCV]:
    return [OHLCV(b.timestamp, float(b.close), float(b.high or b.close), float(b.low or b.close), float(b.close), float(b.volume)) for b in bars]


def _signals(bars: list[Bar]) -> list[Signal]:
    output = []
    for index in range(50, len(bars)):
        history = bars[: index + 1]
        candidates = strategy_signals(history)
        buys = [item for item in candidates if item.direction == "BUY"]
        sells = [item for item in candidates if item.direction == "SELL"]
        if len(buys) <= len(sells) or not buys:
            continue
        atr = _atr(history)
        if not atr or atr <= 0:
            continue
        price = history[-1].close
        output.append(Signal(history[-1].timestamp, "BUY", price - 1.5 * atr, price + 2.5 * atr))
    return output


def _period_rows(bars: list[Bar], start: str, end: str) -> list[Bar]:
    lo, hi = _parse(start), _parse(end)
    return [bar for bar in bars if lo <= _parse(bar.timestamp) < hi]


def run_baseline(connection: sqlite3.Connection, dataset_id: str, universe: list[str], periods: dict[str, tuple[str, str]]) -> dict:
    """Register and run a fixed baseline campaign over declared periods."""
    fold_contract = declared_fold_contract(periods)
    campaign_definition = {
        "research_question": "Does a fixed multi-indicator technical consensus remain useful after costs and slippage?",
        "dataset_id": dataset_id,
        "universe": sorted(symbol.upper() for symbol in universe),
        "train_period": list(periods["train"]),
        "validation_period": list(periods["validation"]),
        "test_period": list(periods["test"]),
        "selection_rule": "No parameter selection; baseline is predeclared.",
        "final_oos_locked": True,
        "walk_forward_contract": fold_contract,
    }
    campaign = create_campaign(connection, campaign_definition)
    experiment = create_experiment(connection, campaign["campaign_id"], {
        "strategy_version": BASELINE_STRATEGY,
        "parameters": BASELINE_PARAMETERS,
        "dataset_id": dataset_id,
        "cost_model": {"fee_bps": 1, "spread_bps": 5},
        "slippage_model": {"slippage_bps": 5, "execution": "next_open"},
        "engine_version": "daily-execution-v1",
    })
    transition_campaign(connection, campaign["campaign_id"], "DATA_READY")
    transition_campaign(connection, campaign["campaign_id"], "RUNNING")
    run_id = "RUN-" + uuid.uuid4().hex[:16].upper()
    started = now()
    connection.execute("INSERT INTO research_runs(run_id,experiment_id,code_version,started_at,status) VALUES(?,?,?,?,?)", (run_id, experiment["experiment_id"], _code_version(), started, "RUNNING"))
    results = {}
    try:
        for name, (start, end) in periods.items():
            period_results = []
            for ticker in sorted(set(symbol.upper() for symbol in universe)):
                all_bars = _bars(connection, ticker)
                selected = _period_rows(all_bars, start, end)
                if len(selected) < 60:
                    period_results.append({"ticker": ticker, "status": "INSUFFICIENT_EVIDENCE", "bars": len(selected)})
                    continue
                result = run_backtest(_execution_bars(selected), _signals(selected), ExecutionConfig())
                period_results.append({"ticker": ticker, "status": result["status"], "bars": len(selected), "metrics": result["metrics"], "ending_cash": result["ending_cash"]})
            results[name] = period_results
        payload = {"campaign": campaign, "experiment": experiment, "run_id": run_id, "strategy_version": BASELINE_STRATEGY, "walk_forward": fold_contract, "results": results}
        connection.execute("UPDATE research_runs SET finished_at=?,status=?,result_json=? WHERE run_id=?", (now(), "COMPLETED", json.dumps(payload, sort_keys=True), run_id))
        connection.execute("UPDATE experiments SET status=?,result_json=? WHERE experiment_id=?", ("COMPLETED", json.dumps(payload, sort_keys=True), experiment["experiment_id"]))
        transition_campaign(connection, campaign["campaign_id"], "VALIDATED")
        return payload
    except Exception:
        connection.execute("UPDATE research_runs SET finished_at=?,status=? WHERE run_id=?", (now(), "FAILED", run_id))
        transition_campaign(connection, campaign["campaign_id"], "REJECTED")
        raise
