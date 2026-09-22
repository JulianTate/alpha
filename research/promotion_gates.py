"""Explicit, conservative validation and promotion gates.

A gate reports eligibility only from declared evidence. It never authorizes live
execution and it rejects missing or insufficient evidence rather than guessing.
"""
from __future__ import annotations

from typing import Any


DEFAULT_RULES = {
    "minimum_oos_observations": 30,
    "minimum_oos_brier_score": 0.25,
    "minimum_oos_accuracy": 0.50,
    "require_calibration": True,
    "require_frozen_dataset": True,
}


def evaluate_promotion_gate(*, dataset_status: str, scorecard: dict[str, Any] | None,
                            evidence_status: str = "COMPLETE", rules: dict[str, Any] | None = None) -> dict[str, Any]:
    active = {**DEFAULT_RULES, **(rules or {})}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if active.get("require_frozen_dataset", True):
        check("dataset_frozen", dataset_status == "FROZEN", f"dataset status is {dataset_status}")
    else:
        check("dataset_frozen", True, "frozen dataset requirement disabled by declared rules")
    check("evidence_complete", evidence_status == "COMPLETE", f"evidence status is {evidence_status}")
    if not scorecard:
        check("scorecard_present", False, "no out-of-sample scorecard supplied")
    else:
        count = int(scorecard.get("sample_count", 0))
        accuracy = float(scorecard.get("accuracy", 0.0))
        brier = float(scorecard.get("brier_score", 1.0))
        calibration = scorecard.get("calibration")
        check("scorecard_complete", scorecard.get("status", "COMPLETE") == "COMPLETE", f"scorecard status is {scorecard.get('status', 'COMPLETE')}")
        scope = str(scorecard.get("evaluation_scope", "OOS")).upper()
        check("locked_oos_scope", "OOS" in scope, f"evaluation scope is {scope}")
        check("oos_sample_size", count >= int(active["minimum_oos_observations"]), f"{count} observations; minimum {active['minimum_oos_observations']}")
        check("oos_accuracy", accuracy >= float(active["minimum_oos_accuracy"]), f"accuracy {accuracy:.4f}; minimum {active['minimum_oos_accuracy']}")
        check("oos_brier_score", brier <= float(active["minimum_oos_brier_score"]), f"Brier score {brier:.4f}; maximum {active['minimum_oos_brier_score']}")
        check("calibration_present", bool(calibration) if active["require_calibration"] else True, "calibration diagnostics supplied" if calibration else "calibration diagnostics missing")
    passed = all(item["passed"] for item in checks)
    return {
        "decision": "ELIGIBLE_FOR_HUMAN_REVIEW" if passed else "REJECTED_OR_INSUFFICIENT_EVIDENCE",
        "eligible": passed,
        "live_execution": False,
        "manual_review_required": True,
        "checks": checks,
        "rules": active,
        "limitations": ["This is a research eligibility gate, not a profitability claim or trade authorization.", "Human review and manual execution remain mandatory."],
    }
