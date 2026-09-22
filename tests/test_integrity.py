import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.integrity import assess_integrity_controls, CONTROL_NAMES


class IntegrityControlsTest(unittest.TestCase):
    def test_missing_controls_block_without_inference(self):
        result = assess_integrity_controls({})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(set(result["missing_controls"]), set(CONTROL_NAMES))
        self.assertFalse(result["live_execution"])

    def test_unverified_control_blocks(self):
        controls = {name: "SUPPORTED" for name in CONTROL_NAMES}
        controls["delistings"] = "UNVERIFIED"
        result = assess_integrity_controls(controls)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["controls"]["delistings"], "UNVERIFIED")

    def test_all_supported_is_ready_but_manual(self):
        result = assess_integrity_controls({name: "SUPPORTED" for name in CONTROL_NAMES})
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["manual_review_required"])


if __name__ == "__main__":
    unittest.main()
