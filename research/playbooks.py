"""Versioned investment playbooks inspired by structured investor judgment systems.

Playbooks are hypothesis specifications, not validated strategies. They make
investment reasoning explicit and provide the input contract for future
campaigns; only Alpha's research laboratory can establish historical evidence.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Playbook:
    playbook_id: str
    name: str
    version: str
    philosophy: str
    research_question: str
    universe_rules: tuple[str, ...]
    evidence_required: tuple[str, ...]
    entry_rules: tuple[str, ...]
    exclusions: tuple[str, ...]
    sizing_rules: tuple[str, ...]
    invalidation_rules: tuple[str, ...]
    monitoring_rules: tuple[str, ...]
    risk_warnings: tuple[str, ...]
    source_inspiration: str
    status: str = "HYPOTHESIS"

    def definition(self) -> dict[str, Any]:
        value = asdict(self)
        value["universe_rules"] = list(self.universe_rules)
        value["evidence_required"] = list(self.evidence_required)
        value["entry_rules"] = list(self.entry_rules)
        value["exclusions"] = list(self.exclusions)
        value["sizing_rules"] = list(self.sizing_rules)
        value["invalidation_rules"] = list(self.invalidation_rules)
        value["monitoring_rules"] = list(self.monitoring_rules)
        value["risk_warnings"] = list(self.risk_warnings)
        return value


PLAYBOOKS = (
    Playbook(
        "PB-QUALITY-MOMENTUM-V1", "Quality Momentum", "quality-momentum-v1",
        "Combine durable business quality with improving price and earnings momentum.",
        "Does a point-in-time quality and momentum combination outperform after costs and turnover?",
        ("liquid listed equities", "exclude unresolved identity or stale prices"),
        ("point-in-time financial statements", "price and volume", "earnings and estimate revisions", "sector and benchmark context"),
        ("quality is above the declared threshold", "momentum and relative strength confirm", "catalyst or revision is timestamped before entry"),
        ("missing or late fundamentals", "extreme spread or insufficient liquidity", "thesis contradicted by new filings"),
        ("volatility-adjusted size", "single-name and sector caps", "paper-only until promoted by a separate campaign"),
        ("quality deterioration", "earnings/revision reversal", "price action violates declared risk limit"),
        ("earnings dates", "estimate revisions", "news and filing changes", "factor and sector concentration"),
        ("quality metrics must be filed-available, not restated with hindsight", "historical hit rates are descriptive"),
        "InvestorSkills quality/value and momentum concepts",
    ),
    Playbook(
        "PB-TREND-BREAKOUT-V1", "Trend Breakout", "trend-breakout-v1",
        "Trade persistent, liquid trends only when a defined breakout is confirmed.",
        "Do rule-based breakouts persist out of sample after realistic costs, gaps, and failed-breakout losses?",
        ("liquid equities", "minimum history for indicators", "avoid unresolved corporate actions"),
        ("adjustment policy and OHLCV", "volume and liquidity", "benchmark trend", "event calendar"),
        ("close breaks a predeclared range", "trend filter agrees", "entry is next-session executable, never same-bar hindsight"),
        ("thin volume", "wide spread or price gaps", "entry after a known disqualifying event"),
        ("ATR or volatility scaled", "fixed maximum loss budget", "portfolio correlation cap"),
        ("failed breakout", "trend filter reversal", "maximum holding period or risk limit"),
        ("volume confirmation", "gap and halt review", "benchmark/regime change", "drawdown and turnover"),
        ("breakouts are vulnerable to data timing and selection bias", "do not tune on locked OOS"),
        "InvestorSkills Livermore, O'Neil and Darvas concepts",
    ),
    Playbook(
        "PB-EVENT-NEWS-V1", "Event and News Reaction", "event-news-v1",
        "Study repeatable reactions to timestamped company, macro, and industry events.",
        "Do specific, point-in-time events create a repeatable net reaction after publication timing and costs are respected?",
        ("companies with reliable entity mapping", "events with publication and availability timestamps"),
        ("official filing or licensed news metadata", "market price and volume", "event classification", "pre-event baseline"),
        ("event is available before the decision timestamp", "reaction rule is predeclared", "direction and horizon are explicit"),
        ("duplicate or unverifiable articles", "events discovered only after the price move", "ambiguous entity mapping"),
        ("small initial paper exposure", "event-type and issuer caps", "no automatic execution"),
        ("event thesis is contradicted", "reaction window expires", "source quality is downgraded"),
        ("follow-up filings", "news novelty", "volume/volatility response", "later revision of event classification"),
        ("news sentiment is not evidence by itself", "GDELT discovery metadata is not a licensed content feed"),
        "InvestorSkills catalyst thinking and Alpha event-provenance rules",
    ),
)


def ensure_playbook_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS research_playbooks(
        playbook_id TEXT PRIMARY KEY, version TEXT UNIQUE NOT NULL,
        definition_hash TEXT UNIQUE NOT NULL, definition_json TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL
    )""")


def register_playbook(connection: sqlite3.Connection, playbook: Playbook) -> dict:
    body = playbook.definition()
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    connection.execute(
        "INSERT OR IGNORE INTO research_playbooks VALUES(?,?,?,?,?,?)",
        (playbook.playbook_id, playbook.version, digest, json.dumps(body, sort_keys=True), playbook.status, _now()),
    )
    return {"playbook_id": playbook.playbook_id, "version": playbook.version, "definition_hash": digest, "status": playbook.status}


def register_builtin_playbooks(connection: sqlite3.Connection) -> list[dict]:
    ensure_playbook_tables(connection)
    return [register_playbook(connection, playbook) for playbook in PLAYBOOKS]


def list_playbooks(connection: sqlite3.Connection) -> list[dict]:
    ensure_playbook_tables(connection)
    cursor = connection.execute("SELECT playbook_id,version,definition_hash,status,created_at FROM research_playbooks ORDER BY version")
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
