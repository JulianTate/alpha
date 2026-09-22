"""Conservative background loop: health checks plus opt-in official SEC ingestion."""
import os,time,logging,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alpha import init, report, conn, now
from ingestion.sec import ingest_recent_filings
from ingestion.market import ingest_prices
from ingestion.news import fetch_news
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[1]
logging.basicConfig(filename=ROOT/'logs'/'worker.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
INTERVAL=int(os.getenv('ALPHA_POLL_SECONDS','300'))
SEC_TICKERS=tuple(x.strip().upper() for x in os.getenv('ALPHA_SEC_TICKERS','').split(',') if x.strip())
MARKET_TICKERS=tuple(x.strip().upper() for x in os.getenv('ALPHA_MARKET_TICKERS','').split(',') if x.strip())
NEWS_QUERIES=tuple(x.strip() for x in os.getenv('ALPHA_NEWS_QUERIES','').split('|') if x.strip())

def record_quality(source,check,status,details):
    with conn() as c:
        c.execute('INSERT INTO data_quality(source,check_name,status,details,checked_at) VALUES(?,?,?,?,?)',(source,check,status,details,now()))

def run_once():
    init()
    results=[]
    for ticker in SEC_TICKERS:
        try:
            result=ingest_recent_filings(ticker)
            results.append(result)
            record_quality('sec-edgar',f'recent-filings:{ticker}','OK',f"ingested={result['count']}")
            logging.info('SEC ticker=%s filings=%s',ticker,result['count'])
        except Exception as exc:
            record_quality('sec-edgar',f'recent-filings:{ticker}','ERROR',str(exc)[:500])
            logging.exception('SEC ingestion failed ticker=%s',ticker)
    market_results=[]
    end=datetime.now(timezone.utc).date()
    start=end-timedelta(days=int(os.getenv('ALPHA_MARKET_LOOKBACK_DAYS','10')))
    for ticker in MARKET_TICKERS:
        try:
            result=ingest_prices(ticker,start.isoformat(),end.isoformat())
            market_results.append(result)
            record_quality('stooq',f'daily-prices:{ticker}','OK',f"ingested={result['count']}")
        except Exception as exc:
            record_quality('stooq',f'daily-prices:{ticker}','ERROR',str(exc)[:500])
            logging.exception('market ingestion failed ticker=%s',ticker)
    news_results=[]
    for query in NEWS_QUERIES:
        try:
            result=fetch_news(query,(end-timedelta(days=2)).strftime('%Y%m%d000000'),(end+timedelta(days=1)).strftime('%Y%m%d000000'),maxrecords=50)
            news_results.append(result)
            record_quality('gdelt',f'news:{query}','OK',f"ingested={result['count']}")
        except Exception as exc:
            record_quality('gdelt',f'news:{query}','ERROR',str(exc)[:500])
            logging.exception('news ingestion failed query=%s',query)
    health=report()
    logging.info('health=%s sec_tickers=%s market_tickers=%s news_queries=%s',health,SEC_TICKERS,MARKET_TICKERS,NEWS_QUERIES)
    return {'health':health,'sec':results,'sec_tickers':SEC_TICKERS,'market':market_results,'market_tickers':MARKET_TICKERS,'news':news_results,'news_queries':NEWS_QUERIES}

if __name__=='__main__':
    init(); logging.info('Alpha worker started in signal/paper mode; SEC=%s market=%s news=%s',SEC_TICKERS,MARKET_TICKERS,NEWS_QUERIES)
    while True:
        try: run_once()
        except Exception: logging.exception('worker failure')
        time.sleep(INTERVAL)
