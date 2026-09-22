"""FRED/ALFRED observations with vintage timestamps; requires an operator-supplied API key."""
from __future__ import annotations
import json, os
from .http import get_json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

def observations(series_id: str, *, api_key=None, realtime_start=None, realtime_end=None, limit=1000):
    key=api_key or os.getenv('ALPHA_FRED_API_KEY')
    if not key: return {'status':'not_configured','source':'fred','series_id':series_id,'message':'FRED API key is not configured; no network call made.'}
    params=[f'series_id={series_id}',f'api_key={key}','file_type=json',f'limit={int(limit)}']
    if realtime_start: params.append(f'realtime_start={realtime_start}')
    if realtime_end: params.append(f'realtime_end={realtime_end}')
    url='https://api.stlouisfed.org/fred/series/observations?'+'&'.join(params)
    payload,meta=get_json(url, headers={'User-Agent':'JarvisAlpha/0.1'})
    from .snapshot import save as save_snapshot
    meta['snapshot_path']=save_snapshot('fred-observations',payload,meta)
    out=[]
    for item in payload.get('observations',[]):
        # FRED observation date and realtime vintage are kept distinct.
        out.append({'series_id':series_id,'observation_date':item.get('date'),'value':item.get('value'),'realtime_start':item.get('realtime_start'),'realtime_end':item.get('realtime_end'),'source_url':url,'received_at':meta['received_at']})
    return {'status':'ok','source':'fred','series_id':series_id,'retrieved_at':meta['received_at'],'count':len(out),'observations':out}
