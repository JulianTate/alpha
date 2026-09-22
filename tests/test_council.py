import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.council import ensure_council_tables, run_council


class CouncilTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE companies(id INTEGER PRIMARY KEY, ticker TEXT UNIQUE, name TEXT, sector TEXT, market_cap REAL);
            CREATE TABLE securities(id INTEGER PRIMARY KEY, company_id INTEGER, ticker TEXT);
            CREATE TABLE prices(id INTEGER PRIMARY KEY, security_id INTEGER, market_timestamp TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
            CREATE TABLE events(id INTEGER PRIMARY KEY, company_id INTEGER, event_type TEXT, headline TEXT, published_at TEXT, available_at TEXT, direction TEXT, strength REAL, facts_json TEXT);
        ''')
        self.db.execute("INSERT INTO companies VALUES(1,'ABC','ABC Corp','Technology',1000000)")
        self.db.execute("INSERT INTO securities VALUES(1,1,'ABC')")
        for i in range(30):
            day = f'2026-01-{i+1:02d}'
            close = 100 + i
            self.db.execute("INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)", (i+1, 1, day, close-1, close+1, close-2, close, 1000))
        self.db.commit()

    def test_missing_domains_reject_review_and_store_paper_only_run(self):
        report = run_council(self.db, ticker='ABC', as_of='2026-01-30T23:59:00+00:00')
        self.assertEqual(report['decision'], 'REJECTED')
        self.assertTrue(report['paper_only'])
        self.assertFalse(report['live_orders'])
        self.assertEqual(report['evidence_summary']['price_bars'], 30)
        self.assertIn('fundamental', report['evidence_summary']['missing_domains'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_council_runs').fetchone()[0], 1)

    def test_same_inputs_have_same_evidence_and_different_run_ids(self):
        first = run_council(self.db, ticker='ABC', as_of='2026-01-30T23:59:00+00:00')
        second = run_council(self.db, ticker='ABC', as_of='2026-01-30T23:59:00+00:00')
        self.assertEqual(first['input_hash'], second['input_hash'])
        self.assertEqual(first['output_hash'], second['output_hash'])
        self.assertNotEqual(first['run_id'], second['run_id'])

    def test_no_price_history_is_blocked(self):
        report = run_council(self.db, ticker='MISSING', as_of='2026-01-30T23:59:00+00:00')
        self.assertEqual(report['decision'], 'REJECTED')
        self.assertTrue(report['risk_review']['veto'])
        self.assertFalse(report['evidence_summary']['company_found'])


if __name__ == '__main__':
    unittest.main()
