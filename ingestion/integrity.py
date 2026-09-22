"""Conservative data-integrity control declarations for frozen datasets.

This module does not infer provider capabilities or repair market data. It makes
unproven corporate-action, survivorship, calendar, borrow, and liquidity
assumptions explicit and blocks a dataset unless the operator has declared each
control adequate for its intended use.
"""
from __future__ import annotations

from typing import Any

CONTROL_NAMES = (
    "corporate_actions", "delistings", "survivorship", "market_calendar",
    "borrow_constraints", "liquidity_model",
)
VALID_STATUSES = {"SUPPORTED", "UNSUPPORTED", "UNVERIFIED", "BLOCKED"}


def assess_integrity_controls(controls: dict[str, str]) -> dict[str, Any]:
    """Return an explicit, deterministic control assessment.

    Every control is required. Only ``SUPPORTED`` permits a complete result;
    all other states remain visible and block use. No status is inferred.
    """
    missing = sorted(set(CONTROL_NAMES) - set(controls))
    invalid = sorted(name for name, status in controls.items()
                     if name not in CONTROL_NAMES or str(status).upper() not in VALID_STATUSES)
    normalized = {name: str(controls.get(name, "MISSING")).upper() for name in CONTROL_NAMES}
    blocked = bool(missing or invalid or any(status != "SUPPORTED" for status in normalized.values()))
    return {
        "status": "BLOCKED" if blocked else "READY",
        "controls": normalized,
        "missing_controls": missing,
        "invalid_controls": invalid,
        "manual_review_required": True,
        "live_execution": False,
    }
