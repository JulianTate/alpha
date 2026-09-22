# Ingestion status

Implemented and safe to test:

- SEC company ticker map, submissions, recent filing events, and companyfacts endpoint boundary.
- FRED observations with explicit API-key gating and realtime/vintage parameters.
- Immutable content-addressed raw snapshots.
- Point-in-time ordering checks for event, publication, availability, and reaction timestamps.

Not activated yet:

- Market prices: provider selection and licensing decision required.
- News: legitimate provider selection required.
- SEC Form 4/13D/13G/13F semantic parsers beyond preserving filing metadata.
- Automatic polling and retry/backoff policy in the worker.

A live SEC smoke test is permitted because `data.sec.gov` requires no API key, but all fetched data must be treated as external input and stored only as provenance-bearing snapshots/events.
