"""Descriptive multiple-testing and anti-overfitting diagnostics.

These diagnostics expose selection pressure and instability. They are not a
claim to have implemented formal DSR, PBO, or CSCV inference.
"""
from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Any, Iterable

from .registry import canonical_hash


def selection_diagnostics(trials: Iterable[dict[str, Any]], *, selected_trial_id: str | None = None) -> dict[str, Any]:
    rows = [dict(row) for row in trials]
    if not rows:
        raise ValueError("anti-overfitting diagnostics require at least one trial")
    values = [float(row.get("oos_return", row.get("mean_return", 0.0))) for row in rows]
    validation = [float(row.get("validation_return", row.get("mean_return", 0.0))) for row in rows]
    best_index = max(range(len(rows)), key=lambda index: values[index])
    selected = rows[best_index] if selected_trial_id is None else next((row for row in rows if str(row.get("trial_id")) == str(selected_trial_id)), None)
    if selected is None:
        raise ValueError("selected_trial_id not found")
    selected_oos = float(selected.get("oos_return", selected.get("mean_return", 0.0)))
    selected_validation = float(selected.get("validation_return", selected.get("mean_return", 0.0)))
    rank = 1 + sum(value > selected_oos for value in values)
    return {
        "diagnostic_hash": canonical_hash({"trials": rows, "selected": selected.get("trial_id", best_index)}),
        "trial_count": len(rows),
        "positive_oos_trials": sum(value > 0 for value in values),
        "best_oos_return": max(values),
        "median_oos_return": median(values),
        "oos_dispersion": pstdev(values) if len(values) > 1 else 0.0,
        "selected_trial_id": selected.get("trial_id", best_index),
        "selected_oos_return": selected_oos,
        "selected_validation_return": selected_validation,
        "selected_rank": rank,
        "selection_rate": 1.0 / len(rows),
        "validation_oos_gap": selected_validation - selected_oos,
        "selection_bias_warning": len(rows) > 1,
        "formal_inference_status": "NOT_IMPLEMENTED",
        "method": "descriptive trial-distribution and validation/OOS comparison; no DSR/PBO/CSCV claim",
        "limitations": ["Selection diagnostics do not correct multiple testing.", "A single selected trial does not establish generalisation.", "Locked holdout and independent replication remain required."],
    }
