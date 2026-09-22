import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.validation_summary import ensure_validation_summary_tables, persist_validation_summary


class ValidationSummaryTest(unittest.TestCase):
    def test_summary_is_immutable_and_deterministic(self):
        db = sqlite3.connect(":memory:")
        ensure_validation_summary_tables(db)
        args = dict(
            campaign_id="CAM-1", experiment_id="EXP-1", dataset_id="DS-1",
            walk_forward={"folds": [{"fold_id": 1}]},
            baseline={"benchmark_name": "BUY_AND_HOLD", "cumulative_return": .1},
            anti_overfitting={"trial_count": 3, "formal_inference_status": "NOT_IMPLEMENTED"},
            gate={"decision": "REJECTED_OR_INSUFFICIENT_EVIDENCE"},
        )
        first = persist_validation_summary(db, **args)
        second = persist_validation_summary(db, **args)
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM campaign_validation_summaries").fetchone()[0], 1)
        with self.assertRaises(ValueError):
            persist_validation_summary(db, **{**args, "summary_id": first["summary_id"], "baseline": {"benchmark_name": "DIFFERENT"}})


if __name__ == "__main__":
    unittest.main()
