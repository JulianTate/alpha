import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.session_completeness import assess_session_completeness


class SessionCompletenessTest(unittest.TestCase):
    def test_missing_and_unexpected_sessions_are_blocked(self):
        result = assess_session_completeness(
            observed=["2026-01-02", "2026-01-04"],
            expected=["2026-01-02", "2026-01-03"],
        )
        self.assertEqual(result["status"], "SESSION_INCOMPLETE")
        self.assertEqual(result["missing_sessions"], ["2026-01-03"])
        self.assertEqual(result["unexpected_sessions"], ["2026-01-04"])

    def test_declared_complete_calendar_is_ready(self):
        result = assess_session_completeness(
            observed=["2026-01-02", "2026-01-03"],
            expected=["2026-01-02", "2026-01-03"],
        )
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["calendar_declared"])


if __name__ == "__main__":
    unittest.main()
