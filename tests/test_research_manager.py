import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.research_manager import checkpoint_job, create_job, ensure_manager_tables, execute_job, resume_job, transition_job


class ResearchManagerTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_manager_tables(self.db)
        self.definition = {"campaign_id": "CAM-1", "experiment_id": "EXP-1", "dataset_id": "DS-1", "steps": ["prepare", "run", "report"]}

    def test_job_checkpoint_and_resume_are_deterministic(self):
        job = create_job(self.db, self.definition)
        self.assertEqual(create_job(self.db, self.definition)["job_id"], job["job_id"])
        transition_job(self.db, job["job_id"], "RUNNING")
        checkpoint = checkpoint_job(self.db, job["job_id"], ["prepare"])
        self.assertEqual(checkpoint["remaining_steps"], ["run", "report"])
        resumed = resume_job(self.db, job["job_id"])
        self.assertEqual(resumed["completed_steps"], ["prepare"])
        self.assertEqual(resumed["remaining_steps"], ["run", "report"])
        self.assertEqual(resumed["attempt"], 2)

    def test_execute_job_checkpoints_each_step_and_resumes_after_failure(self):
        job = create_job(self.db, self.definition)
        calls = []
        failed = {"run": True}
        def prepare(): calls.append("prepare")
        def run():
            calls.append("run")
            if failed["run"]:
                failed["run"] = False
                raise RuntimeError("bounded failure")
        def report(): calls.append("report")
        first = execute_job(self.db, job["job_id"], {"prepare": prepare, "run": run, "report": report})
        self.assertEqual(first["state"], "FAILED")
        self.assertEqual(first["completed_steps"], ["prepare"])
        self.assertEqual(calls, ["prepare", "run"])
        second = execute_job(self.db, job["job_id"], {"prepare": prepare, "run": run, "report": report})
        self.assertEqual(second["state"], "COMPLETED")
        self.assertEqual(calls, ["prepare", "run", "run", "report"])
        self.assertGreaterEqual(self.db.execute("SELECT COUNT(*) FROM research_manager_checkpoints").fetchone()[0], 3)

    def test_invalid_checkpoint_is_rejected(self):
        job = create_job(self.db, self.definition)
        with self.assertRaises(ValueError):
            checkpoint_job(self.db, job["job_id"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
