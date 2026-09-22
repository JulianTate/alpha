import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alpha
from ingestion.tradingview import import_csv

class TradingViewImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); alpha.DB_PATH=Path(self.tmp.name)/'a.sqlite3'; alpha.init()
    def tearDown(self): self.tmp.cleanup()
    def test_imports_export_and_preserves_bars(self):
        csv_path=Path(self.tmp.name)/'NVDA.csv'
        csv_path.write_text('time,open,high,low,close,Volume\n2025-01-01,10,11,9,10.5,1000\n2025-01-02,10.5,12,10,11.5,1200\n',encoding='utf-8')
        result=import_csv(csv_path,'NVDA')
        self.assertEqual(result['count'],2)
        with alpha.conn() as c:
            self.assertEqual(c.execute('select count(*) from prices').fetchone()[0],2)
            self.assertEqual(c.execute('select source from prices').fetchone()[0],'tradingview-csv')
    def test_rejects_missing_columns(self):
        path=Path(self.tmp.name)/'bad.csv'; path.write_text('date,close\n2025-01-01,10\n')
        with self.assertRaises(ValueError): import_csv(path,'BAD')

if __name__=='__main__': unittest.main()
