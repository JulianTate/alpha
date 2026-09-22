"""Deterministic daily-bar paper backtest engine.

Signals are generated after a completed bar and can execute no earlier than the
next bar. Daily OHLC cannot reveal intrabar order, so when stop and target are
both touched the conservative stop is used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class OHLCV:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    timestamp: str
    direction: str = "BUY"
    stop: float | None = None
    target: float | None = None


@dataclass(frozen=True)
class ExecutionConfig:
    initial_cash: float = 100_000.0
    risk_fraction: float = 0.01
    max_position_fraction: float = 0.25
    fee_bps: float = 1.0
    spread_bps: float = 5.0
    slippage_bps: float = 5.0
    max_participation: float = 0.10


@dataclass(frozen=True)
class Fill:
    signal_timestamp: str
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    total_cost: float
    net_pnl: float
    exit_reason: str


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


def _cost(notional: float, config: ExecutionConfig) -> float:
    return notional * (config.fee_bps + config.spread_bps + config.slippage_bps) / 10_000.0


def _entry_price(open_price: float, config: ExecutionConfig) -> float:
    return open_price * (1 + (config.spread_bps + config.slippage_bps) / 10_000.0)


def _exit_price(price: float, config: ExecutionConfig) -> float:
    return price * (1 - (config.spread_bps + config.slippage_bps) / 10_000.0)


def run_backtest(bars: Iterable[OHLCV], signals: Iterable[Signal], config: ExecutionConfig = ExecutionConfig()) -> dict:
    """Run long-only next-session execution with one position at a time."""
    bars = sorted(tuple(bars), key=lambda bar: _time(bar.timestamp))
    signals_by_time = {signal.timestamp: signal for signal in signals}
    if not bars:
        return {"status": "NO_DATA", "fills": [], "ending_cash": config.initial_cash, "metrics": {"trades": 0}}
    cash = float(config.initial_cash)
    fills: list[Fill] = []
    equity_curve = []
    position = None
    for index, bar in enumerate(bars):
        if position is not None:
            signal, entry_bar, entry, quantity = position
            stop = signal.stop
            target = signal.target
            exit_raw = None
            reason = None
            if bar.open <= (stop if stop is not None else float("-inf")):
                exit_raw, reason = bar.open, "STOP_GAP"
            elif bar.open >= (target if target is not None else float("inf")):
                exit_raw, reason = bar.open, "TARGET_GAP"
            elif stop is not None and target is not None and bar.low <= stop and bar.high >= target:
                exit_raw, reason = stop, "STOP_CONSERVATIVE_AMBIGUITY"
            elif stop is not None and bar.low <= stop:
                exit_raw, reason = stop, "STOP"
            elif target is not None and bar.high >= target:
                exit_raw, reason = target, "TARGET"
            if exit_raw is not None:
                exit = _exit_price(exit_raw, config)
                gross = (exit - entry) * quantity
                total_cost = _cost(entry * quantity, config) + _cost(exit * quantity, config)
                net = gross - total_cost
                cash += entry * quantity + gross - total_cost
                fills.append(Fill(signal.timestamp, entry_bar.timestamp, bar.timestamp, entry, exit, quantity, gross, total_cost, net, reason))
                position = None
        if position is None and index > 0:
            prior = bars[index - 1]
            signal = signals_by_time.get(prior.timestamp)
            if signal and signal.direction == "BUY" and bar.open > 0:
                entry = _entry_price(bar.open, config)
                stop_distance = entry - signal.stop if signal.stop is not None else entry * 0.05
                # A gap below the planned stop is still executable; size it
                # conservatively using a fallback risk distance rather than
                # dropping the trade.
                if stop_distance <= 0:
                    stop_distance = entry * 0.05
                risk_budget = cash * config.risk_fraction
                quantity = min(risk_budget / stop_distance, cash * config.max_position_fraction / entry)
                if bar.volume > 0:
                    quantity = min(quantity, bar.volume * config.max_participation)
                if quantity <= 0:
                    continue
                cash -= entry * quantity + _cost(entry * quantity, config)
                position = (signal, bar, entry, quantity)
                # The position was entered at this session's open. Daily OHLC
                # can therefore resolve a stop/target touched later in the
                # same bar, conservatively when both are touched.
                same_bar_exit = None
                same_bar_reason = None
                if bar.open <= (signal.stop if signal.stop is not None else float('-inf')):
                    same_bar_exit, same_bar_reason = bar.open, 'STOP_GAP'
                elif bar.open >= (signal.target if signal.target is not None else float('inf')):
                    same_bar_exit, same_bar_reason = bar.open, 'TARGET_GAP'
                elif signal.stop is not None and signal.target is not None and bar.low <= signal.stop and bar.high >= signal.target:
                    same_bar_exit, same_bar_reason = signal.stop, 'STOP_CONSERVATIVE_AMBIGUITY'
                elif signal.stop is not None and bar.low <= signal.stop:
                    same_bar_exit, same_bar_reason = signal.stop, 'STOP'
                elif signal.target is not None and bar.high >= signal.target:
                    same_bar_exit, same_bar_reason = signal.target, 'TARGET'
                if same_bar_exit is not None:
                    exit_price = _exit_price(same_bar_exit, config)
                    gross = (exit_price - entry) * quantity
                    total_cost = _cost(entry * quantity, config) + _cost(exit_price * quantity, config)
                    net = gross - total_cost
                    cash += entry * quantity + gross - total_cost
                    fills.append(Fill(signal.timestamp, bar.timestamp, bar.timestamp, entry, exit_price, quantity, gross, total_cost, net, same_bar_reason))
                    position = None
        mark = cash + ((position[3] * bar.close) if position is not None else 0.0)
        equity_curve.append({"timestamp": bar.timestamp, "equity": mark})
    if position is not None:
        signal, entry_bar, entry, quantity = position
        bar = bars[-1]
        exit = _exit_price(bar.close, config)
        gross = (exit - entry) * quantity
        total_cost = _cost(entry * quantity, config) + _cost(exit * quantity, config)
        net = gross - total_cost
        cash += entry * quantity + gross - total_cost
        fills.append(Fill(signal.timestamp, entry_bar.timestamp, bar.timestamp, entry, exit, quantity, gross, total_cost, net, "END_OF_DATA"))
    returns = [fill.net_pnl / (fill.entry_price * fill.quantity) for fill in fills if fill.entry_price and fill.quantity]
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x <= 0]
    return {"status": "OK", "fills": [asdict(fill) for fill in fills], "ending_cash": round(cash, 6), "metrics": {"trades": len(fills), "net_pnl": round(sum(fill.net_pnl for fill in fills), 6), "win_rate": len(wins) / len(returns) if returns else 0.0, "expectancy": sum(returns) / len(returns) if returns else 0.0, "average_loss": sum(losses) / len(losses) if losses else 0.0}}
