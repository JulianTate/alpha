import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.manager_report import recovery_report
from research.research_manager import checkpoint_job, create_job, ensure_manager_tables


class ManagerReportTest(unittest.TestCase):
    def test_report_exposes_recovery_without_executing(self):
        db = sqlite3.connect(":memory:")
        ensure_manager_tables(db)
        job = create_job(db, {"campaign_id": "CAM-1", "experiment_id": "EXP-1", "dataset_id": "DS-1", "steps": ["a", "b"]})
        checkpoint_job(db, job["job_id"], ["a"])
        report = recovery_report(db)
        self.assertEqual(report["action_required_jobs"], [job["job_id"]])
        self.assertEqual(report["jobs"][0]["remaining_steps"], ["b"])
        self.assertFalse(report["execution_performed"])


if __name__ == "__main__":
    unittest.main()
