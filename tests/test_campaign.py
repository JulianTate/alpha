import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.registry import ensure_registry_tables
from research.campaign import run_baseline

class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.c.executescript('''
        CREATE TABLE datasets(dataset_id TEXT PRIMARY KEY, dataset_hash TEXT UNIQUE NOT NULL, dataset_version TEXT NOT NULL, provider_composition_json TEXT NOT NULL, coverage_start TEXT, coverage_end TEXT, adjustment_policy TEXT NOT NULL, row_count INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE companies(id INTEGER PRIMARY KEY, ticker TEXT UNIQUE NOT NULL, active INTEGER DEFAULT 1);
        CREATE TABLE securities(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, ticker TEXT NOT NULL);
        CREATE TABLE prices(id INTEGER PRIMARY KEY, security_id INTEGER NOT NULL, market_timestamp TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL, source TEXT NOT NULL);
        ''')
        ensure_registry_tables(self.c)
        self.c.execute("INSERT INTO datasets VALUES('DS-TEST','hash','market-v1','[\"tiingo\"]','2020','2025','raw',100,'FROZEN','2025')")
        self.c.execute("INSERT INTO companies VALUES(1,'TEST',1)")
        self.c.execute("INSERT INTO securities VALUES(1,1,'TEST')")
        for i in range(260):
            year=2020+i//260
            day=i%260+1
            ts=f'2020-01-01T{(i//24)%24:02d}:00:00+00:00'
            price=100+i*.05
            self.c.execute('INSERT INTO prices VALUES(?,?,?,?,?,?,?,?,?)',(i+1,1,ts,price,price+1,price-1,price,10000,'tiingo'))
        self.c.commit()
    def test_baseline_registers_and_completes_without_parameter_search(self):
        result=run_baseline(self.c,'DS-TEST',['TEST'],{'train':('2020-01-01','2020-01-01T00:00:10+00:00'),'validation':('2020-01-01T00:00:10+00:00','2020-01-01T00:00:20+00:00'),'test':('2020-01-01T00:00:20+00:00','2030-01-01')})
        self.assertTrue(result['run_id'].startswith('RUN-'))
        self.assertEqual(self.c.execute('SELECT state FROM campaigns').fetchone()[0],'VALIDATED')
        self.assertEqual(self.c.execute('SELECT status FROM research_runs').fetchone()[0],'COMPLETED')
        self.assertEqual(result['experiment']['status'],'REGISTERED')

if __name__=='__main__': unittest.main()
