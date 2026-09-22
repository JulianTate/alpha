import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.backtest import CostModel
from research.holding_periods import compare_holding_periods


class HoldingPeriodTest(unittest.TestCase):
    def test_compares_horizons_after_costs_and_reports_liquidity_blocks(self):
        rows = [
            {'entry_price': 100, 'average_volume': 10, 'exit_prices': {1: 101, 5: 104}},
            {'entry_price': 100, 'average_volume': 10, 'exit_prices': {1: 99, 5: 103}},
            {'entry_price': 100, 'average_volume': 1, 'exit_prices': {1: 102, 5: 105}},
        ]
        result = compare_holding_periods(rows, [1, 5], quantity=1,
                                         cost=CostModel(fee_bps=0, half_spread_bps=0,
                                                        slippage_bps=0, max_participation=.5),
                                         minimum_observations=2)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['horizons']['1']['status'], 'COMPLETE')
        self.assertEqual(result['horizons']['1']['observations'], 2)
        self.assertEqual(result['horizons']['1']['excluded']['liquidity_blocked'], 1)
        self.assertEqual(result['horizons']['5']['net_pnl'], 7)

    def test_missing_horizon_remains_insufficient(self):
        result = compare_holding_periods([{'entry_price': 100, 'exit_prices': {1: 101}}],
                                         [1, 5], minimum_observations=2)
        self.assertEqual(result['status'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['horizons']['5']['status'], 'INSUFFICIENT_DATA')
        self.assertEqual(result['horizons']['5']['excluded']['missing'], 1)

    def test_invalid_horizons_rejected(self):
        with self.assertRaises(ValueError): compare_holding_periods([], [0])


if __name__ == '__main__':
    unittest.main()
