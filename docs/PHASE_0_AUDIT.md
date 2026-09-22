# Alpha Phase 0 — Read-Only Technical Audit

- **Project:** `C:\Jarvis\Alpha`
- **Audit date:** 2026-09-22
- **Audit scope:** repository structure, SQLite state, core research/data modules, dashboard, worker, Telegram adapter, Jarvis integration, tests, compilation, and local dashboard endpoints
- **Change policy:** read-only audit; no source, schema, configuration, or runtime-data changes were made
- **Git baseline:** `24f3d533eb5e16967123b1c1d51b012e6ae6e246`

## Executive conclusion

Alpha is a functioning local research and paper/manual workflow prototype with real frozen historical market data, deterministic scanning/council/laboratory components, and a working localhost dashboard. It is **not** a production trading system, broker-connected system, autonomous agent, or validated profitable strategy platform.

The correct next step is to improve reliability, evidence-state presentation, and operational test coverage before adding more strategy complexity. Phase 0 is complete when this document and the recovery state below are accepted as the baseline.

## Verified baseline

### Verification commands and results

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py" -v` | **PASS — 46 tests** |
| `python -m compileall -q .` | **PASS** |
| `GET http://127.0.0.1:8765/api/overview` | **HTTP 200** |
| `GET http://127.0.0.1:8765/api/reports` | **HTTP 200** |
| Overview payload | **15 active company records; 3 reports** |
| Dashboard refresh implementation | Deterministic local scan + council persistence; no model/order call |
| Worker default mode | Health-check loop; ingestion is opt-in by environment variables |
| Broker/live-order path | **Not present** |

The overview JSON contains repeated ticker fields because stock detail payloads include ticker data; the authoritative company count is 15.

### Current SQLite state

Database: `C:\Jarvis\Alpha\database\alpha.sqlite3`

| Table/metric | Observed value |
|---|---:|
| Companies | 15 |
| Price rows | 50,708 |
| Frozen datasets | 1 |
| Data-quality records | 11 |
| Data-quality runs | 0 |
| Council runs | 31 |
| Campaigns | 4 |
| Experiments | 4 |
| Laboratory reports | 3 (dashboard-visible) |
| Research playbooks | 3 |
| Paper candidates | 0 |
| Paper observations | 0 |
| Manual trades | 1 |
| Outcomes | 1 |
| Alerts | 0 |
| Model runs | 0 |
| Strategy versions | 1 |

Frozen dataset record:

- ID: `DS-50C930AB9C1DAE12`
- Status: `FROZEN`
- Row count recorded by dataset: `47,065`
- Coverage: `2011-01-03T00:00:00+00:00` through `2026-09-18T00:00:00+00:00`
- Provider composition: Tiingo
- Dataset hash: `50c930ab9c1da...` (full hash is in the database and prior operational record; do not duplicate runtime data unnecessarily)

The database currently has more price rows than the frozen dataset row count. This is an important provenance/state distinction: the frozen dataset is an immutable research artifact, while the operational database may contain subsequent or additional stored rows. Any future campaign must declare exactly which frozen dataset it uses and must not silently use the mutable operational table as a substitute.

### Dataset/universe observations

Active company records include:

`AAPL`, `ACME`, `AMD`, `AMZN`, `GOOGL`, `JNJ`, `JPM`, `META`, `MSFT`, `NVDA`, `SUPPLY`, `TSLA`, `UNH`, `WMT`, `XOM`.

Synthetic/demo records such as `ACME` and `SUPPLY` remain present. They must remain visibly distinct from validated market-data coverage. The current system does not claim that every company record has a complete price history.

## Implemented and inspected components

### Core data and provenance

- `alpha.py` initializes the base schema and extension tables.
- `ingestion/data_engine.py` validates canonical OHLCV rows and rejects malformed data without interpolation or repair.
- `ingestion/data_manager.py` plans coverage as `COVERED`, `PARTIAL`, or `MISSING` and persists a hashed plan.
- `ingestion/tiingo.py` reads `TIINGO_API_KEY` only from the environment and redacts it from returned metadata/errors.
- `ingestion/openbb.py` is an optional normalization boundary. Its output is explicitly `UNVALIDATED` until Alpha validation, raw snapshot, provenance, point-in-time, and freeze gates are completed.
- `ingestion/tradingview.py` supports user-exported CSV import; there is no TradingView scraping path.
- SEC, FRED, Stooq, and GDELT adapters exist, but provider coverage and terms are not equivalent to a validated production dataset.

### Research and evaluation

- `research/strategy_scan.py` produces explainable research candidates and historical evidence; it is not an order engine.
- `research/council.py` performs deterministic structured review, records hashes, and persists `paper_only=1`, `live_orders=0` runs.
- `research/execution.py` implements conservative daily-bar hypothetical execution: next-session entry, costs/slippage, position/risk limits, and conservative stop/target ambiguity.
- `research/laboratory.py` and `research/lab_runner.py` support bounded campaigns, temporal splits, walk-forward reporting, robustness and multiple-testing diagnostics.
- `research/registry.py` stores campaign/experiment lineage and state transitions.
- `research/paper.py` stores paper candidates, observations, and manual state transitions, but the current database has no paper candidates or observations.
- `research/playbooks.py` registers three immutable hypothesis playbooks; playbooks are not validated strategies.

### Dashboard

- `dashboard/server.py` serves a localhost Flask dashboard on port 8765.
- `/api/overview` performs local bounded scans; recent scans use at most 600 bars.
- `/api/refresh` runs deterministic council reviews and persists them.
- `/api/stock/<ticker>` exposes a local stock detail payload.
- The dashboard declares `PAPER / MANUAL ONLY` and `ON DEMAND ONLY` cloud-model status.
- No authentication or production deployment hardening was verified. It should remain localhost-only.

### Worker, messaging, and integration wiring

- `services/worker.py` is an executable infinite loop when run directly. It performs health checks and only calls SEC/market/news ingestion when the corresponding environment variable lists are populated. No Windows service, scheduler, startup registration, or watchdog wiring was found.
- `messaging/telegram.py` is a direct optional send adapter. It reads token/chat ID from environment variables and returns `not_configured` when absent. No caller wiring from the worker/dashboard/council to Telegram was verified, and no delivery was tested.
- `integrations/jarvis_alpha.py` is an importable read-only query helper for open trades, signals, or a report. It is not registered as a verified production tool/endpoint in this repository.
- No cloud LLM call was found in the worker or dashboard path.

## Verified limitations and gaps

### High priority before expanding strategy research

1. **Mutable-vs-frozen data boundary:** operational prices (50,708 rows) and frozen dataset metadata (47,065 rows) differ. Campaign execution must enforce and report the selected dataset rows/hash.
2. **Data-quality-run history:** `data_quality_runs` is empty despite dataset/data-quality functionality. Quality checks need persisted run records before the system can claim durable quality history.
3. **Evidence-state UX:** dashboard states need explicit stale, partial, blocked, unresolved, rejected, and insufficient-evidence presentation.
4. **Dashboard/API tests:** route, response-schema, refresh persistence, empty-data, stale-data, and provider-failure tests are not yet a dedicated verified layer.
5. **Paper workflow UI:** paper candidates, observations, positions, approvals, and closed-result journal are not surfaced as a complete dashboard workflow.

### Important but later

- Corporate actions, delistings, symbol changes, survivorship bias, market calendars, and provider reconciliation need additional controls.
- DSR/PBO/CSCV anti-overfitting controls are not implemented; current reports explicitly make no such claim.
- Portfolio-level selection, capacity, liquidity, correlation, and compounded-equity validation remain incomplete.
- Alerts/notifications/recovery are not operational; `alerts` is empty and no notification caller is verified.
- Telegram credentials, Tiingo credentials, FRED credentials, and external provider terms remain environment/account dependent.
- `psutil` is not installed in the current process, so RSS/process-memory checks cannot be claimed.
- Empty directories such as `models`, `features`, `signals`, `evaluation`, and `backtest` are not evidence that those capabilities are implemented.

## Security and safety conclusion

No broker integration, live order submission, autonomous execution, or Trading 212 path was found. The paper/manual-only boundary is represented in the council and dashboard code. Credentials are intended to remain environment-based.

Before any non-local deployment, add authentication and binding review. Do not register a Windows scheduled task or external notification path without a separate explicit approval and a testable audit trail.

## Phase 1 entry gate

Phase 1 may begin only with this baseline preserved and with the following scope:

- Keep all changes local and reversible.
- Do not add broker/live-order/autonomous execution functionality.
- First address the mutable-vs-frozen data boundary and persisted data-quality-run evidence, or explicitly narrow Phase 1 to dashboard evidence-state work with tests.
- Add tests before claiming the affected behavior is complete.
- Re-run the 46-test baseline plus new tests and compileall.
- Keep runtime DB, raw snapshots, reports, logs, and caches uncommitted.
