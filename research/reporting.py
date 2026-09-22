"""Explainable validation reports grouped by split, horizon, and strategy."""
from __future__ import annotations
from collections import defaultdict
from .validation import metrics


def _group(rows, key):
    grouped=defaultdict(list)
    for row in rows:
        grouped[row.get(key,'unknown')].append(row)
    return grouped


def summarize_rows(rows, *, split_key='split', strategy_key='strategy', horizon_key='horizon', return_key='net_return'):
    """Return deterministic nested metrics without combining train/test data.

    Each input row must already be point-in-time valid and must contain a return
    expressed as a decimal (0.01 = 1%). Metrics are descriptive, not a claim of
    predictive skill.
    """
    rows=list(rows)
    out={'overall':metrics((r[return_key] for r in rows),sum(float(r.get('capital_time',0)) for r in rows),sum(float(r.get('turnover',0)) for r in rows),sum(float(r.get('capital',0)) for r in rows)),'by_split':{},'by_strategy':{},'by_horizon':{}}
    for name,key in [('by_split',split_key),('by_strategy',strategy_key),('by_horizon',horizon_key)]:
        for group, items in sorted(_group(rows,key).items(),key=lambda item:str(item[0])):
            out[name][str(group)]=metrics((r[return_key] for r in items),sum(float(r.get('capital_time',0)) for r in items),sum(float(r.get('turnover',0)) for r in items),sum(float(r.get('capital',0)) for r in items))
    return out


def select_oos(rows, split='test'):
    """Select one evaluation split; rejects mixed split labels."""
    selected=[r for r in rows if r.get('split')==split]
    if any(r.get('split') not in {split} for r in selected): raise ValueError('mixed split selection')
    return selected
