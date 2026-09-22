# Architecture

CLI and future API -> Alpha service/data layer -> SQLite operational store -> deterministic research/event/paper pipelines -> optional messaging adapter -> Jarvis read-only query integration -> Obsidian research notes.

M1 data foundation: `ingestion.data_engine` provides provider capability records, canonical OHLCV validation, deterministic dataset fingerprints, provider-health/dataset tables, and explicit `VALID`/`INVALID`/`UNRESOLVED` outcomes. It never interpolates or silently repairs observations. The autonomous provider manager, incremental updates, and fallback orchestration remain later milestones.

Timestamps are stored as ISO-8601 values supplied by the source; future point-in-time correctness requires source publication timestamps and decision-time filtering. The schema has separate source documents, events, prices, signals, trades, outcomes, model runs, strategy versions, and data-quality records.

No cloud LLM is called by the worker. A future Luna adapter must be a red-team stage, JSON validated, cached, budgeted, version logged, and unable to bypass risk rules.
