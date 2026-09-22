import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.shadow_validation import compare_champion_challenger


class ShadowValidationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.rows = [
            {"key": "a", "champion_probability": .7, "challenger_probability": .8, "realized_label": 1},
            {"key": "b", "champion_probability": .7, "challenger_probability": .2, "realized_label": 0},
            {"key": "c", "champion_probability": .7, "challenger_probability": .8, "realized_label": 0},
        ]

    def test_comparison_is_deterministic_and_manual_only(self):
        first = compare_champion_challenger(self.db, champion_version="champ-v1", challenger_version="chall-v1", observations=self.rows)
        second = compare_champion_challenger(self.db, champion_version="champ-v1", challenger_version="chall-v1", observations=list(reversed(self.rows)))
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        self.assertEqual(first["sample_count"], 3)
        self.assertTrue(first["paired_sample"])
        self.assertIn("champion_brier", first)
        self.assertIn("challenger_brier", first)
        self.assertFalse(first["promotion_authorized"])
        self.assertFalse(first["live_execution"])
        self.assertTrue(first["manual_review_required"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM shadow_validation_runs").fetchone()[0], 1)

    def test_invalid_observation_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_champion_challenger(self.db, champion_version="a", challenger_version="b", observations=[{"realized_label": 2, "champion_probability": .5, "challenger_probability": .5}])

    def test_duplicate_keys_and_same_versions_are_rejected(self):
        duplicate = [dict(self.rows[0], key="same"), dict(self.rows[1], key="same")]
        with self.assertRaises(ValueError):
            compare_champion_challenger(self.db, champion_version="a", challenger_version="b", observations=duplicate)
        with self.assertRaises(ValueError):
            compare_champion_challenger(self.db, champion_version="a", challenger_version="a", observations=self.rows)


if __name__ == "__main__":
    unittest.main()
