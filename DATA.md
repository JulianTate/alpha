# Data

Active adapters in this milestone:

- SEC EDGAR submissions/companyfacts: official `data.sec.gov`, no API key, provenance snapshots enabled.
- FRED/ALFRED observations: official API boundary, API-key gated, realtime/vintage parameters preserved.
- Market prices: Stooq public daily CSV adapter, research-only and not treated as a licensed real-time feed; bounded retry/backoff now handles transient rate limits and server errors.
- News metadata: GDELT 2.1 DOC adapter, discovery metadata only; article content is not copied; shared HTTP retry/backoff preserves attempt metadata.
- Manual ingestion remains available.

Every adapter preserves source URL, retrieval time, publication/availability time where supplied, market timestamp where applicable, and a content-addressed raw snapshot. SEC official documentation was fetched on 2026-09-14: `data.sec.gov` JSON APIs require no authentication/API key, update in real time, and provide submissions/companyfacts/XBRL data; bulk archives are republished nightly. FRED official documentation was fetched the same date: API v1 supports realtime periods and vintage dates but requires an API key.

Operational smoke observations on 2026-09-14: SEC submissions/companyfacts succeeded for MSFT; Stooq returned a valid empty result for the tested future-dated window; GDELT returned HTTP 429 under the current network/provider pacing, so news ingestion must use backoff and remains non-authoritative until sustained access is proven. Market/news source terms and coverage must be reviewed before relying on them for production backtests.
