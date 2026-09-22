"""Read-only Jarvis-facing query helpers; no broker operations exist here."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alpha import conn, init, propagate, report

def answer(question=''):
    init(); q=question.lower()
    with conn() as c:
        if 'open' in q: rows=c.execute("SELECT ticker,quantity,entry_price,entry_timestamp,signal_id FROM manual_trades WHERE status='OPEN'").fetchall(); return [dict(r) for r in rows]
        if 'signal' in q or 'interesting' in q: rows=c.execute("SELECT s.signal_id,c.ticker,s.strategy,s.score,s.expected_horizon,s.thesis,s.status FROM signals s JOIN companies c ON c.id=s.company_id ORDER BY s.score DESC LIMIT 10").fetchall(); return [dict(r) for r in rows]
        return report()
