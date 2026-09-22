import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.promotion_gates import evaluate_promotion_gate


class PromotionGateTest(unittest.TestCase):
    def test_insufficient_evidence_is_rejected_without_guessing(self):
        result = evaluate_promotion_gate(dataset_status="FROZEN", scorecard=None)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["decision"], "REJECTED_OR_INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["live_execution"])

    def test_strong_declared_evidence_is_only_eligible_for_human_review(self):
        result = evaluate_promotion_gate(
            dataset_status="FROZEN",
            scorecard={"status": "COMPLETE", "evaluation_scope": "LOCKED-OOS", "sample_count": 40, "accuracy": 0.60, "brier_score": 0.18, "calibration": {"0": {"count": 40}}},
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["decision"], "ELIGIBLE_FOR_HUMAN_REVIEW")
        self.assertFalse(result["live_execution"])
        self.assertTrue(result["manual_review_required"])

    def test_incomplete_or_non_oos_scorecard_is_rejected(self):
        for scorecard in (
            {"status": "INSUFFICIENT_DATA", "evaluation_scope": "LOCKED-OOS", "sample_count": 40, "accuracy": .60, "brier_score": .18, "calibration": {"0": {"count": 40}}},
            {"status": "COMPLETE", "evaluation_scope": "TRAIN", "sample_count": 40, "accuracy": .60, "brier_score": .18, "calibration": {"0": {"count": 40}}},
        ):
            result = evaluate_promotion_gate(dataset_status="FROZEN", scorecard=scorecard)
            self.assertFalse(result["eligible"])


if __name__ == "__main__":
    unittest.main()
