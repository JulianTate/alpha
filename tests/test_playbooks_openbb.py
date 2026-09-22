import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.openbb import guarded_result, normalize_news_rows, normalize_price_rows
from research.playbooks import ensure_playbook_tables, list_playbooks, register_builtin_playbooks


class PlaybookAndOpenBBTest(unittest.TestCase):
    def test_builtin_playbooks_are_registered_and_immutable(self):
        connection = sqlite3.connect(':memory:')
        ensure_playbook_tables(connection)
        first = register_builtin_playbooks(connection)
        second = register_builtin_playbooks(connection)
        self.assertEqual([item['definition_hash'] for item in first], [item['definition_hash'] for item in second])
        self.assertEqual(len(list_playbooks(connection)), 3)
        self.assertTrue(all(item['status'] == 'HYPOTHESIS' for item in first))

    def test_openbb_rows_are_normalized_without_repair(self):
        rows = normalize_price_rows([{
            'date': '2026-01-02', 'open': 10, 'high': 12,
            'low': 9, 'close': 11, 'volume': 100,
        }])
        self.assertEqual(rows[0]['market_timestamp'], '2026-01-02T00:00:00+00:00')
        self.assertEqual(rows[0]['close'], 11)
        self.assertIsNone(normalize_price_rows([{'date': '2026-01-02', 'close': 11}])[0]['open'])

    def test_openbb_news_is_metadata_only_and_guarded(self):
        news = normalize_news_rows([{'headline': 'Example', 'link': 'https://example.test', 'date': '2026-01-02'}])
        self.assertEqual(news[0]['title'], 'Example')
        self.assertNotIn('body', news[0])
        result = guarded_result([{'date': '2026-01-02', 'close': 11}], kind='prices')
        self.assertEqual(result['status'], 'UNVALIDATED')
        self.assertIn('alpha_validate_rows', result['gates'])


if __name__ == '__main__':
    unittest.main()
