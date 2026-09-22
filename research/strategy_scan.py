"""Leakage-aware multi-strategy stock scanner for Alpha.

This module produces research candidates, not predictions or orders. Signals are
formed from OHLCV bars available at the bar close; forward outcomes are only
used for historical evaluation and never for the live candidate score.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import isfinite
from statistics import mean
from typing import Iterable, Sequence

from .backtest import CostModel, simulate_trade

@dataclass(frozen=True)
class Bar:
    timestamp: str
    close: float
    high: float | None = None
    low: float | None = None
    volume: float = 0.0

@dataclass(frozen=True)
class StrategySignal:
    strategy: str
    direction: str
    strength: float
    reason: str

@dataclass(frozen=True)
class ScanResult:
    ticker: str
    timestamp: str
    direction: str
    consensus: float
    agreement: int
    strategies_checked: int
    empirical_hit_rate: float | None
    historical_samples: int
    confidence_band: str
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    risk_reward: float | None
    setup_score: float
    signals: tuple[StrategySignal, ...]
    warnings: tuple[str, ...]


def _closes(bars): return [float(b.close) for b in bars]
def _sma(values, n): return mean(values[-n:]) if len(values) >= n else None

def _rsi(values, n=14):
    if len(values) <= n: return None
    changes=[values[i]-values[i-1] for i in range(1,len(values))][-n:]
    gains=[max(x,0) for x in changes]; losses=[max(-x,0) for x in changes]
    avg_gain=mean(gains); avg_loss=mean(losses)
    if avg_loss == 0: return 100.0
    return 100 - (100/(1 + avg_gain/avg_loss))

def _ema(values, n):
    if len(values) < n: return None
    value=mean(values[:n]); k=2/(n+1)
    for x in values[n:]: value=x*k+value*(1-k)
    return value

def strategy_signals(bars: Sequence[Bar]) -> list[StrategySignal]:
    """Calculate deliberately simple, explainable daily strategies."""
    values=_closes(bars); price=values[-1]; out=[]
    fast, slow=_sma(values,20),_sma(values,50)
    if fast is not None and slow is not None:
        if fast > slow and price > fast: out.append(StrategySignal('SMA trend','BUY',min(1,(fast/slow-1)*20+0.5),'price above rising 20-day average; 20-day average above 50-day average'))
        elif fast < slow and price < fast: out.append(StrategySignal('SMA trend','SELL',min(1,(slow/fast-1)*20+0.5),'price below falling 20-day average; 20-day average below 50-day average'))
    rsi=_rsi(values)
    if rsi is not None:
        if rsi < 30: out.append(StrategySignal('RSI mean reversion','BUY',min(1,(30-rsi)/20+0.5),f'RSI={rsi:.1f}, oversold threshold'))
        elif rsi > 70: out.append(StrategySignal('RSI mean reversion','SELL',min(1,(rsi-70)/20+0.5),f'RSI={rsi:.1f}, overbought threshold'))
    e12,e26=_ema(values,12),_ema(values,26)
    if e12 is not None and e26 is not None:
        macd=e12-e26
        if macd > 0 and price > e12: out.append(StrategySignal('MACD momentum','BUY',0.55,'MACD positive and price above 12-day EMA'))
        elif macd < 0 and price < e12: out.append(StrategySignal('MACD momentum','SELL',0.55,'MACD negative and price below 12-day EMA'))
    if len(values)>=20:
        prior=values[-21:-1]; high=max(prior); low=min(prior)
        if price > high: out.append(StrategySignal('Donchian breakout','BUY',0.7,f'close broke above prior 20-day high {high:.2f}'))
        elif price < low: out.append(StrategySignal('Donchian breakout','SELL',0.7,f'close broke below prior 20-day low {low:.2f}'))
    return out


def _hit(direction, entry, exit_price):
    ret=exit_price/entry-1
    return ret > 0 if direction == 'BUY' else ret < 0


def historical_evidence(bars: Sequence[Bar], horizon=5, min_strength=0.0, cost=CostModel()):
    """Evaluate prior signals with a fixed forward horizon; no tuning occurs here."""
    rows=[]
    for i in range(50, len(bars)-horizon):
        signals=strategy_signals(bars[:i+1]); buys=[s for s in signals if s.direction=='BUY' and s.strength>=min_strength]; sells=[s for s in signals if s.direction=='SELL' and s.strength>=min_strength]
        if not buys and not sells: continue
        direction='BUY' if len(buys)>=len(sells) else 'SELL'; entry=bars[i].close; exit_price=bars[i+horizon].close
        gross=(exit_price/entry-1) if direction=='BUY' else (entry/exit_price-1)
        result=simulate_trade('SCAN',1,entry,exit_price,horizon,cost=cost)
        net=(result.net_pnl/entry) if direction=='BUY' else ((-result.net_pnl)/entry)
        rows.append({'timestamp':bars[i].timestamp,'direction':direction,'hit':_hit(direction,entry,exit_price),'gross_return':gross,'net_return':net,'agreement':max(len(buys),len(sells))})
    return rows


def _atr(bars: Sequence[Bar], n=14):
    if len(bars) < n + 1: return None
    values=[]
    for i in range(len(bars)-n, len(bars)):
        b, prev = bars[i], bars[i-1]
        high=float(b.high or b.close); low=float(b.low or b.close)
        values.append(max(high-low, abs(high-prev.close), abs(low-prev.close)))
    return mean(values)


def scan_bars(ticker: str, bars: Sequence[Bar], horizon=5, cost=CostModel()) -> ScanResult:
    bars=tuple(sorted(bars,key=lambda b:b.timestamp)); warnings=[]
    if len(bars)<50: warnings.append(f'insufficient history: {len(bars)} bars; at least 50 required')
    if not bars: raise ValueError('at least one bar is required')
    signals=strategy_signals(bars); buys=[s for s in signals if s.direction=='BUY']; sells=[s for s in signals if s.direction=='SELL']
    direction='BUY' if len(buys)>len(sells) else 'SELL' if len(sells)>len(buys) else 'WATCH'
    agreement=max(len(buys),len(sells)); checked=len({s.strategy for s in signals})
    evidence=historical_evidence(bars,horizon=horizon,cost=cost); same=[r for r in evidence if r['direction']==direction] if direction!='WATCH' else []
    hit=mean(r['hit'] for r in same) if same else None
    if len(same)<20: band='INSUFFICIENT_EVIDENCE'; warnings.append('fewer than 20 comparable historical observations')
    elif hit is not None and hit>=.65 and agreement>=2: band='RESEARCH_CANDIDATE'
    else: band='WEAK_OR_MIXED'
    entry=stop=target=rr=None
    atr=_atr(bars)
    if direction in ('BUY','SELL') and atr and atr > 0:
        entry=float(bars[-1].close)
        if direction=='BUY':
            stop=entry-1.5*atr; target=entry+2.5*atr
        else:
            stop=entry+1.5*atr; target=entry-2.5*atr
        rr=round(abs(target-entry)/abs(entry-stop),2)
    if direction=='WATCH': warnings.append('strategies disagree or produced no current signal')
    if atr is None: warnings.append('ATR-based trade levels unavailable until at least 15 bars exist')
    warnings.append('empirical hit rate is historical, not a probability guarantee')
    score=(100 * (0.55*(hit or 0) + 0.25*(agreement/4) + 0.20*min(1,len(same)/50))) if hit is not None else 0.0
    return ScanResult(ticker.upper(),bars[-1].timestamp,direction,round(agreement/max(1,4),3),agreement,4,round(hit,3) if hit is not None else None,len(same),band,round(entry,4) if entry is not None else None,round(stop,4) if stop is not None else None,round(target,4) if target is not None else None,rr,round(score,2),tuple(signals),tuple(warnings))


def bars_from_rows(rows: Iterable[dict]) -> list[Bar]:
    return [Bar(str(r.get('timestamp') or r.get('market_timestamp')),float(r['close']),float(r.get('high') or r['close']),float(r.get('low') or r['close']),float(r.get('volume') or 0)) for r in rows]

def result_dict(result: ScanResult):
    value=asdict(result); value['signals']=[asdict(s) for s in result.signals]; return value


def rank_results(results: Iterable[ScanResult], limit=10):
    """Rank only research candidates first, then weaker setups by evidence score."""
    order={'RESEARCH_CANDIDATE':0,'WEAK_OR_MIXED':1,'INSUFFICIENT_EVIDENCE':2}
    return sorted(results, key=lambda r:(order.get(r.confidence_band, 9), -r.setup_score, -(r.empirical_hit_rate or 0), -r.historical_samples))[:limit]
