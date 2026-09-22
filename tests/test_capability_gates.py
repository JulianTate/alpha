import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.capability_gates import assess_capabilities
from ingestion.data_engine import ProviderCapability


class CapabilityGatesTest(unittest.TestCase):
    def test_declared_provider_capability_is_not_overclaimed(self):
        capability = ProviderCapability(
            provider="fixture", max_history="known", symbol_limits="one", request_limits="known",
            rate_limits="known", interval_support="daily", corporate_action_support="declared",
            adjusted_or_raw_support="raw", point_in_time_support="not assumed",
            licensing_and_use_restrictions="check terms",
        )
        result = assess_capabilities([capability], provider_names=["fixture"])
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["items"][0]["status"], "DECLARED")

    def test_missing_capability_is_unresolved(self):
        result = assess_capabilities([], provider_names=["unknown"])
        self.assertEqual(result["status"], "CAPABILITY_UNRESOLVED")
        self.assertEqual(result["items"][0]["missing_fields"], ["interval_support", "corporate_action_support", "point_in_time_support"])


if __name__ == "__main__":
    unittest.main()
