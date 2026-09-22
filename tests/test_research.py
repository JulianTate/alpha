import unittest
from pathlib import Path
import tempfile, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha
from research.reaction import event_reaction
from research.backtest import CostModel, simulate_trade, summarize

class ResearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); alpha.DB_PATH=Path(self.tmp.name)/'a.sqlite3'; alpha.init()
    def tearDown(self): self.tmp.cleanup()
    def test_reaction_and_abnormal_return(self):
        alpha.add_price('XYZ','2026-01-02T00:00:00+00:00',100)
        alpha.add_price('XYZ','2026-01-05T00:00:00+00:00',110)
        alpha.add_price('SPY','2026-01-02T00:00:00+00:00',100)
        alpha.add_price('SPY','2026-01-05T00:00:00+00:00',105)
        eid=alpha.ingest_event('XYZ','8-K','test event',published_at='2026-01-01T12:00:00+00:00',available_at='2026-01-02T00:00:00+00:00',source='test')
        result=event_reaction(eid,'XYZ','SPY',horizons={'1-3d':3})
        self.assertEqual(result['status'],'ok'); self.assertAlmostEqual(result['reactions'][0]['abnormal_return_pct'],5.0)
        self.assertIn('mfe_pct',result['reactions'][0]); self.assertIn('volatility_pct',result['reactions'][0])
    def test_costs_and_liquidity(self):
        r=simulate_trade('XYZ',10,100,110,3,cost=CostModel(fee_bps=10,half_spread_bps=10,slippage_bps=10))
        self.assertLess(r.net_pnl,r.gross_pnl); self.assertEqual(summarize([r])['trades'],1)
        with self.assertRaises(ValueError): simulate_trade('XYZ',101,100,110,3,average_volume=100)

if __name__=='__main__': unittest.main()
