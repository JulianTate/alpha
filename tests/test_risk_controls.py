import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.risk_controls import classify_regime, concentration_report


class RiskControlsTest(unittest.TestCase):
    def test_regime_is_explicit_when_inputs_missing(self):
        self.assertEqual(classify_regime(trend_return=None, volatility=0.01), "UNRESOLVED")
        self.assertEqual(classify_regime(trend_return=0.1, volatility=0.04), "HIGH_VOLATILITY_UP")

    def test_concentration_blocks_position_and_sector_breaches(self):
        result = concentration_report([
            {"ticker": "AAA", "sector": "TECH", "weight": 0.6},
            {"ticker": "BBB", "sector": "TECH", "weight": 0.2},
            {"ticker": "CCC", "sector": "HEALTH", "weight": 0.2},
        ])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("position:AAA", result["violations"])
        self.assertIn("sector:TECH", result["violations"])
        self.assertTrue(result["manual_review_required"])


if __name__ == "__main__":
    unittest.main()
