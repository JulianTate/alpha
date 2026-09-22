import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.predictions import (ModelVersion, Prediction, ensure_prediction_tables,
                                  get_model_version, get_prediction, persist_prediction,
                                  register_model_version)


class PredictionTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        ensure_prediction_tables(self.connection)
        self.prediction = Prediction(
            "PRED-001", "EXP-001", "DS-001", "aapl", "2026-01-02T00:00:00+00:00",
            21, "LONG", 0.72, "momentum-v1", "features-abc",
        )

    def test_model_version_lineage_is_deterministic_and_immutable(self):
        model = ModelVersion('momentum-v1', 'MOMENTUM', 'code-1', 'features-v1', 'DS-TRAIN', {'lookback': 20})
        first = register_model_version(self.connection, model)
        second = register_model_version(self.connection, model)
        self.assertEqual(first['definition_hash'], second['definition_hash'])
        self.assertEqual(get_model_version(self.connection, 'momentum-v1')['parameters'], {'lookback': 20})
        changed = ModelVersion('momentum-v1', 'MOMENTUM', 'code-2', 'features-v1', 'DS-TRAIN', {'lookback': 20})
        with self.assertRaises(ValueError):
            register_model_version(self.connection, changed)

    def test_prediction_persistence_links_registered_model_lineage(self):
        model = ModelVersion('momentum-v1', 'MOMENTUM', 'code-1', 'features-v1', 'DS-TRAIN', {'lookback': 20})
        register_model_version(self.connection, model)
        stored = persist_prediction(self.connection, self.prediction)
        self.assertEqual(stored['model_definition_hash'], model.definition_hash)
        self.assertEqual(get_prediction(self.connection, 'PRED-001')['model_definition_hash'], model.definition_hash)

    def test_persistence_is_deterministic_and_idempotent(self):
        first = persist_prediction(self.connection, self.prediction)
        second = persist_prediction(self.connection, self.prediction)
        self.assertEqual(first["definition_hash"], second["definition_hash"])
        stored = get_prediction(self.connection, "PRED-001")
        self.assertEqual(stored["ticker"], "AAPL")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], 1)

    def test_existing_id_cannot_be_silently_overwritten(self):
        persist_prediction(self.connection, self.prediction)
        changed = Prediction(
            "PRED-001", "EXP-001", "DS-001", "aapl", "2026-01-02T00:00:00+00:00",
            21, "SHORT", 0.72, "momentum-v1", "features-abc",
        )
        with self.assertRaises(ValueError):
            persist_prediction(self.connection, changed)


if __name__ == "__main__":
    unittest.main()
