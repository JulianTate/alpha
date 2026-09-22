# Alpha Master Roadmap
<!-- project: path:C:\Users\julia\.openclaw\workspace -->

This file is the durable implementation index for the supplied Alpha roadmap. The governing objective is to build a continuously improving quantitative research and paper/manual investment system, not a toy backtester or unvalidated stock picker.

## Operating principles

- Deterministic quantitative code is authoritative for data, predictions, backtests, portfolio accounting, and risk.
- Research must use point-in-time information, realistic costs, unseen validation, reproducible configurations, and explicit failure states.
- Alpha may say no edge found; it must not force trades or invent missing observations.
- Strategies move through research, robustness, walk-forward, out-of-sample, cost stress, paper observation, and only then live eligibility.
- Tactical trading and long-term ISA/Core research are separate systems.
- Human review and manual execution remain the initial live boundary; no broker automation is part of this build.
- LLMs interpret literature/results and generate testable hypotheses but do not calculate or authorize numerical outcomes.

## Sequential phases

0. Audit and preserve the existing system.
1. Build a versioned Strategy & Evidence Library.
2. Harden point-in-time data, provenance, universe, corporate-action, and survivorship controls.
3. Standardize prediction objects and model/version lineage.
4. Persist out-of-sample prediction scorecards and calibration diagnostics.
5. Establish trustworthy random/benchmark/factor/technical baselines.
6. Run bounded autonomous research campaigns with recovery and immutable records.
7. Add controlled strategy genome and lineage.
8. Compare holding periods after costs and liquidity constraints.
9. Enforce automated validation and promotion gates.
10. Add tested regime-conditioned analysis.
11. Combine validated strategies with portfolio and concentration controls.
12. Produce human-reviewable live opportunities from eligible strategies only.
13. Add a hard-separated Alpha Core / ISA intelligence layer.
14. Record real/paper outcomes and compare predictions with outcomes.
15. Maintain champion/challenger shadow validation.
16. Add a deterministic 24/7 research manager with safe retry/resume.
17. Add selective, cached, budgeted LLM research interpretation.
18. Maintain searchable long-term research memory.
19. Integrate multiple-testing and anti-overfitting controls throughout.
20. Add a separate intraday pipeline only after daily foundations are mature.
21. Produce continuous self-evaluation reports.

## Recovery rule

At every increment, read `ALPHA_STATE.md`, inspect the repository and tests, implement one bounded change, verify it, and update the state/log files. Never claim a phase is complete without implementation and verification evidence.

## Current pointer

Phases 0 through 24 are complete for their implemented scopes, including immutable paper-review records, explicit observation gates, outcome reconciliation, strengthened paired champion/challenger shadow validation, bounded data-integrity controls, the hard-separated Core/ISA intelligence layer, explicit Core/ISA outcome observations with declared windows and provenance, deterministic research-manager recovery, bounded cached LLM interpretation requests, immutable searchable research-memory records, typed memory-to-provenance links, descriptive validation of supported local provenance references, descriptive cross-dataset provenance views, structured deterministic memory retrieval filters, opt-in provenance-aware retrieval results, and deterministic provenance completeness summaries. Formal multiple-testing correction, semantic retrieval, provider-backed evidence acquisition, distributed scheduling, and automated promotion remain future work; no automatic execution is enabled. The original roadmap’s final numbered capability is Phase 21, continuous self-evaluation reports; Phases 22 onward are bounded implementation increments rather than additional original roadmap capabilities. See `ALPHA_CHECKPOINT.md`, `ALPHA_STATE.md`, and `ALPHA_NEXT_ACTIONS.md` for verification evidence.
