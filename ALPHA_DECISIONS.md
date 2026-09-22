# Alpha Decisions
<!-- project: path:C:\Users\julia\.openclaw\workspace -->

## D-0001 — Preserve the existing vertical slice

**Date:** 2026-09-21
**Decision:** Extend the existing local Alpha implementation in place. Do not rebuild the Tiingo/provenance, SQLite, registry, laboratory, execution, paper, or test components that already exist.
**Reason:** The audit found working components and 46 passing tests. Rebuilding would increase regression and provenance risk.

## D-0002 — Keep the two investment systems logically separate

**Decision:** Tactical research/paper trading and the long-term ISA/Core layer must remain separate objectives and data views. Shared infrastructure is acceptable; tactical signals must not churn ISA holdings.

## D-0003 — Quantitative code is authoritative for numbers

**Decision:** Backtests, portfolio accounting, risk, predictions, and historical returns must be computed by deterministic code. LLM output may interpret results or propose hypotheses but may not invent or override numerical evidence.

## D-0004 — Missing evidence is a first-class outcome

**Decision:** Missing, stale, blocked, or unresolved data produces `DATA_BLOCKED`, `DATA_INCOMPLETE`, `NO_DATA`, `REJECTED`, or equivalent explicit states. Alpha must never fill gaps silently or present a candidate as validated.

## D-0005 — Manual execution remains the initial boundary

**Decision:** Alpha remains paper/manual-only. No broker credentials, automatic orders, or startup persistence are added as part of the current roadmap work.
