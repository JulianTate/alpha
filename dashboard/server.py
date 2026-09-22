"""Local Alpha research cockpit: local scans, council evidence and reports only."""
from __future__ import annotations
import json, os, sqlite3, sys
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
# When launched as ``python dashboard\\server.py``, Python puts dashboard/
# on sys.path rather than the Alpha project root. Add the project root so the
# existing research and ingestion packages remain available.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_PATH = Path(os.getenv("ALPHA_DB", ROOT / "database" / "alpha.sqlite3"))
WEB = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(WEB), static_url_path="")


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def rows(c, query, args=()):
    return [dict(r) for r in c.execute(query, args).fetchall()]


def table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def bars(c, ticker):
    return rows(c, """SELECT p.market_timestamp AS timestamp,p.open,p.high,p.low,p.close,p.volume
        FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies co ON co.id=s.company_id
        WHERE co.ticker=? ORDER BY p.market_timestamp""", (ticker,))


def local_scan(ticker, data):
    """Run the existing deterministic scanner; this never calls a model or places an order."""
    from research.strategy_scan import Bar, scan_bars, result_dict
    if not data:
        return {"ticker": ticker, "confidence_band": "NO_DATA", "warnings": ["No stored price history."]}
    if len(data) < 50:
        return {"ticker": ticker, "confidence_band": "INSUFFICIENT_EVIDENCE", "warnings": [f"Only {len(data)} bars; scanner requires 50."]}
    # Interactive scans use a bounded recent window so the local dashboard stays responsive.
    # Full historical testing remains in the campaign/laboratory pipeline.
    data = data[-600:]
    converted = [Bar(x["timestamp"], float(x["close"]), float(x["high"] or x["close"]), float(x["low"] or x["close"]), float(x["volume"] or 0)) for x in data]
    return result_dict(scan_bars(ticker, converted, horizon=5))


def report_cards(c):
    result = []
    if table(c, "laboratory_reports"):
        for r in rows(c, "SELECT campaign_id,report_json,created_at FROM laboratory_reports ORDER BY created_at DESC LIMIT 8"):
            try:
                report = json.loads(r.pop("report_json"))
                result.append({"campaign_id": r["campaign_id"], "created_at": r["created_at"], "decision": report.get("decision"), "strategy_family": report.get("strategy_family"), "dataset_id": report.get("dataset_id"), "results": report.get("results", {}), "experiment_counts": report.get("experiment_counts", {})})
            except json.JSONDecodeError:
                continue
    return result


def _review_summary(scan, council):
    """Build a descriptive end-stage review summary; never authorizes execution."""
    band = scan.get("confidence_band", "NO_DATA")
    council_decision = (council or {}).get("decision", "UNRESOLVED")
    checks = {
        "historical_evidence": band in {"RESEARCH_CANDIDATE", "WEAK_OR_MIXED"},
        "strategy_agreement": int(scan.get("agreement", 0)) >= 2,
        "paper_review": council_decision == "PAPER_REVIEW",
        "manual_execution_only": True,
    }
    blockers = list(scan.get("warnings", []))
    if council and council_decision != "PAPER_REVIEW":
        blockers.append(f"Council decision: {council_decision}")
    return {
        "status": "REVIEW" if band == "RESEARCH_CANDIDATE" and council_decision == "PAPER_REVIEW" else "BLOCKED_OR_REVIEW",
        "checks": checks,
        "blockers": blockers,
        "manual_review_required": True,
        "live_execution": False,
    }


def build_overview(run_council_reviews=False):
    from research.council import run_council
    with db() as c:
        companies = rows(c, "SELECT ticker,name,sector FROM companies WHERE active=1 ORDER BY ticker")
        stocks = []
        for company in companies:
            ticker = company["ticker"]
            history = bars(c, ticker)
            scan = local_scan(ticker, history)
            signal = rows(c, """SELECT signal_id,direction,score,expected_horizon,entry_low,entry_high,invalidation,status,thesis,bear_case,created_at
                FROM signals WHERE company_id=(SELECT id FROM companies WHERE ticker=?) ORDER BY created_at DESC LIMIT 1""", (ticker,))
            if run_council_reviews:
                # The council is deterministic and persisted for auditability; it is not an AI call.
                council = run_council(c, ticker=ticker, as_of=(history[-1]["timestamp"] if history else "9999-12-31T23:59:59+00:00"), max_price_bars=600)
            else:
                council_rows = rows(c, "SELECT report_json FROM research_council_runs WHERE ticker=? ORDER BY created_at DESC LIMIT 1", (ticker,)) if table(c, "research_council_runs") else []
                council = json.loads(council_rows[0]["report_json"]) if council_rows else None
            latest = history[-1] if history else None
            review = _review_summary(scan, council)
            stocks.append({**company, "bars": history[-120:], "latest": latest, "scan": scan,
                           "signal": signal[0] if signal else None, "council": council,
                           "review": review})
        order = {"RESEARCH_CANDIDATE": 0, "WEAK_OR_MIXED": 1,
                 "INSUFFICIENT_EVIDENCE": 2, "NO_DATA": 3}
        stocks.sort(key=lambda item: (order.get(item["scan"].get("confidence_band"), 9),
                                      -(item["scan"].get("setup_score") or 0),
                                      -(item["scan"].get("empirical_hit_rate") or 0),
                                      item["ticker"]))
        # Show the best available daily research result even when no setup clears
        # the stricter validation band. This is a shortlist, never an execution gate.
        candidates = [item for item in stocks if item["scan"].get("confidence_band") in {"RESEARCH_CANDIDATE", "WEAK_OR_MIXED"}][:5]
        validated = [item for item in stocks if item["scan"].get("confidence_band") == "RESEARCH_CANDIDATE"]
        reviewable = [item for item in stocks if item["review"]["status"] == "REVIEW"]
        data = c.execute("SELECT COUNT(*) n,MIN(market_timestamp) first_ts,MAX(market_timestamp) last_ts FROM prices").fetchone()
        return {"stocks": stocks, "candidates": candidates, "validated_count": len(validated), "reviewable_count": len(reviewable),
                "data": {"rows": data["n"], "start": data["first_ts"], "end": data["last_ts"]},
                "reports": report_cards(c), "mode": "PAPER / MANUAL ONLY", "cloud_model": "ON DEMAND ONLY",
                "delivery": {"status": "NOT_CONFIGURED", "channel": "Telegram adapter available; phone delivery requires setup"}}


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/api/overview")
def overview():
    return jsonify(build_overview(False))


@app.post("/api/refresh")
def refresh():
    # Explicit user action: local strategy scans plus deterministic council persistence.
    return jsonify(build_overview(True))


@app.get("/api/reports")
def reports():
    with db() as c:
        return jsonify({"reports": report_cards(c)})


@app.get("/api/stock/<ticker>")
def stock(ticker):
    payload = build_overview(False)
    item = next((x for x in payload["stocks"] if x["ticker"] == ticker.upper()), None)
    return jsonify(item) if item else (jsonify({"error": "ticker not found"}), 404)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8765")), debug=False)
