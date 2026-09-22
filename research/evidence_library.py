"""Versioned quantitative strategy and evidence metadata registry.

The library records research hypotheses and implementation requirements. It is
not a claim that any family remains profitable; empirical validation belongs to
Alpha's frozen-data campaigns and locked out-of-sample evaluation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    family_id: str
    name: str
    version: str
    category: str
    source_references: tuple[str, ...]
    original_definition: str
    data_requirements: tuple[str, ...]
    expected_horizons: tuple[int, ...]
    limitations: tuple[str, ...]
    cost_considerations: tuple[str, ...]
    failure_modes: tuple[str, ...]
    implementation_status: str = "EVIDENCE_LIBRARY"

    def definition(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("source_references", "data_requirements", "expected_horizons", "limitations", "cost_considerations", "failure_modes"):
            value[key] = list(value[key])
        return value

    @property
    def definition_hash(self) -> str:
        return _hash(self.definition())

    @property
    def record_id(self) -> str:
        return f"EVID-{self.family_id}-{self.version}"

    def as_dict(self) -> dict[str, Any]:
        return self.definition() | {"record_id": self.record_id, "definition_hash": self.definition_hash}


BUILTIN_EVIDENCE = (
    EvidenceRecord("MOMENTUM", "Momentum", "momentum-v1", "equity_factor", ("Jegadeesh and Titman (1993)", "Fama-French momentum literature"), "Rank securities by prior intermediate returns, with a predeclared formation and holding period.", ("point-in-time prices", "corporate-action policy", "historical universe", "liquidity"), (5, 21, 63, 126, 252), ("Can suffer crashes and crowding", "formation/skip conventions matter", "published results are not a guarantee"), ("turnover", "spread and slippage", "capacity", "shorting costs if used"), ("look-ahead through adjusted data", "survivorship bias", "overfitted lookbacks", "reversal after crowded trends")),
    EvidenceRecord("VALUE", "Value", "value-v1", "equity_factor", ("Fama and French (1992, 1993)", "Fama-French factor research"), "Rank securities using a predeclared valuation measure such as book-to-market or earnings yield.", ("point-in-time fundamentals", "filing availability", "identifier history", "prices"), (21, 63, 126, 252), ("Value definitions vary by sector", "cheap securities may be distressed", "fundamental revisions must not leak"), ("rebalance turnover", "fundamental data licensing", "liquidity", "tax and transaction costs"), ("look-ahead fundamentals", "value traps", "sector concentration", "delistings omitted")),
    EvidenceRecord("QUALITY", "Quality / Profitability", "quality-v1", "equity_factor", ("Novy-Marx (2013)", "Fama-French profitability research"), "Rank securities using predeclared profitability, stability, or balance-sheet quality measures available at the decision time.", ("point-in-time financial statements", "restatement/version policy", "market data", "sector context"), (21, 63, 126, 252), ("Accounting definitions are not interchangeable", "quality can be regime-dependent", "data availability lags filings"), ("fundamental data cost", "rebalance turnover", "liquidity"), ("restated data leakage", "sector bias", "accounting manipulation", "stale filings")),
    EvidenceRecord("TREND", "Time-Series Trend", "trend-v1", "trend", ("Moskowitz, Ooi and Pedersen (2012)", "trend-following literature"), "Take exposure when an instrument's own prior return or trend filter satisfies a fixed rule.", ("continuous price history", "corporate-action policy", "execution timing", "benchmark"), (1, 5, 21, 63, 126, 252), ("Whipsaws in sideways regimes", "daily bars do not model intraday execution", "signal timing is material"), ("turnover", "gap slippage", "spread", "volatility scaling"), ("same-bar execution", "look-ahead", "parameter tuning", "regime overfitting")),
    EvidenceRecord("REVERSAL", "Short-Term Reversal", "reversal-v1", "equity_factor", ("Jegadeesh (1990)", "short-term reversal literature"), "Buy relative recent losers or sell relative recent winners under a predeclared short horizon and liquidity rule.", ("prices", "volume/liquidity", "corporate actions", "shorting constraints"), (1, 2, 3, 5, 10), ("Often cost-sensitive", "may capture bid-ask bounce", "can fail during information events"), ("spread", "commission", "market impact", "borrow availability"), ("microstructure artefacts", "event contamination", "same-day leakage", "unrealistic fills")),
    EvidenceRecord("SIZE", "Size", "size-v1", "equity_factor", ("Banz (1981)", "Fama-French size research"), "Measure size using point-in-time market capitalisation and test a predeclared small-versus-large exposure.", ("point-in-time prices", "shares outstanding", "universe membership", "liquidity"), (21, 63, 126, 252), ("Effect can vary across markets and periods", "small names have higher implementation friction"), ("spread", "market impact", "capacity", "turnover"), ("survivorship", "stale shares outstanding", "microcap liquidity", "universe drift")),
    EvidenceRecord("INVESTMENT", "Investment", "investment-v1", "equity_factor", ("Fama and French (2015, 2016)", "investment factor research"), "Rank firms using a predeclared measure of asset or investment growth available after reporting lag.", ("point-in-time financial statements", "filing dates", "identifier history", "prices"), (63, 126, 252), ("Definitions and accounting treatment vary", "annual data can be stale", "not a standalone trade signal"), ("rebalance costs", "fundamental data cost", "liquidity"), ("restatement leakage", "sector effects", "accounting comparability", "annual look-ahead")),
    EvidenceRecord("LOW_VOLATILITY", "Low Volatility / Defensive", "low-volatility-v1", "equity_factor", ("Ang et al. (2006)", "low-volatility factor literature"), "Rank or weight securities using a predeclared historical volatility or defensive-risk measure.", ("price history", "corporate-action policy", "liquidity", "benchmark"), (21, 63, 126, 252), ("Can lag strongly in risk-on markets", "risk measure choice changes exposure", "factor overlap must be measured"), ("rebalance turnover", "spread", "capacity", "volatility estimation"), ("future volatility leakage", "concentration", "sector bias", "unstable estimates")),
)


def ensure_evidence_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS strategy_evidence_library(
        record_id TEXT PRIMARY KEY, family_id TEXT NOT NULL, name TEXT NOT NULL,
        version TEXT NOT NULL, definition_hash TEXT UNIQUE NOT NULL,
        definition_json TEXT NOT NULL, implementation_status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def register_evidence(connection: sqlite3.Connection, record: EvidenceRecord) -> dict[str, Any]:
    ensure_evidence_tables(connection)
    body = record.definition()
    existing = connection.execute("SELECT definition_hash, definition_json FROM strategy_evidence_library WHERE record_id=?", (record.record_id,)).fetchone()
    if existing and existing[0] != record.definition_hash:
        raise ValueError(f"evidence record version already exists with a different definition: {record.record_id}")
    connection.execute("""INSERT OR IGNORE INTO strategy_evidence_library
        VALUES(?,?,?,?,?,?,?,?)""", (record.record_id, record.family_id, record.name, record.version, record.definition_hash, json.dumps(body, sort_keys=True), record.implementation_status, _now()))
    return record.as_dict()


def register_builtin_evidence(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [register_evidence(connection, record) for record in BUILTIN_EVIDENCE]


def list_evidence(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_evidence_tables(connection)
    rows = connection.execute("SELECT record_id,family_id,name,version,definition_hash,implementation_status,created_at FROM strategy_evidence_library ORDER BY family_id,version").fetchall()
    columns = [item[0] for item in connection.execute("SELECT record_id,family_id,name,version,definition_hash,implementation_status,created_at FROM strategy_evidence_library LIMIT 0").description]
    return [dict(zip(columns, row)) for row in rows]
