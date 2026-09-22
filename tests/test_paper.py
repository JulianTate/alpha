import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.paper import ensure_paper_tables, create_candidate, record_observation, paper_report

class PaperTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        ensure_paper_tables(self.c)
    def candidate(self):
        return {'ticker':'AAPL','direction':'BUY','timestamp':'2026-09-20T00:00:00+00:00','confidence_band':'WEAK_OR_MIXED','entry_price':100,'stop_price':95,'target_price':110,'signals':[{'strategy':'SMA trend'}],'warnings':['descriptive only']}
    def test_candidate_is_pending_review_and_manual_observations_change_only_paper_state(self):
        result=create_candidate(self.c,self.candidate(),source_run_id='RUN-TEST')
        self.assertEqual(result['status'],'PENDING_REVIEW')
        observed=record_observation(self.c,result['candidate_id'],'MANUAL_ENTRY',observed_price=101,manual_fill_price=101)
        self.assertEqual(observed['status'],'OPEN_MANUAL')
        report=paper_report(self.c)
        self.assertTrue(report['paper_only'])
        self.assertFalse(report['live_orders'])
        self.assertEqual(report['counts']['open_manual'],1)
    def test_insufficient_evidence_is_rejected(self):
        row=self.candidate(); row['confidence_band']='INSUFFICIENT_EVIDENCE'
        with self.assertRaises(ValueError): create_candidate(self.c,row)

if __name__=='__main__': unittest.main()
