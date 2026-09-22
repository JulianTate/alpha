# Operations

Initialize: `python alpha.py init`. Health: `python alpha.py report`. Worker: `python services\worker.py`; it is safe in paper mode and performs no broker execution. All real-data polling is opt-in through environment variables; with them unset, the worker performs health checks only.

Optional polling variables:

- `ALPHA_SEC_TICKERS=MSFT,AAPL` — official SEC submissions/XBRL event ingestion.
- `ALPHA_MARKET_TICKERS=MSFT,SPY` — Stooq daily research prices; not real-time and not yet approved as a production/licensed feed.
- `ALPHA_NEWS_QUERIES=Microsoft|Federal Reserve` — GDELT metadata discovery; provider rate limits are retried with bounded backoff and recorded if still unsuccessful.
- `ALPHA_MARKET_LOOKBACK_DAYS=10` — daily price lookback.
- `ALPHA_POLL_SECONDS=300` — worker interval.

Example one-shot verification:

```powershell
$env:ALPHA_SEC_TICKERS='MSFT'
python -c "from services.worker import run_once; print(run_once())"
```

Do not register a Windows scheduled task until the operator approves persistence/startup changes after sustained adapter verification. No automatic startup change has been made.

## Strategy scanning

Historical prices must be ingested before the scanner can produce evidence-backed candidates. For example:

```powershell
$env:ALPHA_MARKET_TICKERS='NVDA,MSFT,SPY'
$env:ALPHA_MARKET_LOOKBACK_DAYS='3650'
python services\worker.py
python alpha.py scan NVDA MSFT SPY
```

The market adapter currently uses Stooq daily research data and is explicitly delayed/end-of-day; verify adjusted-price and corporate-action semantics before treating it as production-grade. If that source is blocked or unsuitable, export chart data from TradingView and import it as a provenance-preserved snapshot:

```powershell
python alpha.py import-tradingview NVDA C:\path\to\NVDA.csv
python alpha.py scan NVDA
```

The TradingView CSV must contain `time,open,high,low,close` and may include `Volume`. TradingView remains a manual data-export and visual-validation source; Alpha remains the canonical reproducible scanner. The scan is read-only and paper/manual-only. It reports historical hit rates and agreement, not guaranteed probabilities. No Trading 212 credentials or broker connection are required.

Optional Telegram setup uses environment variables `ALPHA_TELEGRAM_BOT_TOKEN` and `ALPHA_TELEGRAM_CHAT_ID`; never put them in Git, SQLite, Obsidian, or logs. OpenClaw currently has no phone channel configured, so phone delivery is not claimed complete.

Obsidian target for future human-readable notes: `C:\Jarvis\Memory\03_RESEARCH\Alpha`.
