import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.anti_overfitting import selection_diagnostics


class AntiOverfittingTest(unittest.TestCase):
    def test_diagnostics_expose_selection_pressure_without_formal_claim(self):
        result = selection_diagnostics([
            {"trial_id": "A", "validation_return": .04, "oos_return": .01},
            {"trial_id": "B", "validation_return": .06, "oos_return": -.02},
            {"trial_id": "C", "validation_return": .02, "oos_return": .03},
        ], selected_trial_id="C")
        self.assertEqual(result["trial_count"], 3)
        self.assertEqual(result["selected_rank"], 1)
        self.assertTrue(result["selection_bias_warning"])
        self.assertEqual(result["formal_inference_status"], "NOT_IMPLEMENTED")

    def test_empty_trials_are_blocked(self):
        with self.assertRaises(ValueError):
            selection_diagnostics([])


if __name__ == "__main__":
    unittest.main()
