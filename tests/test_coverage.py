import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.coverage import assess_coverage


class CoverageTest(unittest.TestCase):
    def test_partial_stale_and_future_observations_remain_explicit(self):
        rows = [
            {"ticker": "ABC", "market_timestamp": "2026-01-01T00:00:00+00:00"},
            {"ticker": "ABC", "market_timestamp": "2026-01-02T00:00:00+00:00"},
            {"ticker": "STALE", "market_timestamp": "2025-12-01T00:00:00+00:00"},
            {"ticker": "FUTURE", "market_timestamp": "2026-01-03T00:00:00+00:00"},
        ]
        result = assess_coverage(rows, symbols=["ABC", "STALE", "FUTURE", "MISSING"],
                                 requested_start="2026-01-01", requested_end="2026-01-03",
                                 as_of="2026-01-02", max_age_days=5)
        statuses = {item["symbol"]: item["status"] for item in result["items"]}
        self.assertEqual(statuses["ABC"], "PARTIAL")
        self.assertEqual(statuses["STALE"], "MISSING")
        self.assertEqual(statuses["FUTURE"], "INVALID_FUTURE_OBSERVATION")
        self.assertEqual(statuses["MISSING"], "MISSING")
        self.assertEqual(result["status"], "DATA_INCOMPLETE")

    def test_complete_coverage_is_deterministically_ready(self):
        rows = [{"symbol": "ABC", "timestamp": day} for day in
                ("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00")]
        result = assess_coverage(rows, symbols=["abc"], requested_start="2026-01-01", requested_end="2026-01-02")
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["summary"]["covered"], 1)


if __name__ == "__main__":
    unittest.main()
