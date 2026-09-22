import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.dataset_contract import ensure_dataset_contract_tables, register_dataset_contract


class DatasetContractTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_dataset_contract_tables(self.db)
        self.metadata = {
            "dataset_id": "DS-001",
            "universe_definition": ["aapl", "MSFT"],
            "as_of_policy": "information_available_at_market_close",
            "corporate_action_policy": "adjusted_prices_with_raw_snapshot_retained",
            "survivorship_policy": "historical_constituents_and_delisted_names_retained",
            "source_snapshot_hash": "snapshot-abc",
            "quality_status": "VALID",
        }

    def test_contract_is_normalized_deterministic_and_idempotent(self):
        first = register_dataset_contract(self.db, self.metadata)
        second = register_dataset_contract(self.db, {**self.metadata, "universe_definition": ["MSFT", "aapl"]})
        self.assertEqual(first["contract_hash"], second["contract_hash"])
        self.assertEqual(first["universe_definition"], ["AAPL", "MSFT"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM dataset_reconstruction_records").fetchone()[0], 1)

    def test_changed_contract_or_nonvalid_data_is_rejected(self):
        register_dataset_contract(self.db, self.metadata)
        with self.assertRaises(ValueError):
            register_dataset_contract(self.db, {**self.metadata, "survivorship_policy": "current_names_only"})
        with self.assertRaises(ValueError):
            register_dataset_contract(self.db, {**self.metadata, "dataset_id": "DS-002", "quality_status": "UNRESOLVED"})


if __name__ == "__main__":
    unittest.main()
