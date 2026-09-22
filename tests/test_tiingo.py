import os
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion import tiingo

class TiingoTest(unittest.TestCase):
    def test_key_is_required_without_exposing_value(self):
        with patch.dict(os.environ, {}, clear=True):
            result=tiingo.health_check()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('RuntimeError', result['error_type'])
        self.assertNotIn('test-token', repr(result))

    def test_history_canonicalizes_adjusted_and_raw_fields(self):
        payload=[{'date':'2024-01-02T00:00:00.000Z','open':100,'high':110,'low':95,'close':105,'adjClose':104.5,'volume':1234,'divCash':0,'splitFactor':1}]
        meta={'received_at':'2024-01-03T00:00:00+00:00','http_status':200}
        with patch.dict(os.environ, {'TIINGO_API_KEY':'test-token'}):
            with patch.object(tiingo,'get_json',return_value=(payload,meta)), patch.object(tiingo,'save_snapshot',return_value='snapshot.json'):
                result=tiingo.get_history('aapl','2024-01-01','2024-01-03')
        self.assertEqual(result['count'],1)
        row=result['rows'][0]
        self.assertEqual(row['symbol'],'AAPL')
        self.assertEqual(row['close'],105.0)
        self.assertEqual(row['adjusted_close'],104.5)
        self.assertNotIn('test-token', repr(result))

    def test_health_result_is_redacted(self):
        with patch.dict(os.environ, {'TIINGO_API_KEY':'test-token'}):
            with patch.object(tiingo,'get_json',return_value=({'ok':True},{'http_status':200})):
                result=tiingo.health_check()
        self.assertEqual(result['status'],'OK')
        self.assertNotIn('test-token', repr(result))

if __name__=='__main__': unittest.main()
