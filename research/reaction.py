"""Point-in-time event reaction calculations over Alpha's SQLite prices."""
from __future__ import annotations
import math
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

HORIZONS={'intraday':0,'1-3d':3,'3-10d':10,'10-30d':30}

def _dt(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

def _prices(c,ticker):
    rows=c.execute('SELECT p.* FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies co ON co.id=s.company_id WHERE co.ticker=? ORDER BY p.market_timestamp',(ticker.upper(),)).fetchall()
    return [( _dt(r['market_timestamp']), float(r['close']), r) for r in rows]

def _at_or_after(rows, instant):
    return next((x for x in rows if x[0]>=instant), None)

def _at_or_before(rows, instant):
    return next((x for x in reversed(rows) if x[0]<=instant), None)

def event_reaction(event_id:int, ticker:str, benchmark:str|None=None, sector_proxy:str|None=None, horizons=None):
    horizons=horizons or HORIZONS
    with alpha.conn() as c:
        e=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not e: raise ValueError('event not found')
        event_time=_dt(e['market_timestamp'] or e['published_at'])
        available_time=_dt(e['available_at'] or e['published_at'])
        decision_time=max(event_time,available_time)
        target=_prices(c,ticker)
        if not target: return {'status':'insufficient_data','event_id':event_id,'ticker':ticker,'reactions':[]}
        # A simulated decision cannot use a bar before the information became available.
        base=_at_or_after(target,decision_time)
        if not base: return {'status':'insufficient_data','event_id':event_id,'ticker':ticker,'reactions':[]}
        bench=_prices(c,benchmark) if benchmark else []
        sector=_prices(c,sector_proxy) if sector_proxy else []
        results=[]
        for name,days in horizons.items():
            end=_at_or_after(target,event_time+timedelta(days=days))
            if not end or end[0] < base[0]: continue
            raw=(end[1]/base[1]-1)*100
            bret=None
            if bench:
                b0=_at_or_after(bench,base[0]); b1=_at_or_after(bench,end[0])
                if b0 and b1: bret=(b1[1]/b0[1]-1)*100
            sret=None
            if sector:
                s0=_at_or_after(sector,base[0]); s1=_at_or_after(sector,end[0])
                if s0 and s1: sret=(s1[1]/s0[1]-1)*100
            window=[x for x in target if base[0] <= x[0] <= end[0]]
            closes=[x[1] for x in window]
            path_returns=[(closes[i]/closes[i-1]-1)*100 for i in range(1,len(closes)) if closes[i-1]]
            volume=[float(x[2]['volume'] or 0) for x in window]
            results.append({'horizon':name,'days':days,'base_timestamp':base[0].isoformat(),'end_timestamp':end[0].isoformat(),'raw_return_pct':raw,'benchmark_return_pct':bret,'sector_return_pct':sret,'abnormal_return_pct':raw-bret if bret is not None else None,'sector_relative_return_pct':raw-sret if sret is not None else None,'mfe_pct':(max(closes)/base[1]-1)*100 if closes else None,'mae_pct':(min(closes)/base[1]-1)*100 if closes else None,'volatility_pct':(statistics.pstdev(path_returns) if len(path_returns)>1 else 0.0),'average_volume':statistics.mean(volume) if volume else None,'observations':len(window)})
        return {'status':'ok','event_id':event_id,'ticker':ticker.upper(),'event_timestamp':event_time.isoformat(),'available_timestamp':available_time.isoformat(),'decision_timestamp':decision_time.isoformat(),'reactions':results}
