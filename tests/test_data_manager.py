import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.data_manager import plan_update


class DataManagerTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
            CREATE TABLE companies(id INTEGER PRIMARY KEY, ticker TEXT, active INTEGER);
            CREATE TABLE securities(id INTEGER PRIMARY KEY, company_id INTEGER, ticker TEXT);
            CREATE TABLE prices(security_id INTEGER, market_timestamp TEXT, close REAL);
        ''')
        self.db.execute("INSERT INTO companies VALUES (1,'ABC',1)")
        self.db.execute("INSERT INTO securities VALUES (1,1,'ABC')")
        self.db.executemany("INSERT INTO prices VALUES (?,?,?)", [(1,'2026-01-01',100),(1,'2026-01-02',101)])
        self.db.commit()

    def test_missing_and_partial_coverage_are_explicit(self):
        plan = plan_update(self.db, symbols=['ABC', 'MISSING'], start='2026-01-01', end='2026-01-03')
        self.assertEqual(plan['status'], 'DATA_INCOMPLETE')
        self.assertEqual(plan['summary']['covered'], 0)
        self.assertEqual(plan['summary']['incomplete'], 2)
        self.assertEqual(plan['items'][0]['status'], 'PARTIAL')
        self.assertEqual(plan['items'][1]['status'], 'MISSING')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM data_manager_runs').fetchone()[0], 1)

    def test_complete_coverage_is_no_action(self):
        plan = plan_update(self.db, symbols=['ABC'], start='2026-01-01', end='2026-01-02')
        self.assertEqual(plan['status'], 'READY')
        self.assertEqual(plan['items'][0]['action'], 'NO_ACTION')
        self.assertEqual(plan['plan_hash'], plan_update(self.db, symbols=['ABC'], start='2026-01-01', end='2026-01-02')['plan_hash'])


if __name__ == '__main__':
    unittest.main()
