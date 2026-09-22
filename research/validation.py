"""Leakage-resistant walk-forward evaluation helpers.

These helpers operate on already materialized, timestamped observations. They do
not tune a strategy or invent labels. The caller must provide decision_time and
availability_time for every observation.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Iterable, Sequence


def parse_time(value: str) -> datetime:
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('timestamps must include timezone')
    return parsed

@dataclass(frozen=True)
class Observation:
    decision_time: str
    availability_time: str
    label: float
    key: str=''
    metadata: dict|None=None

    def validate(self):
        decision=parse_time(self.decision_time); available=parse_time(self.availability_time)
        if available > decision: raise ValueError(f'look-ahead: {self.key or "observation"} available after decision time')
        return self

@dataclass(frozen=True)
class Split:
    name: str
    start: str
    end: str
    observations: tuple[Observation,...]

def chronological_splits(observations: Iterable[Observation], train_end: str, validation_end: str, test_end: str, start: str|None=None):
    rows=sorted((o.validate() for o in observations), key=lambda o: parse_time(o.decision_time))
    bounds=[parse_time(train_end),parse_time(validation_end),parse_time(test_end)]
    if not bounds[0] < bounds[1] < bounds[2]: raise ValueError('split boundaries must be strictly increasing')
    lower=parse_time(start) if start else None
    def select(lo,hi): return tuple(o for o in rows if (lo is None or parse_time(o.decision_time)>=lo) and parse_time(o.decision_time)<hi)
    return [Split('train',(lower or parse_time(rows[0].decision_time) if rows else bounds[0]).isoformat(),bounds[0].isoformat(),select(lower,bounds[0])),Split('validation',bounds[0].isoformat(),bounds[1].isoformat(),select(bounds[0],bounds[1])),Split('test',bounds[1].isoformat(),bounds[2].isoformat(),select(bounds[1],bounds[2]))]

def assert_no_overlap(splits: Sequence[Split]):
    seen=set()
    for split in splits:
        for obs in split.observations:
            identity=obs.key or (obs.decision_time,obs.availability_time,obs.label)
            if identity in seen: raise ValueError(f'observation appears in multiple splits: {identity}')
            seen.add(identity)
    return True

def metrics(returns: Iterable[float], capital_time: float=0.0, turnover: float=0.0, utilised_capital: float=0.0):
    values=[float(x) for x in returns]; n=len(values)
    if not values: return {'trades':0,'expectancy':0.0,'win_rate':0.0,'average_win':0.0,'average_loss':0.0,'volatility':0.0,'max_drawdown':0.0,'longest_losing_streak':0,'turnover':turnover,'capital_utilisation':utilised_capital,'return_per_capital_time':0.0,'risk_of_ruin_proxy':0.0}
    equity=1.0; peak=1.0; drawdown=0.0; streak=0; longest=0
    for ret in values:
        equity*=1+ret
        peak=max(peak,equity); drawdown=max(drawdown,(peak-equity)/peak)
        streak=streak+1 if ret<=0 else 0; longest=max(longest,streak)
    wins=[x for x in values if x>0]; losses=[x for x in values if x<=0]
    # A conservative empirical proxy, not a formal ruin probability.
    loss_rate=len(losses)/n
    ruin=min(1.0, loss_rate**max(1,longest)) if longest else 0.0
    return {'trades':n,'expectancy':mean(values),'win_rate':len(wins)/n,'average_win':mean(wins) if wins else 0.0,'average_loss':mean(losses) if losses else 0.0,'volatility':pstdev(values) if n>1 else 0.0,'max_drawdown':drawdown,'longest_losing_streak':longest,'turnover':turnover,'capital_utilisation':utilised_capital,'return_per_capital_time':sum(values)/capital_time if capital_time else 0.0,'risk_of_ruin_proxy':ruin,'ending_equity':equity}

def compare_horizons(rows: Iterable[dict], horizon_key='horizon', return_key='net_return', capital_time_key='capital_time'):
    grouped={}
    for row in rows:
        grouped.setdefault(row[horizon_key],[]).append(row)
    out={}
    for horizon, items in grouped.items():
        out[horizon]=metrics((i[return_key] for i in items),sum(float(i.get(capital_time_key,0)) for i in items),sum(float(i.get('turnover',0)) for i in items),sum(float(i.get('capital',0)) for i in items))
    return out
