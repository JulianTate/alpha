import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.validation import Observation, chronological_splits, assert_no_overlap, metrics, compare_horizons
from research.reporting import summarize_rows, select_oos

class ValidationTest(unittest.TestCase):
    def test_walk_forward_and_leakage_guard(self):
        rows=[Observation(f'2026-01-{d:02d}T12:00:00+00:00',f'2026-01-{d:02d}T11:00:00+00:00',0.01 if d%2 else -0.01,str(d)) for d in range(1,10)]
        splits=chronological_splits(rows,'2026-01-04T00:00:00+00:00','2026-01-07T00:00:00+00:00','2026-01-10T00:00:00+00:00')
        self.assertEqual([len(s.observations) for s in splits],[3,3,3]); self.assertTrue(assert_no_overlap(splits))
        bad=Observation('2026-01-01T12:00:00+00:00','2026-01-01T13:00:00+00:00',0.1,'bad')
        with self.assertRaises(ValueError): chronological_splits([bad],'2026-01-04T00:00:00+00:00','2026-01-07T00:00:00+00:00','2026-01-10T00:00:00+00:00')
    def test_reporting_keeps_split_strategy_and_horizon_separate(self):
        rows=[{'split':'train','strategy':'s1','horizon':'1-3d','net_return':0.01},{'split':'test','strategy':'s1','horizon':'1-3d','net_return':-0.02},{'split':'test','strategy':'s2','horizon':'10-30d','net_return':0.03}]
        report=summarize_rows(rows)
        self.assertEqual(report['overall']['trades'],3); self.assertEqual(report['by_split']['test']['trades'],2); self.assertEqual(len(select_oos(rows)),2)

    def test_metrics_and_horizon_comparison(self):
        result=metrics([0.10,-0.05,-0.02,0.03],capital_time=10,turnover=100,utilised_capital=50)
        self.assertEqual(result['longest_losing_streak'],2); self.assertGreater(result['max_drawdown'],0); self.assertAlmostEqual(result['return_per_capital_time'],0.006)
        compared=compare_horizons([{'horizon':'1-3d','net_return':0.02,'capital_time':2,'turnover':10,'capital':5},{'horizon':'10-30d','net_return':0.01,'capital_time':10,'turnover':10,'capital':5}])
        self.assertGreater(compared['1-3d']['return_per_capital_time'],compared['10-30d']['return_per_capital_time'])

if __name__=='__main__': unittest.main()
