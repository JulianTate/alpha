import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.laboratory import StrategyDefinition, compute_features, generate_hypotheses, temporal_splits, robustness, multiple_testing, research_gate

class LaboratoryTest(unittest.TestCase):
    def rows(self, n=80):
        from datetime import date, timedelta
        start=date(2025,1,1)
        return [{'timestamp':f'{start+timedelta(days=i)}T00:00:00+00:00','close':100+i,'high':101+i,'low':99+i,'volume':1000+i} for i in range(n)]
    def test_identical_strategy_definitions_have_identical_fingerprint(self):
        kwargs=dict(strategy_id='momentum',strategy_version='v1',hypothesis='q',universe=('AAPL',),features=('return_21d',),signal_conditions=('return_21d>0',),entry_rules=('next_open',),exit_rules=('horizon',),holding_horizon=5,parameters={'lookback':21},position_sizing='equal',transaction_cost_model={'bps':12},execution_assumptions={'next_session':True})
        self.assertEqual(StrategyDefinition(**kwargs).strategy_fingerprint,StrategyDefinition(**kwargs).strategy_fingerprint)
    def test_feature_at_index_cannot_use_future_rows(self):
        rows=self.rows()
        before=compute_features(rows,30)['daily_return']
        rows[79]['close']=999999
        after=compute_features(rows,30)['daily_return']
        self.assertEqual(before,after)
        self.assertEqual(compute_features(rows,30)['daily_return'].availability_timestamp,rows[30]['timestamp'])
    def test_controlled_hypotheses_and_nonoverlapping_partitions(self):
        hs=generate_hypotheses('MOMENTUM',(21,63),(5,),10)
        self.assertEqual(len(hs),2)
        parts=temporal_splits(self.rows(),('2025-01-01','2025-01-21'),('2025-01-21','2025-02-10'),('2025-02-10','2025-03-01'))
        self.assertEqual(set(parts),{'train','validation','oos'})
        with self.assertRaises(ValueError): temporal_splits(self.rows(),('2025-01-21','2025-01-01'),('2025-01-21','2025-02-10'),('2025-02-10','2025-03-01'))
    def test_multiple_testing_and_gate_are_explicit(self):
        diagnostics=multiple_testing([{'mean_return':.1},{'mean_return':-.1}])
        self.assertEqual(diagnostics['total_trials'],2)
        gate=research_gate({'trades':30,'max_drawdown':-.1},{'positive_neighbor_fraction':.8,'cost_sensitivity':[{'mean_return':.01}]})
        self.assertIn(gate['decision'],{'MONITOR','REJECTED'})

if __name__=='__main__': unittest.main()
