# Validation

Run `python scripts\demo_e2e.py` for the deterministic offline chain. Run unit tests with `python -m unittest discover -s tests` (pytest is not installed). The demo proves plumbing, not alpha.

The validation primitives in `research\validation.py` require timezone-aware decision and availability timestamps, reject look-ahead observations, create chronological train/validation/test splits, and report expectancy, win rate, volatility, drawdown, losing streak, turnover, capital utilisation, and a clearly-labelled empirical risk-of-ruin proxy. `research\reporting.py` keeps split, strategy, and horizon metrics separate; use the test split for out-of-sample reporting rather than pooling all rows.

A production validation program still needs sustained timestamped historical source snapshots, adjusted prices and corporate-action treatment, event-window policy, universe controls, benchmarks, multiple walk-forward folds, realistic order/latency modelling, and independent review. These modules do not claim alpha or profitability.
