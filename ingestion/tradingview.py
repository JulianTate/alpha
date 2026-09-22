"""Import user-exported TradingView chart CSV into Alpha.

TradingView exports are treated as a user-supplied research snapshot. Alpha
stores the original CSV hash through its normal raw snapshot mechanism and
imports only OHLCV bars; no TradingView credentials or scraping are used.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alpha
from .snapshot import save as save_snapshot


def _timestamp(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        # TradingView exports may use Unix seconds for some instruments.
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    for fmt in (None, '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y'):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if fmt is None else datetime.strptime(value, fmt)
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    raise ValueError(f'unsupported TradingView timestamp: {value!r}')


def import_csv(path: str | Path, ticker: str, source='tradingview-csv'):
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames: raise ValueError('CSV has no header')
    fields = {str(x).strip().lower(): x for x in reader.fieldnames}
    required = {'time', 'open', 'high', 'low', 'close'}
    missing = required - set(fields)
    if missing: raise ValueError(f'Missing TradingView CSV columns: {sorted(missing)}')
    rows=[]
    for row in reader:
        if not row.get(fields['time']) or not row.get(fields['close']): continue
        rows.append({'ticker': ticker.upper(), 'timestamp': _timestamp(row[fields['time']]),
                     'open_': float(row[fields['open']]), 'high': float(row[fields['high']]),
                     'low': float(row[fields['low']]), 'close': float(row[fields['close']]),
                     'volume': float(row[fields['volume']]) if fields.get('volume') and row.get(fields['volume']) else 0.0,
                     'source': source})
    if not rows: raise ValueError('CSV contained no usable price rows')
    snapshot = save_snapshot('market-tradingview-csv', {'csv': text}, {'source': source, 'path': str(path), 'ticker': ticker.upper()})
    for row in rows: alpha.add_price(**row)
    return {'status':'ok', 'ticker':ticker.upper(), 'count':len(rows), 'first':rows[0]['timestamp'], 'last':rows[-1]['timestamp'], 'snapshot_path':snapshot}
