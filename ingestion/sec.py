"""Official SEC submissions/XBRL ingestion. No API key is required by data.sec.gov."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from .http import get_json
from .snapshot import save as save_snapshot
from .quality import parse_timestamp
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

TICKERS_URL='https://www.sec.gov/files/company_tickers.json'

def ticker_map():
    payload, meta=get_json(TICKERS_URL)
    return {str(v['ticker']).upper(): str(v['cik_str']).zfill(10) for v in payload.values()}, meta

def submissions(ticker_or_cik: str):
    value=str(ticker_or_cik).upper()
    if value.isdigit():
        cik=value.zfill(10); ticker=value
    else:
        mapping,map_meta=ticker_map()
        if value not in mapping: raise ValueError(f'ticker not found in SEC map: {value}')
        cik=mapping[value]; ticker=value
    payload, meta=get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')
    meta['cik']=cik; meta['ticker']=ticker
    meta['snapshot_path']=save_snapshot('sec-submissions',payload,meta)
    return payload, meta

def companyfacts(ticker_or_cik: str):
    _submissions, meta=submissions(ticker_or_cik)
    payload, fact_meta=get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{meta['cik']}.json")
    fact_meta.update({'cik':meta['cik'],'ticker':meta['ticker']})
    fact_meta['snapshot_path']=save_snapshot('sec-companyfacts',payload,fact_meta)
    return payload, fact_meta

def ingest_recent_filings(ticker_or_cik: str, forms=('8-K','10-Q','10-K','4','SC 13D','SC 13G','13F-HR'), limit=100):
    payload, meta=submissions(ticker_or_cik)
    recent=payload.get('filings',{}).get('recent',{})
    keys=list(recent.keys()); rows=[]
    for i in range(min(len(recent.get('form',[])), limit)):
        row={k:recent[k][i] for k in keys if i < len(recent[k])}
        if row.get('form') not in forms: continue
        form=row.get('form',''); accession=row.get('accessionNumber',''); filed=row.get('filingDate'); accepted=row.get('acceptanceDateTime') or filed
        if accepted and len(accepted) == 14 and accepted.isdigit():
            accepted=f'{accepted[:4]}-{accepted[4:6]}-{accepted[6:8]}T{accepted[8:10]}:{accepted[10:12]}:{accepted[12:14]}+00:00'
        elif accepted and len(accepted) == 10:
            accepted=f'{accepted}T00:00:00+00:00'
        title=f"SEC {form} filing {accession}"
        source_url=f"https://www.sec.gov/Archives/edgar/data/{int(meta['cik'])}/{accession.replace('-','')}/{row.get('primaryDocument','')}"
        facts={'form':form,'accession_number':accession,'filing_date':filed,'report_date':row.get('reportDate'),'acceptance_datetime':row.get('acceptanceDateTime'),'items':row.get('items')}
        # Publication/availability is acceptance time when present; report period is not availability.
        event_id=alpha.ingest_event(meta['ticker'], 'sec_filing', title, published_at=accepted, available_at=meta['received_at'], source='sec-edgar', url=source_url, direction='neutral', strength=0.0)
        with alpha.conn() as c:
            c.execute('UPDATE events SET effective_date=?,facts_json=?,market_timestamp=? WHERE id=?',(row.get('reportDate'),json.dumps(facts),accepted,event_id))
        rows.append({'event_id':event_id,'form':form,'accession_number':accession,'published_at':accepted,'report_date':row.get('reportDate'),'url':source_url})
    return {'source':'sec-edgar','ticker':str(ticker_or_cik).upper(),'cik':meta['cik'],'retrieved_at':meta['received_at'],'count':len(rows),'events':rows}
