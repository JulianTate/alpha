"""Small, explicit cost-aware paper backtest primitive.

It consumes already point-in-time signals and prices; it does not manufacture
signals or connect to a broker. Costs are configurable and reported separately.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class CostModel:
    fee_bps: float = 1.0
    half_spread_bps: float = 5.0
    slippage_bps: float = 5.0
    latency_bps: float = 0.0
    max_participation: float = 0.10

@dataclass(frozen=True)
class TradeResult:
    ticker: str
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    total_cost: float
    net_pnl: float
    return_pct: float
    capital_time_days: float


def simulate_trade(ticker: str, quantity: float, entry_price: float, exit_price: float, holding_days: float, *, average_volume: float|None=None, cost=CostModel()):
    if quantity <= 0 or entry_price <= 0 or exit_price <= 0: raise ValueError('prices and quantity must be positive')
    if average_volume is not None and quantity > average_volume * cost.max_participation: raise ValueError('liquidity constraint breached')
    notional_in=quantity*entry_price; notional_out=quantity*exit_price
    gross=notional_out-notional_in
    turnover=notional_in+notional_out
    cost_rate=(cost.fee_bps+cost.half_spread_bps+cost.slippage_bps+cost.latency_bps)/10000
    total_cost=turnover*cost_rate
    net=gross-total_cost
    return TradeResult(ticker.upper(),quantity,entry_price,exit_price,gross,total_cost,net,net/notional_in*100,notional_in*holding_days)


def summarize(results):
    results=list(results)
    if not results: return {'trades':0,'net_pnl':0.0,'expectancy':0.0,'win_rate':0.0,'capital_time':0.0,'net_return_per_capital_day':0.0}
    wins=[r for r in results if r.net_pnl>0]
    capital_time=sum(r.capital_time_days for r in results)
    return {'trades':len(results),'net_pnl':sum(r.net_pnl for r in results),'gross_pnl':sum(r.gross_pnl for r in results),'total_cost':sum(r.total_cost for r in results),'expectancy':sum(r.net_pnl for r in results)/len(results),'win_rate':len(wins)/len(results),'average_win':sum(r.net_pnl for r in wins)/len(wins) if wins else 0.0,'average_loss':sum(r.net_pnl for r in results if r.net_pnl<=0)/len(results) if len(results)-len(wins) else 0.0,'capital_time':capital_time,'net_return_per_capital_day':sum(r.net_pnl for r in results)/capital_time if capital_time else 0.0}
