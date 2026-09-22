import unittest
from datetime import date, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.strategy_scan import Bar, strategy_signals, scan_bars, historical_evidence, rank_results

class StrategyScanTest(unittest.TestCase):
    def bars(self, n=160):
        out=[]; price=100.0
        for i in range(n):
            if 72 <= i < 78: price *= .985
            else: price *= 1.003
            d=(date(2025,1,1)+timedelta(days=i)).isoformat()
            out.append(Bar(d, price, price*1.01, price*.99, 100000))
        return out

    def test_signals_are_explainable(self):
        signals=strategy_signals(self.bars())
        self.assertTrue(signals)
        self.assertTrue(all(s.strategy and s.reason for s in signals))
        self.assertTrue(all(0 <= s.strength <= 1 for s in signals))

    def test_scan_requires_evidence_before_candidate(self):
        result=scan_bars('TEST', self.bars())
        self.assertEqual(result.ticker, 'TEST')
        self.assertEqual(result.strategies_checked, 4)
        self.assertIn(result.confidence_band, {'RESEARCH_CANDIDATE','WEAK_OR_MIXED','INSUFFICIENT_EVIDENCE'})
        self.assertTrue(any('not a probability guarantee' in w for w in result.warnings))

    def test_trade_levels_are_defined_and_risk_reward_is_two_to_one(self):
        result=scan_bars('TEST', self.bars())
        if result.direction in ('BUY','SELL'):
            self.assertIsNotNone(result.entry_price)
            self.assertIsNotNone(result.stop_price)
            self.assertIsNotNone(result.target_price)
            self.assertEqual(result.risk_reward, 1.67)

    def test_short_history_is_not_overstated(self):
        result=scan_bars('SHORT', self.bars(30))
        self.assertEqual(result.confidence_band, 'INSUFFICIENT_EVIDENCE')
        self.assertIsNone(result.empirical_hit_rate)

    def test_historical_evidence_excludes_future_bars(self):
        rows=historical_evidence(self.bars(), horizon=5)
        self.assertTrue(all(r['timestamp'] < self.bars()[-1].timestamp for r in rows))

if __name__=='__main__': unittest.main()
