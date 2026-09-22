# Jarvis Alpha query surface

The read-only helper is `integrations\jarvis_alpha.py`.

Supported query intents in the first slice:
- strongest/today's signals or what's interesting -> top signals by score
- open trades -> open manual positions
- other questions -> operational report

Manual trade entry is explicit and offline:
`python alpha.py buy ALP-XXXXXXXX TICKER QUANTITY PRICE`

Manual exit:
`python alpha.py sell ALP-XXXXXXXX PRICE`

No query can place an order.

## Strategy scanner

Scan one or more tickers from historical OHLCV data already stored in Alpha:

```powershell
python alpha.py scan NVDA MSFT SPY
python alpha.py data-status
python alpha.py data-verify
python alpha.py scan-universe --limit 10
python alpha.py scan-universe NVDA MSFT AMD TSM --horizon 10 --limit 5
python alpha.py scan NVDA --horizon 10
```

The scanner compares four explainable research strategies: SMA trend, RSI mean reversion, MACD momentum, and Donchian breakout. `scan-universe` scans all active companies with sufficient stored history, ranks research candidates before weaker setups, and returns the best available candidates. Directional setups include a current entry reference, ATR-based stop, ATR-based target, and risk/reward estimate. A hit rate is historical descriptive evidence, not a probability guarantee. With fewer than 20 comparable observations, the result is marked `INSUFFICIENT_EVIDENCE`; with no stored prices it returns `NO_DATA`.

The M1 data checks are explicit: `data-status` reports `DATA_BLOCKED` when no canonical observations are available, and `data-verify` reports `VALID`, `INVALID`, or `UNRESOLVED`. Bad OHLCV rows are rejected; Alpha does not interpolate or silently repair them.

The scanner is read-only. It does not place orders, connect to Trading 212, or treat TradingView as an execution source.
