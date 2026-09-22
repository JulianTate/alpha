import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alpha


class AlphaWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        alpha.DB_PATH = Path(self.tmp.name) / 'test.sqlite3'
        alpha.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_event_graph_signal_trade(self):
        eid = alpha.ingest_event('A', 'contract', 'A wins contract', source='test')
        alpha.add_relationship('A', 'B', 'supplier', 'positive', .8, 'filing', exposure=.7)
        candidates = alpha.propagate(eid)
        self.assertEqual(candidates[0]['ticker'], 'B')
        signal = alpha.make_signal(eid, candidates[0], 10)
        alpha.buy(signal, 'B', 2, 10)
        out = alpha.sell(signal, 11)
        self.assertAlmostEqual(out['gross_pnl'], 2)
        self.assertGreater(out['return_pct'], 9)

    def test_freeze_blocks_active_universe_symbol_without_observations(self):
        alpha.add_price('ABC', '2026-01-01T00:00:00+00:00', 100, open_=99, high=101, low=98)
        alpha.add_price('ABC', '2026-01-02T00:00:00+00:00', 101, open_=100, high=102, low=99)
        alpha.add_company('MISSING')
        result = alpha.data_freeze()
        self.assertEqual(result['status'], 'DATA_BLOCKED')
        self.assertEqual(result['missing_symbols'], ['MISSING'])

    def test_freeze_blocks_declared_session_gap(self):
        alpha.add_price('ABC', '2026-01-01T00:00:00+00:00', 100, open_=99, high=101, low=98)
        alpha.add_price('ABC', '2026-01-03T00:00:00+00:00', 101, open_=100, high=102, low=99)
        result = alpha.data_freeze(expected_sessions=['2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00', '2026-01-03T00:00:00+00:00'])
        self.assertEqual(result['status'], 'DATA_BLOCKED')
        self.assertEqual(result['session_reports']['ABC']['missing_sessions'], ['2026-01-02T00:00:00+00:00'])


if __name__ == '__main__':
    unittest.main()
