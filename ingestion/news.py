"""GDELT 2.1 DOC API adapter for public news metadata.

GDELT is a public research dataset. Results are treated as discovery metadata;
article content/licensing is not copied. Publication and retrieval timestamps
are retained, and event creation is opt-in via ingest_news_events().
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from .http import get_json
from .snapshot import save as save_snapshot
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

BASE='https://api.gdeltproject.org/api/v2/doc/doc'

def fetch_news(query: str, start: str, end: str, *, maxrecords=250, mode='artlist'):
    params={'query':query,'mode':mode,'format':'json','maxrecords':int(maxrecords),'startdatetime':start.replace('-','').replace(':','').replace('Z',''),'enddatetime':end.replace('-','').replace(':','').replace('Z','')}
    url=BASE+'?'+urlencode(params)
    payload,meta=get_json(url,headers={'Accept':'application/json'})
    meta['snapshot_path']=save_snapshot('news-gdelt',payload,meta)
    rows=[]
    for item in payload.get('articles',[]):
        published=item.get('seendate') or item.get('date')
        if published and len(published)>=14 and published[:14].isdigit():
            published=f'{published[:4]}-{published[4:6]}-{published[6:8]}T{published[8:10]}:{published[10:12]}:{published[12:14]}+00:00'
        rows.append({'title':item.get('title'),'url':item.get('url'),'domain':item.get('domain'),'language':item.get('language'),'published_at':published,'source':'gdelt','retrieved_at':meta['received_at']})
    return {'status':'ok','source':'gdelt','query':query,'count':len(rows),'rows':rows,'metadata':meta}

def ingest_news_events(query: str, start: str, end: str, *, ticker: str, event_type='news_discovery'):
    result=fetch_news(query,start,end)
    for row in result['rows']:
        if not row['published_at']: continue
        alpha.ingest_event(ticker,event_type,row['title'] or query,published_at=row['published_at'],source='gdelt',url=row['url'],direction='neutral',strength=0.0)
    return result
