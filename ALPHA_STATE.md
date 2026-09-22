# Alpha State
<!-- project: path:C:\Users\julia\.openclaw\workspace -->

**Updated:** 2026-09-21
**Repository:** `C:\Jarvis\Alpha`
**Branch/version:** `master` at `24f3d53` plus uncommitted working changes preserved

## Current phase

**Phase 24 - Provenance Completeness Summary**

## Current phase status

**Phase 24 is complete for the implemented bounded scope:** Provenance-aware research-memory search can optionally attach deterministic status counts and an overall `RESOLVED`/`INCOMPLETE` summary. Manual review, non-authoritative outputs, and no live execution remain mandatory.

## Completed increments

- Located the canonical Alpha repository at `C:\Jarvis\Alpha`.
- Audited architecture, providers, database, research engine, paper workflow, dashboard, and tests.
- Added durable recovery/state documentation.
- Added `research/evidence_library.py`: deterministic, versioned evidence records for momentum, value, quality, trend, reversal, size, investment, and low-volatility families.
- Registered the library during `alpha.py init` and exposed `python alpha.py evidence-library`.
- Added tests for stable hashes, idempotent registration, and changed-definition rejection.
- Added `research/predictions.py`: deterministic prediction objects with dataset, experiment, as-of, horizon, model, feature-snapshot, score, and status lineage.
- Added immutable `ModelVersion` lineage records covering model family, code version, feature definition, training dataset, parameters, parent version, and status; prediction rows retain the model definition hash.
- Added read-only `model-version-list` CLI visibility and regression coverage for deterministic registration and changed-definition rejection.
- Extended `research/scorecards.py` with declared out-of-sample scope, as-of bounds, model-version filters, minimum sample requirements, explicit status, expected calibration error, and maximum calibration-bin error.
- Added immutable scorecard retrieval/listing and CLI commands: `build-scorecard`, `scorecard`, and `scorecard-list`.
- Extended `research/baseline_scorecards.py` with a deterministic baseline suite covering RANDOM, BUY_AND_HOLD, FACTOR, and TECHNICAL series.
- Required explicit non-negative transaction-cost input and a reproducible random seed; costs are deducted from every accepted series observation.
- Added explicit per-baseline and suite-level `COMPLETE`/`INSUFFICIENT_DATA` states without fabrication or silent repair of missing series.
- Added read-only `baseline-suite` CLI support from a JSON observation file.
- Integrated prediction-table creation into `alpha.py init`.
- Added focused tests for idempotence, ticker normalization, retrieval, and no silent overwrite.
- Added `research/scorecards.py`: persisted observed outcomes, deterministic scorecards, accuracy, Brier score, and five-bin calibration diagnostics.
- Integrated scorecard-table creation into `alpha.py init`.
- Added focused tests for deterministic scorecard persistence and immutable outcome labels.
- Added `ingestion/dataset_contract.py`: immutable dataset reconstruction/provenance contracts covering universe, as-of policy, corporate actions, survivorship, source snapshot, and quality status.
- Integrated dataset-contract table creation into `alpha.py init` and contract registration into `data-freeze`.
- Added `research/walk_forward.py`: expanding-train, sequential validation/test fold construction with look-ahead and overlap rejection.
- Added focused dataset-contract and walk-forward tests.
- Added `research/promotion_gates.py`: conservative evidence gate requiring frozen data, complete evidence, sufficient out-of-sample observations, accuracy/Brier thresholds, and calibration diagnostics; output is human-review eligibility only.
- Integrated an explicit walk-forward contract into baseline campaign definitions and persisted campaign results.
- Added `research/baseline_scorecards.py`: deterministic buy-and-hold/comparative scorecards with costs-included status, cumulative return, win rate, and drawdown diagnostics.
- Added focused tests proving deterministic comparative-only behavior and hard failure on missing returns.
- Added `research/risk_controls.py`: explicit unresolved regime states and deterministic position/sector concentration checks with manual-review requirements.
- Added focused tests for regime classification and concentration blocking.
- Added `research/shadow_validation.py`: deterministic champion/challenger comparison on identical observed samples, explicitly manual-review-only.
- Added `research/research_manager.py`: immutable job definitions with explicit state, attempt, checkpoint, retry, and resume semantics.
- Added immutable `strategy_genomes` registry records with deterministic definition hashes and optional parent lineage.
- Added required strategy genome contracts for family, parameters, feature definition, signal definition, and cost model.
- Added read-only `strategy-genome-list` CLI visibility and focused deterministic/idempotence/lineage tests.
- Added conservative frozen-evidence validation and promotion gates in `research/promotion_gates.py`.
- Added `research/paper_review.py` with immutable operator review records and explicit paper-observation gates.
- Added read-only `paper-review` and `paper-observation-gate` CLI commands.
- Required an `APPROVE_PAPER` operator decision plus the declared minimum observation count; preserved blocked states and manual-execution-only semantics.
- Added `research/outcome_reconciliation.py` to reconcile linked predictions and explicitly report missing observations without inference.
- Exposed `outcome-reconcile` and `shadow-compare` as read-only CLI commands.
- Preserved descriptive-only champion/challenger comparison, manual review, and `live_execution: False`.
- Required complete scorecards in an OOS scope, frozen datasets, complete evidence, minimum observations, accuracy, Brier score, and calibration diagnostics.
- Added read-only `promotion-gate` CLI evaluation from JSON evidence.
- Preserved explicit rejection/insufficient-evidence states, mandatory human review, and no live execution.
- Added `research/holding_periods.py` for explicit multi-horizon comparisons after costs and liquidity participation limits.
- Added `holding-period-compare` CLI support from JSON observations.
- Preserved missing, malformed, and liquidity-blocked observations as explicit exclusions with per-horizon statuses.
- Added focused holding-period, cost, liquidity, and insufficient-data tests.
- Extended research-manager recovery with append-only `research_manager_checkpoints` records containing sequence, state, completed steps, and checkpoint hash.
- Added bounded `execute_job` orchestration that runs only unfinished declared steps, checkpoints after each successful step, and persists failures as resumable `FAILED` jobs.
- Integrated research-manager table creation into `alpha.py init`.
- Added focused tests for shadow validation and job recovery.
- Added `research/anti_overfitting.py`: descriptive selection-pressure, validation/OOS-gap, rank, and dispersion diagnostics; formal DSR/PBO/CSCV status remains explicitly unimplemented.
- Added focused tests for anti-overfitting diagnostics and empty-trial blocking.
- Added `research/paper_outcomes.py`: explicit manual-paper candidate links and observed prediction outcomes feeding scorecards without inference or automation.
- Integrated paper-outcome table creation into `alpha.py init`.
- Added focused tests for paper linkage, outcome persistence, and missing-candidate rejection.
- Added `research/manager_report.py` and `python alpha.py research-manager-report` for read-only operator recovery visibility.
- Verified the new CLI report against the existing SQLite database; no jobs were pending and no execution was performed.
- Added `research/validation_summary.py`: deterministic, immutable campaign-level composition of walk-forward, baseline, anti-overfitting, and promotion-gate diagnostics.
- Integrated validation-summary table creation into `alpha.py init`.
- Added focused tests for deterministic persistence, idempotence, and changed-definition rejection.
- Verified `python alpha.py init`, `python alpha.py evidence-library`, and existing SQLite migration/initialization successfully.
- Added `ingestion/coverage.py`: deterministic symbol coverage, partial/missing, stale, future-observation, and malformed-row diagnostics with explicit no-repair guardrails.
- Integrated coverage diagnostics into `data_manager.plan_update`; incomplete symbols now remain explicit `MISSING`/`PARTIAL`/other blocked statuses with per-symbol diagnostics.
- Integrated coverage checks into `alpha.py data-freeze`; incomplete requested-range coverage is blocked before a dataset can be frozen.
- Added `ingestion/capability_gates.py`: explicit provider capability declarations are required before freeze; declarations are not treated as proof of point-in-time sufficiency.
- Integrated Tiingo capability gating into `alpha.py data-freeze`.
- Persisted both coverage and provider-capability reports in the immutable dataset reconstruction contract.
- Added `ingestion/provenance.py`: immutable provider retrieval evidence and point-in-time universe membership evidence.
- Integrated retrieval evidence recording into successful, invalid, and blocked `data_update` observations and membership evidence into dataset freeze.
- Added immutable data-update run summaries, including blocked/empty provider responses and result status.
- Dataset freeze now compares the active expected universe with observed symbols and blocks missing active symbols explicitly.
- Added a regression test proving missing active-universe symbols cannot be silently omitted from a frozen dataset.
- Added `ingestion/session_completeness.py`: explicit expected-versus-observed session diagnostics requiring a declared calendar; missing, unexpected, and duplicate sessions remain blockers.
- Added immutable dataset-level retrieval-completeness reports with per-symbol `COVERED`, `INCOMPLETE`, `NO_EVIDENCE`, and `CONFLICT` states.
- Added read-only `retrieval-completeness` and `retrieval-completeness-list` CLI commands.
- Added immutable update-run reconciliation reports, `reconcile-update-run`, `reconciliation-report`, and `reconciliation-report-list` CLI commands.
- Integrated reconciliation-report creation into every completed `data_update` run summary, including blocked, empty, invalid, and ready outcomes.
- Integrated optional declared session calendars into `alpha.data_freeze(expected_sessions=...)`; absent calendars remain explicitly unassumed.
- Added a regression test proving a declared session gap blocks freeze.
- Added focused coverage/freshness tests; no market calendar, interpolation, or provider substitution is inferred.
- Added focused tests proving insufficient evidence is rejected and no gate authorizes live execution.

## Tests status

- `python -m unittest tests.test_evidence_library`: **2 passed** on 2026-09-21.
- `python -m unittest tests.test_predictions`: **2 passed** on 2026-09-21.
- `python -m unittest tests.test_scorecards`: **2 passed** on 2026-09-21.
- `python -m unittest tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards tests.test_walk_forward`: **15 passed** on 2026-09-21.
- `python -m unittest tests.test_promotion_gates tests.test_walk_forward tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards tests.test_campaign`: **18 passed** on 2026-09-21.
- Campaign verification was rerun after walk-forward integration: **18 passed** on 2026-09-21.
- `python -m unittest tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **20 passed** on 2026-09-21.
- `python -m unittest tests.test_risk_controls tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **22 passed** on 2026-09-21.
- `python -m unittest tests.test_research_manager tests.test_shadow_validation tests.test_risk_controls tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **26 passed** on 2026-09-21.
- `python -m unittest tests.test_anti_overfitting tests.test_research_manager tests.test_shadow_validation tests.test_risk_controls tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **28 passed** on 2026-09-21.
- `python -m unittest tests.test_paper_outcomes tests.test_anti_overfitting tests.test_research_manager tests.test_shadow_validation tests.test_risk_controls tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **30 passed** on 2026-09-21.
- `python -m unittest tests.test_manager_report tests.test_paper_outcomes tests.test_anti_overfitting tests.test_research_manager tests.test_shadow_validation tests.test_risk_controls tests.test_baseline_scorecards tests.test_campaign tests.test_walk_forward tests.test_promotion_gates tests.test_dataset_contract tests.test_data_engine tests.test_data_manager tests.test_registry tests.test_predictions tests.test_scorecards`: **31 passed** on 2026-09-21.
- Full cumulative verification: `python -m unittest discover -s tests` — **71 passed** on 2026-09-21.
- Compilation: `python -m compileall -q .` — **passed** on 2026-09-21.
- Full cumulative verification completed: `python -m unittest discover -s tests` — **70 passed** on 2026-09-21.
- Full cumulative verification after validation-summary work: `python -m unittest discover -s tests` — **72 passed** on 2026-09-21.
- Full cumulative verification after coverage diagnostics: `python -m unittest discover -s tests` — **74 passed** on 2026-09-21.
- Full cumulative verification after planning/freeze integration: `python -m unittest discover -s tests` — **74 passed** on 2026-09-21.
- Full cumulative verification after provider-capability gates: `python -m unittest discover -s tests` — **76 passed** on 2026-09-21.
- Full cumulative verification after provenance-evidence persistence: `python -m unittest discover -s tests` — **76 passed** on 2026-09-21.
- Full cumulative verification after retrieval/universe provenance: `python -m unittest discover -s tests` — **78 passed** on 2026-09-21.
- Full cumulative verification after blocked-update summaries: `python -m unittest discover -s tests` — **79 passed** on 2026-09-21.
- Full cumulative verification after expected-versus-observed universe checks: `python -m unittest discover -s tests` — **80 passed** on 2026-09-21.
- Full cumulative verification after declared-session completeness safeguards: `python -m unittest discover -s tests` — **82 passed** on 2026-09-21.
- Full cumulative verification after retrieval-completeness reports, conflict detection, and CLI listing: `python -m unittest discover -s tests` — **87 passed** on 2026-09-21.
- Full cumulative verification after reconciliation CLI and automatic data-update report integration: `python -m unittest discover -s tests` — **92 passed** on 2026-09-21.
- Full cumulative verification after Phase 3 model/version lineage: `python -m unittest discover -s tests` — **94 passed** on 2026-09-21.
- Full cumulative verification after Phase 4 scorecard/calibration diagnostics: `python -m unittest discover -s tests` — **96 passed** on 2026-09-21.
- Focused Phase 5 verification: `python -m unittest tests.test_baseline_scorecards tests.test_campaign` — **5 passed** on 2026-09-21.
- Full cumulative verification after Phase 5 baseline suite: `python -m unittest discover -s tests` — **98 passed** on 2026-09-21.
- `python -m compileall -q .` — **passed** on 2026-09-21.
- CLI smoke input with one row returned explicit `INSUFFICIENT_DATA` states for all baseline series.
- Full cumulative verification after optional session-calendar freeze validation: `python -m unittest discover -s tests` — **83 passed** on 2026-09-21.
- Compilation completed: `python -m compileall -q .` — **passed** on 2026-09-21.
- No profitability claim has been established.
- No profitability claim has been established.

## Known issues

- Historical price availability remains provider- and coverage-dependent; missing data must remain a hard blocker.
- Point-in-time fundamentals, delistings/survivorship controls, corporate actions, and licensed market-data semantics need further hardening.
- Research laboratory metrics are bounded diagnostics; multiple-testing controls are not yet DSR/PBO/CSCV evidence.
- Dashboard is a local reporting surface, not yet the full research cockpit described by the roadmap.
- Telegram/phone delivery and unattended Windows startup are not proven or enabled.
- Existing uncommitted changes and local runtime artifacts must not be discarded.

## Blocked items

- No automatic broker execution is permitted.
- No strategy may be promoted from backtest alone.
- No live opportunity qualification until data, validation, and paper gates are satisfied.

## Current research queue

1. Add explicit retrieval-report linkage to data-update run summaries and frozen dataset IDs.
2. Add formal multiple-testing/anti-overfitting methods only after validated requirements and test fixtures exist.
3. Add semantic retrieval, provider-backed evidence acquisition, memory lifecycle/version migration, statistical inference, and formal multiple-testing controls after the bounded provenance-completeness increment.
4. Harden 24/7 manager observability and operator-facing recovery reports.

## Next exact action

Begin Phase 25 only after operator review of the Phase 24 evidence. Preserve deterministic memory, provenance completeness, manual review, and no-execution boundaries.

## Files/components changed in this increment

- `CURRENT_SYSTEM.md`
- `ALPHA_STATE.md`
- `ALPHA_DECISIONS.md`
- `ALPHA_RESEARCH_LOG.md`
- `ALPHA_PHASE_LOG.md`
- `ALPHA_NEXT_ACTIONS.md`
- `ALPHA_MASTER_ROADMAP.md`
- `research/evidence_library.py`
- `tests/test_evidence_library.py`
- `alpha.py`
