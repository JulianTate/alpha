import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.execution import OHLCV, Signal, ExecutionConfig, run_backtest

class ExecutionTest(unittest.TestCase):
    def bars(self, rows):
        return [OHLCV(f'2025-01-0{i+1}T00:00:00+00:00', *row) for i,row in enumerate(rows)]

    def test_signal_executes_next_session_not_same_bar(self):
        bars=self.bars([(100,101,99,100,1000),(105,106,104,105,1000),(106,107,105,106,1000)])
        result=run_backtest(bars,[Signal(bars[0].timestamp, stop=95, target=110)],ExecutionConfig(fee_bps=0,spread_bps=0,slippage_bps=0))
        self.assertEqual(result['fills'][0]['entry_timestamp'],bars[1].timestamp)
        self.assertNotEqual(result['fills'][0]['entry_timestamp'],bars[0].timestamp)

    def test_stop_target_ambiguity_uses_conservative_stop(self):
        bars=self.bars([(100,100,100,100,1000),(100,110,90,105,1000),(100,100,100,100,1000)])
        result=run_backtest(bars,[Signal(bars[0].timestamp, stop=95, target=108)],ExecutionConfig(fee_bps=0,spread_bps=0,slippage_bps=0))
        self.assertEqual(result['fills'][0]['exit_reason'],'STOP_CONSERVATIVE_AMBIGUITY')
        self.assertLess(result['fills'][0]['net_pnl'],0)

    def test_gap_through_stop_and_costs_are_recorded(self):
        bars=self.bars([(100,100,100,100,1000),(90,95,89,92,1000)])
        result=run_backtest(bars,[Signal(bars[0].timestamp, stop=95, target=110)],ExecutionConfig(fee_bps=10,spread_bps=5,slippage_bps=5))
        fill=result['fills'][0]
        self.assertEqual(fill['exit_reason'],'STOP_GAP')
        self.assertGreater(fill['total_cost'],0)
        self.assertLess(fill['net_pnl'],fill['gross_pnl'])

if __name__=='__main__': unittest.main()
