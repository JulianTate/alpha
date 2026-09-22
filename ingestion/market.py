"""Historical market adapter using Stooq's public CSV endpoint.

This adapter is for research/ETL only: data is delayed/end-of-day, adjusted-data
semantics must be checked before production use, and no trading is performed.
"""
from __future__ import annotations
import csv, io
from datetime import datetime, timezone
from urllib.parse import urlencode
from .http import get_bytes
from .snapshot import save as save_snapshot
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

BASE='https://stooq.com/q/d/l/'

def _date(value):
    return datetime.strptime(value,'%Y-%m-%d').replace(tzinfo=timezone.utc).isoformat()

def fetch_prices(ticker: str, start: str, end: str, *, source='stooq'):
    params=urlencode({'s':ticker.lower(),'d1':start.replace('-',''),'d2':end.replace('-',''),'i':'d'})
    url=f'{BASE}?{params}'
    raw,meta=get_bytes(url,headers={'Accept':'text/csv'},timeout=20,min_interval=0.5,retries=3,backoff=1.0)
    body=raw.decode('utf-8')
    if body.lstrip().startswith('No data'):
        return {'status':'empty','source':source,'ticker':ticker.upper(),'count':0,'rows':[],'metadata':meta}
    rows=[]
    for row in csv.DictReader(io.StringIO(body)):
        if not row.get('Date') or not row.get('Close'): continue
        rows.append({'ticker':ticker.upper(),'market_timestamp':_date(row['Date']),'open':float(row['Open']) if row.get('Open') else None,'high':float(row['High']) if row.get('High') else None,'low':float(row['Low']) if row.get('Low') else None,'close':float(row['Close']),'volume':float(row['Volume']) if row.get('Volume') else 0.0,'source':source})
    meta['snapshot_path']=save_snapshot('market-stooq',{'csv':body},meta)
    return {'status':'ok','source':source,'ticker':ticker.upper(),'count':len(rows),'rows':rows,'metadata':meta}

def ingest_prices(ticker: str, start: str, end: str):
    result=fetch_prices(ticker,start,end)
    for row in result.get('rows',[]): alpha.add_price(**row)
    return result
