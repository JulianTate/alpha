import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.validation import Observation
from research.walk_forward import build_walk_forward_folds


class WalkForwardTest(unittest.TestCase):
    def test_expanding_folds_have_locked_nonoverlapping_tests(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        observations = [
            Observation((start + timedelta(days=i)).isoformat(), (start + timedelta(days=i)).isoformat(), float(i % 2), str(i))
            for i in range(90)
        ]
        folds = build_walk_forward_folds(
            observations,
            train_ends=["2026-01-31T00:00:00+00:00", "2026-02-15T00:00:00+00:00"],
            validation_span_days=10,
            test_span_days=10,
        )
        self.assertEqual(len(folds), 2)
        self.assertGreater(len(folds[1].train), len(folds[0].train))
        self.assertEqual(len(folds[0].test), 10)
        self.assertEqual(len(folds[1].test), 10)
        self.assertEqual(set(item.key for item in folds[0].test).intersection(item.key for item in folds[1].test), set())

    def test_lookahead_is_rejected(self):
        with self.assertRaises(ValueError):
            build_walk_forward_folds([
                Observation("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", 1, "bad")
            ], train_ends=["2026-01-03T00:00:00+00:00"], validation_span_days=1, test_span_days=1)


if __name__ == "__main__":
    unittest.main()
