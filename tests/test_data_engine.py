import unittest
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.data_engine import validate_rows, freeze_dataset, ensure_data_tables, verify_stored_prices

class DataEngineTest(unittest.TestCase):
    def test_rejects_bad_ohlc_without_repair(self):
        rows=[{'market_timestamp':'2025-01-01T00:00:00+00:00','open':10,'high':9,'low':8,'close':8.5,'volume':1}]
        issues=validate_rows(rows)
        self.assertTrue(any(i.status=='INVALID' and i.check=='ohlc_bounds' for i in issues))
        self.assertEqual(rows[0]['high'],9)

    def test_conflicting_duplicate_is_unresolved(self):
        rows=[
            {'market_timestamp':'2025-01-01T00:00:00+00:00','open':10,'high':11,'low':9,'close':10,'volume':100},
            {'market_timestamp':'2025-01-01T00:00:00+00:00','open':10,'high':12,'low':9,'close':11,'volume':100},
        ]
        issues=validate_rows(rows)
        self.assertTrue(any(i.status=='UNRESOLVED' and i.check=='conflicting_observation' for i in issues))

    def test_rejects_malformed_and_non_finite_values(self):
        rows=[{'market_timestamp':'not-a-timestamp','close':10}]
        issues=validate_rows(rows)
        self.assertTrue(any(i.check=='malformed_timestamp' for i in issues))
        rows=[{'market_timestamp':'2025-01-01T00:00:00+00:00','close':float('nan')}]
        issues=validate_rows(rows)
        self.assertTrue(any(i.check=='non_finite_value' for i in issues))

    def test_freeze_is_deterministic(self):
        rows=[{'market_timestamp':'2025-01-01T00:00:00+00:00','close':10}]
        a=freeze_dataset(['fixture'],rows,start='2025-01-01',end='2025-01-01',adjustment_policy='raw')
        b=freeze_dataset(['fixture'],rows,start='2025-01-01',end='2025-01-01',adjustment_policy='raw')
        self.assertEqual(a['dataset_hash'],b['dataset_hash'])
        self.assertEqual(a['dataset_id'],b['dataset_id'])

    def test_stored_price_verification(self):
        c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE prices(security_id INTEGER, market_timestamp TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)')
        c.execute('INSERT INTO prices VALUES (?,?,?,?,?,?,?)',(1,'2025-01-01',10,11,9,10.5,100))
        result=verify_stored_prices(c)
        self.assertEqual(result['status'],'VALID')
        self.assertEqual(result['row_count'],1)

if __name__=='__main__': unittest.main()
