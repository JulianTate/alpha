import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alpha
from ingestion import fred, http, market, news, quality, sec, snapshot

class IngestionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        alpha.DB_PATH=Path(self.tmp.name)/'alpha.sqlite3'
        alpha.init()
    def tearDown(self):
        self.tmp.cleanup()
    def test_pit_ordering_and_as_of(self):
        good=quality.validate_observation(event_time='2026-01-01T12:00:00+00:00', published_at='2026-01-01T13:00:00+00:00', available_at='2026-01-01T13:01:00+00:00', reaction_at='2026-01-01T14:00:00+00:00')
        self.assertTrue(quality.usable_as_of(good['available_at'],'2026-01-01T13:01:00+00:00'))
        with self.assertRaises(ValueError): quality.validate_observation(event_time='2026-01-02T00:00:00+00:00',published_at='2026-01-01T00:00:00+00:00',available_at='2026-01-01T01:00:00+00:00')
    def test_fred_without_key_is_safe(self):
        with patch.dict(os.environ, {}, clear=True):
            result=fred.observations('CPIAUCSL')
        self.assertEqual(result['status'],'not_configured')
    def test_news_fixture_shape(self):
        payload={'articles':[{'title':'XYZ event','url':'https://example.test/a','domain':'example.test','language':'English','seendate':'20260102153000'}]}
        with patch.object(news,'get_json',return_value=(payload,{'received_at':'2026-01-02T15:31:00+00:00','http_status':200})):
            result=news.fetch_news('XYZ','20260101000000','20260103000000')
        self.assertEqual(result['count'],1); self.assertEqual(result['rows'][0]['published_at'],'2026-01-02T15:30:00+00:00')
    def test_market_fixture_shape(self):
        with patch.object(market,'get_bytes',return_value=(b'Date,Open,High,Low,Close,Volume\n2026-01-02,100,110,90,105,1000\n',{'received_at':'2026-01-02T00:00:00+00:00','http_status':200})):
            result=market.fetch_prices('XYZ','2026-01-01','2026-01-02')
        self.assertEqual(result['count'],1); self.assertEqual(result['rows'][0]['close'],105.0)

    def test_http_retries_rate_limit_and_preserves_attempt_metadata(self):
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return b'{"ok": true}'
        errors=[__import__('urllib.error',fromlist=['HTTPError']).HTTPError('https://example.test',429,'rate limited',{'Retry-After':'0'},None)]
        def opener(*args,**kwargs):
            if errors: raise errors.pop(0)
            return Response()
        with patch.object(http,'urlopen',side_effect=opener), patch.object(http.time,'sleep'):
            payload,meta=http.get_json('https://example.test',retries=1,backoff=0)
        self.assertTrue(payload['ok']); self.assertEqual(meta['attempts'],2)
    def test_sec_fixture_preserves_availability_and_facts(self):
        payload={'filings':{'recent':{'form':['8-K'],'accessionNumber':['0000000000-26-000001'],'filingDate':['2026-01-02'],'acceptanceDateTime':['20260102153000'],'reportDate':['2025-12-31'],'primaryDocument':['x.htm'],'items':['2.02']}}}
        with patch.object(sec,'submissions',return_value=(payload,{'cik':'0000000001','ticker':'XYZ','received_at':'2026-01-02T15:31:00+00:00'})):
            result=sec.ingest_recent_filings('XYZ')
        self.assertEqual(result['count'],1)
        with alpha.conn() as c:
            row=c.execute('SELECT * FROM events').fetchone()
        self.assertEqual(row['published_at'],'2026-01-02T15:30:00+00:00')
        self.assertEqual(json.loads(row['facts_json'])['report_date'],'2025-12-31')
    def test_snapshot_is_content_addressed(self):
        old=snapshot.ROOT
        try:
            snapshot.ROOT=Path(self.tmp.name)
            path=snapshot.save('fixture',{'b':2,'a':1},{'received_at':'2026-01-02T00:00:00+00:00'})
            self.assertTrue(Path(path).exists())
            self.assertEqual(path,snapshot.save('fixture',{'a':1,'b':2},{'received_at':'2026-01-02T00:00:00+00:00'}))
        finally: snapshot.ROOT=old

if __name__=='__main__': unittest.main()
