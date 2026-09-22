"""Bounded, evidence-first research council for Alpha Phase 3.

This is an orchestration and review layer, not an autonomous trading agent.
Each analyst emits structured observations from persisted Alpha data. The
synthesis is deterministic, stores its input/output fingerprint, and can only
produce a paper/manual recommendation. Missing evidence lowers confidence or
blocks the recommendation; it is never invented.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def ensure_council_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS research_council_runs(
        run_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, as_of TEXT NOT NULL,
        input_hash TEXT NOT NULL, output_hash TEXT NOT NULL, report_json TEXT NOT NULL,
        status TEXT NOT NULL, paper_only INTEGER NOT NULL, live_orders INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")


def _prices(connection: sqlite3.Connection, ticker: str, as_of: str, max_bars: int | None = None) -> list[dict]:
    query = """SELECT p.market_timestamp,p.open,p.high,p.low,p.close,p.volume
      FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies c ON c.id=s.company_id
      WHERE c.ticker=? AND p.market_timestamp<=? ORDER BY p.market_timestamp"""
    args = (ticker.upper(), as_of)
    if max_bars is not None:
        query = """SELECT * FROM (""" + query + """ DESC LIMIT ?) ORDER BY market_timestamp"""
        args = args + (int(max_bars),)
    rows = connection.execute(query, args).fetchall()
    return [dict(timestamp=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]


def _company(connection: sqlite3.Connection, ticker: str) -> dict | None:
    row = connection.execute("SELECT id,ticker,name,sector,market_cap FROM companies WHERE ticker=?", (ticker.upper(),)).fetchone()
    return dict(row) if row else None


def _events(connection: sqlite3.Connection, ticker: str, as_of: str) -> list[dict]:
    rows = connection.execute("""SELECT e.id,e.event_type,e.headline,e.published_at,e.available_at,e.direction,e.strength,e.facts_json
      FROM events e JOIN companies c ON c.id=e.company_id
      WHERE c.ticker=? AND COALESCE(e.available_at,e.published_at)<=? ORDER BY COALESCE(e.available_at,e.published_at),e.id""", (ticker.upper(), as_of)).fetchall()
    return [dict(r) for r in rows]


def _technical(ticker: str, bars: list[dict]) -> dict:
    closes = [float(r["close"]) for r in bars if r["close"] is not None]
    evidence = {"bars": len(closes), "latest_timestamp": bars[-1]["timestamp"] if bars else None}
    if len(closes) < 21:
        return {"analyst": "technical", "status": "BLOCKED", "stance": "UNKNOWN", "confidence": 0.0,
                "observations": ["At least 21 point-in-time closes are required for the technical review."], "evidence": evidence}
    latest = closes[-1]
    sma20 = sum(closes[-20:]) / 20
    ret20 = latest / closes[-21] - 1 if closes[-21] else 0.0
    stance = "POSITIVE" if latest > sma20 and ret20 > 0 else ("NEGATIVE" if latest < sma20 and ret20 < 0 else "MIXED")
    return {"analyst": "technical", "status": "READY", "stance": stance,
            "confidence": round(min(1.0, len(closes) / 252) * (0.7 if stance != "MIXED" else 0.4), 4),
            "observations": [f"Close is {latest:.4g}; 20-session average is {sma20:.4g}.", f"20-session return is {ret20:.2%}."],
            "evidence": evidence | {"sma20": sma20, "return20": ret20}}


def _fundamental(ticker: str, company: dict | None, events: list[dict]) -> dict:
    filings = [e for e in events if "filing" in str(e.get("event_type", "")).lower() or e.get("facts_json") not in (None, "{}", "")]
    if not company:
        return {"analyst": "fundamental", "status": "BLOCKED", "stance": "UNKNOWN", "confidence": 0.0,
                "observations": ["Company identity is unresolved."], "evidence": {"filings": 0}}
    if not filings:
        return {"analyst": "fundamental", "status": "UNRESOLVED", "stance": "UNKNOWN", "confidence": 0.0,
                "observations": ["No point-in-time filing/fundamental evidence is available."], "evidence": {"filings": 0, "sector": company.get("sector")}}
    return {"analyst": "fundamental", "status": "READY", "stance": "NEUTRAL", "confidence": 0.25,
            "observations": [f"{len(filings)} filing/fundamental event(s) are available as of the review time; facts require analyst interpretation."],
            "evidence": {"filings": len(filings), "event_ids": [e["id"] for e in filings], "sector": company.get("sector")}}


def _news(ticker: str, events: list[dict]) -> dict:
    news = [e for e in events if "news" in str(e.get("event_type", "")).lower()]
    if not news:
        return {"analyst": "news", "status": "UNRESOLVED", "stance": "UNKNOWN", "confidence": 0.0,
                "observations": ["No timestamped news metadata is available."], "evidence": {"events": 0}}
    direction = sum((float(e.get("strength") or 0) * (1 if e.get("direction") == "positive" else -1 if e.get("direction") == "negative" else 0)) for e in news)
    stance = "POSITIVE" if direction > 0 else "NEGATIVE" if direction < 0 else "MIXED"
    return {"analyst": "news", "status": "READY", "stance": stance, "confidence": round(min(0.6, len(news) / 10), 4),
            "observations": [f"{len(news)} timestamped news event(s) are available; metadata is not a substitute for licensed article content."],
            "evidence": {"events": len(news), "event_ids": [e["id"] for e in news], "weighted_direction": direction}}


def _macro(events: list[dict]) -> dict:
    macro = [e for e in events if any(term in str(e.get("event_type", "")).lower() for term in ("macro", "fred", "economic"))]
    return {"analyst": "macro", "status": "READY" if macro else "UNRESOLVED", "stance": "NEUTRAL" if macro else "UNKNOWN",
            "confidence": 0.2 if macro else 0.0,
            "observations": [f"{len(macro)} macro event(s) are available." if macro else "No point-in-time macro evidence is available."],
            "evidence": {"events": len(macro), "event_ids": [e["id"] for e in macro]}}


def _risk(analysts: list[dict], bars: list[dict], events: list[dict]) -> dict:
    blockers = []
    if len(bars) < 21: blockers.append("insufficient price history")
    if any(a["status"] in {"BLOCKED", "UNRESOLVED"} for a in analysts): blockers.append("one or more required analyst domains lack evidence")
    if not bars: blockers.append("no canonical price observations")
    return {"analyst": "risk", "status": "BLOCKED" if blockers else "READY", "veto": bool(blockers),
            "stance": "REJECT" if blockers else "CAUTIOUS", "confidence": 1.0 if blockers else 0.7,
            "observations": blockers or ["No hard data blocker detected; concentration, liquidity, event risk, and paper observation remain to be reviewed."],
            "evidence": {"bars": len(bars), "events": len(events), "blockers": blockers}}


def run_council(connection: sqlite3.Connection, *, ticker: str, as_of: str, required_domains: tuple[str, ...] = ("technical", "fundamental", "news", "macro"), max_price_bars: int | None = None) -> dict:
    """Run one deterministic council review; never creates orders or live signals."""
    ensure_council_tables(connection)
    ticker = ticker.upper()
    company = _company(connection, ticker)
    bars = _prices(connection, ticker, as_of, max_bars=max_price_bars)
    events = _events(connection, ticker, as_of)
    analysts = [_technical(ticker, bars), _fundamental(ticker, company, events), _news(ticker, events), _macro(events)]
    risk = _risk(analysts, bars, events)
    available = [a for a in analysts if a["status"] == "READY"]
    positive = sum(a["confidence"] for a in available if a["stance"] == "POSITIVE")
    negative = sum(a["confidence"] for a in available if a["stance"] == "NEGATIVE")
    missing = [a["analyst"] for a in analysts if a["analyst"] in required_domains and a["status"] != "READY"]
    decision = "REJECTED" if risk["veto"] or missing else ("PAPER_REVIEW" if positive != negative else "NO_EDGE")
    report = {"schema_version": 1, "ticker": ticker, "as_of": as_of, "paper_only": True, "live_orders": False,
              "decision": decision, "confidence": round(min(1.0, sum(a["confidence"] for a in available) / max(1, len(required_domains))), 4),
              "analysts": analysts, "risk_review": risk,
              "guardrails": ["No broker integration", "No live orders", "No automated execution", "No recommendation without point-in-time evidence"],
              "limitations": ["Council output is structured research evidence, not a guaranteed return or probability.", "News metadata is discovery evidence only.", "A PAPER_REVIEW decision requires separate campaign validation and manual approval."],
              "evidence_summary": {"company_found": company is not None, "price_bars": len(bars), "events": len(events), "missing_domains": missing}}
    input_payload = {"ticker": ticker, "as_of": as_of, "company": company, "bars": bars, "events": events, "required_domains": required_domains}
    report["input_hash"] = _hash(input_payload)
    report["output_hash"] = _hash(report)
    run_id = "COUNCIL-" + uuid.uuid4().hex[:16].upper()
    connection.execute("INSERT INTO research_council_runs VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, ticker, as_of, report["input_hash"], report["output_hash"], json.dumps(report, sort_keys=True), "COMPLETED", 1, 0, _now()))
    report["run_id"] = run_id
    return report
