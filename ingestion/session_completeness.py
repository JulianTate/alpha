"""Explicit market-session completeness checks.

The module never invents a trading calendar. Callers must provide the expected
session timestamps from a declared calendar or licensed source.
"""
from __future__ import annotations

from typing import Iterable


def assess_session_completeness(*, observed: Iterable[str], expected: Iterable[str],
                                allow_duplicates: bool = False) -> dict:
    observed_values = [str(value) for value in observed]
    expected_values = [str(value) for value in expected]
    observed_set, expected_set = set(observed_values), set(expected_values)
    duplicate_observations = sorted({value for value in observed_values if observed_values.count(value) > 1})
    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)
    duplicate_blocked = bool(duplicate_observations and not allow_duplicates)
    status = "READY" if not missing and not unexpected and not duplicate_blocked else "SESSION_INCOMPLETE"
    return {
        "schema_version": 1,
        "status": status,
        "observed_count": len(observed_values),
        "expected_count": len(expected_values),
        "missing_sessions": missing,
        "unexpected_sessions": unexpected,
        "duplicate_sessions": duplicate_observations,
        "calendar_declared": bool(expected_values),
        "guardrails": [
            "Expected sessions must be supplied by an explicit calendar policy",
            "No market-calendar inference",
            "No interpolation or synthetic observations",
        ],
    }
