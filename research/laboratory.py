"""Controlled Alpha research laboratory primitives.

The laboratory is intentionally bounded: definitions are fingerprinted,
features are point-in-time, searches are budgeted, final OOS is a separate
method, and every trial carries full provenance. It is research tooling, not a
profitability claim or an execution system.
"""
from __future__ import annotations

import hashlib, html, json, math, random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import mean, median, pstdev
from typing import Any, Iterable


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any, prefix: str = "") -> str:
    return prefix + hashlib.sha256(canonical(value).encode()).hexdigest()[:16].upper()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    strategy_version: str
    hypothesis: str
    universe: tuple[str, ...]
    features: tuple[str, ...]
    signal_conditions: tuple[str, ...]
    entry_rules: tuple[str, ...]
    exit_rules: tuple[str, ...]
    holding_horizon: int
    parameters: dict[str, Any]
    position_sizing: str
    transaction_cost_model: dict[str, Any]
    execution_assumptions: dict[str, Any]

    @property
    def strategy_fingerprint(self) -> str:
        return fingerprint(asdict(self), "STR-")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self); result["strategy_fingerprint"] = self.strategy_fingerprint; return result


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float | None
    input_data: str
    lookback: int
    timestamp: str
    availability_timestamp: str
    usable_at_signal_time: bool


def _sma(xs, n): return mean(xs[-n:]) if len(xs) >= n else None

def _atr(rows, n):
    if len(rows) < n + 1: return None
    tr=[]
    for i in range(len(rows)-n, len(rows)):
        high, low, prev = float(rows[i].get("high") or rows[i]["close"]), float(rows[i].get("low") or rows[i]["close"]), float(rows[i-1]["close"])
        tr.append(max(high-low, abs(high-prev), abs(low-prev)))
    return mean(tr)


def compute_features(rows: list[dict], index: int | None = None) -> dict[str, FeatureValue]:
    """Compute features using rows through index only; no future row is read."""
    if index is None: index = len(rows)-1
    if index < 0 or index >= len(rows): raise IndexError("feature index outside rows")
    history = rows[:index+1]; closes=[float(r["close"]) for r in history]; volumes=[float(r.get("volume") or 0) for r in history]
    row=history[-1]; ts=str(row.get("market_timestamp") or row.get("timestamp")); result={}
    def add(name, value, lookback, input_data):
        result[name]=FeatureValue(name, None if value is None else float(value), input_data, lookback, ts, ts, value is not None)
    ret=(closes[-1]/closes[-2]-1) if len(closes)>=2 else None
    add("daily_return", ret, 1, "close")
    for n in (5,21,63,126): add(f"return_{n}d", closes[-1]/closes[-n-1]-1 if len(closes)>n else None, n, "close")
    for n in (20,50,100,200):
        avg=_sma(closes,n); add(f"distance_sma_{n}", closes[-1]/avg-1 if avg else None,n,"close")
        add(f"sma_{n}_slope", (_sma(closes,n)-_sma(closes[:-n//5],n) if len(closes)>=n+n//5 else None), n+n//5,"close")
    for n in (20,50,100):
        window=closes[-n:] if len(closes)>=n else []
        add(f"rolling_high_{n}", max(window) if window else None,n,"high/close")
        add(f"rolling_low_{n}", min(window) if window else None,n,"low/close")
        add(f"breakout_distance_{n}", closes[-1]/max(window[:-1])-1 if len(window)>1 else None,n,"high/close")
    atr14=_atr(history,14); add("atr_14",atr14,14,"high/low/close")
    returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    add("rolling_volatility_21", pstdev(returns[-21:]) if len(returns)>=21 else None,21,"close")
    add("volatility_change", (pstdev(returns[-10:])/pstdev(returns[-30:-10])-1 if len(returns)>=30 and pstdev(returns[-30:-10]) else None),30,"close")
    changes=[closes[i]-closes[i-1] for i in range(max(1,len(closes)-14),len(closes))]; gains=[max(x,0) for x in changes]; losses=[max(-x,0) for x in changes]; ag,al=mean(gains),mean(losses)
    add("rsi_14",100 if al==0 and gains else (100-100/(1+ag/al) if changes and al else None),14,"close")
    add("momentum_21",closes[-1]-closes[-22] if len(closes)>=22 else None,21,"close")
    add("roc_63",closes[-1]/closes[-64]-1 if len(closes)>=64 else None,63,"close")
    avgvol=_sma(volumes,20); add("volume_ratio_20",volumes[-1]/avgvol if avgvol else None,20,"volume")
    add("volume_trend_20",_sma(volumes,5)/_sma(volumes,20)-1 if len(volumes)>=20 and _sma(volumes,20) else None,20,"volume")
    return result


HYPOTHESIS_FAMILIES = {
    "MOMENTUM": ["Does {lookback}-day momentum predict next-{horizon}-day returns after costs?"],
    "TREND": ["Does price above the {lookback}-day moving average predict next-{horizon}-day returns after costs?"],
    "BREAKOUT": ["Does a {lookback}-day breakout with volume confirmation predict next-{horizon}-day returns after costs?"],
    "MEAN_REVERSION": ["Does an RSI extreme mean-revert over the next-{horizon} days after costs?"],
    "CROSS_SECTIONAL": ["Does cross-sectional {lookback}-day momentum rank predict next-{horizon}-day returns after costs?"],
}


def generate_hypotheses(family: str, lookbacks: tuple[int, ...], horizons: tuple[int, ...], budget: int) -> list[dict]:
    family=family.upper()
    if family not in HYPOTHESIS_FAMILIES: raise ValueError(f"unsupported hypothesis family: {family}")
    output=[]
    for lookback in lookbacks:
        for horizon in horizons:
            if len(output)>=budget: return output
            question=HYPOTHESIS_FAMILIES[family][0].format(lookback=lookback,horizon=horizon)
            output.append({"hypothesis_id":fingerprint({"family":family,"lookback":lookback,"horizon":horizon},"HYP-"),"family":family,"lookback":lookback,"horizon":horizon,"question":question})
    return output


def temporal_splits(rows: list[dict], train: tuple[str,str], validation: tuple[str,str], oos: tuple[str,str]) -> dict[str,list[dict]]:
    ranges={"train":train,"validation":validation,"oos":oos}; output={}
    for name,(start,end) in ranges.items():
        lo,hi=parse_time(start),parse_time(end); output[name]=[r for r in rows if lo<=parse_time(str(r.get("market_timestamp") or r.get("timestamp")))<hi]
    train_start, train_end = parse_time(train[0]), parse_time(train[1])
    validation_start, validation_end = parse_time(validation[0]), parse_time(validation[1])
    oos_start, oos_end = parse_time(oos[0]), parse_time(oos[1])
    if not (train_start < train_end <= validation_start < validation_end <= oos_start < oos_end):
        raise ValueError("temporal partitions must be non-empty, ordered, and non-overlapping")
    return output


def walk_forward_folds(rows: list[dict], start: str, end: str, train_days: int, validation_days: int, step_days: int) -> list[dict]:
    eligible=[r for r in rows if parse_time(start)<=parse_time(str(r.get("market_timestamp") or r.get("timestamp")))<parse_time(end)]
    folds=[]; cursor=0
    while cursor+train_days+validation_days<=len(eligible):
        folds.append({"fold":len(folds)+1,"train":eligible[cursor:cursor+train_days],"validation":eligible[cursor+train_days:cursor+train_days+validation_days]}); cursor+=step_days
    return folds


def parameter_grid(family: str) -> list[dict]:
    if family=="MOMENTUM": return [{"lookback":n,"horizon":h} for n in (21,63,126,252) for h in (5,21)]
    if family=="TREND": return [{"lookback":n,"horizon":h} for n in (20,50,100,200) for h in (5,21)]
    if family=="BREAKOUT": return [{"lookback":n,"horizon":h} for n in (20,50,100,200) for h in (5,21)]
    if family=="MEAN_REVERSION": return [{"rsi_period":n,"horizon":h} for n in (7,14,21) for h in (5,21)]
    return [{"lookback":n,"horizon":h} for n in (21,63,126) for h in (5,21)]


def baseline_metrics(rows: list[dict], horizon: int, cost_bps: float=12) -> dict:
    if len(rows)<=horizon: return {"trades":0,"return":0.0,"win_rate":0.0}
    gross=float(rows[-1]["close"])/float(rows[0]["close"])-1; costs=2*cost_bps/10000; net=gross-costs
    return {"trades":1,"return":net,"win_rate":1.0 if net>0 else 0.0,"label":"buy_and_hold"}


def score_candidate(rows: list[dict], family: str, params: dict, cost_bps: float=12) -> dict:
    horizon=int(params.get("horizon",5)); lb=int(params.get("lookback",params.get("rsi_period",14))); returns=[]
    for i in range(max(lb,21),len(rows)-horizon):
        now=float(rows[i]["close"]); future=float(rows[i+horizon]["close"]); signal=False
        if family=="MOMENTUM": signal=now/float(rows[i-lb]["close"])-1>0
        elif family=="TREND": signal=now>mean(float(r["close"]) for r in rows[i-lb+1:i+1])
        elif family=="BREAKOUT": signal=now>max(float(r["high"] or r["close"]) for r in rows[i-lb:i]) and float(rows[i].get("volume") or 0)>mean(float(r.get("volume") or 0) for r in rows[i-lb:i])
        elif family=="MEAN_REVERSION": signal=now<mean(float(r["close"]) for r in rows[i-lb+1:i+1])*.98
        elif family=="CROSS_SECTIONAL": signal=now/float(rows[i-lb]["close"])-1>0
        if signal: returns.append(future/now-1-cost_bps/10000)
    return {"trades":len(returns),"return":sum(returns),"mean_return":mean(returns) if returns else 0.0,"win_rate":sum(x>0 for x in returns)/len(returns) if returns else 0.0,"max_drawdown":_max_drawdown(returns),"family":family,"parameters":params}


def _max_drawdown(returns):
    # Returns are event-level observations and may overlap. Do not present a
    # compounded equity curve as a portfolio drawdown; use a fixed-notional
    # cumulative P&L proxy and label it as such in callers.
    equity=peak=0.0; worst=0.0
    for ret in returns:
        equity += ret; peak=max(peak,equity); worst=min(worst,equity-peak)
    return worst


def robustness(rows: list[dict], family: str, params: dict) -> dict:
    neighbors=[]
    base=int(params.get("lookback",params.get("rsi_period",14)))
    for delta in (-2,-1,0,1,2):
        value=max(2,base+delta*max(1,base//10)); key="rsi_period" if "rsi_period" in params else "lookback"; variant=dict(params); variant[key]=value; neighbors.append(score_candidate(rows,family,variant,12))
    costs=[score_candidate(rows,family,params,c) for c in (8,12,20,30)]
    returns=[x["mean_return"] for x in neighbors]; positive=sum(x>0 for x in returns)
    return {"parameter_surface":neighbors,"cost_sensitivity":costs,"positive_neighbor_fraction":positive/len(returns),"stable":positive>=3 and costs[-1]["mean_return"]>=0}


def multiple_testing(trials: list[dict]) -> dict:
    values=[float(t.get("mean_return",0)) for t in trials]; n=len(values); best=max(values) if values else 0; return {"total_trials":n,"successful_trials":sum(v>0 for v in values),"rejected_trials":sum(v<=0 for v in values),"best_mean_return":best,"median_mean_return":median(values) if values else 0.0,"selection_bias_warning":n>1,"method":"descriptive trial-distribution diagnostics; no DSR/PBO claim"}


def research_gate(metrics: dict, robustness_result: dict, config: dict | None=None) -> dict:
    cfg={"min_trades":20,"min_validation_periods":2,"max_drawdown":-0.35,"min_neighbor_fraction":0.6,"min_cost_return":0.0}; cfg.update(config or {})
    checks={"minimum_trades":metrics.get("trades",0)>=cfg["min_trades"],"drawdown":metrics.get("max_drawdown",-1)<=0 and metrics.get("max_drawdown",-1)>=cfg["max_drawdown"],"parameter_stability":robustness_result.get("positive_neighbor_fraction",0)>=cfg["min_neighbor_fraction"],"cost_sensitivity":robustness_result.get("cost_sensitivity",[{}])[-1].get("mean_return",-1)>=cfg["min_cost_return"]}
    return {"decision":"MONITOR" if all(checks.values()) else "REJECTED","checks":checks,"thresholds":cfg,"note":"Gate is configurable evidence policy, not a probability estimate."}


def html_report(report: dict) -> str:
    title=html.escape(str(report.get("campaign_id","Alpha Research Campaign"))); body=html.escape(json.dumps(report,indent=2,default=str)); return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body><h1>{title}</h1><pre>{body}</pre></body></html>"
