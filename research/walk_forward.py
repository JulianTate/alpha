"""Deterministic walk-forward fold construction for locked evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .validation import Observation, assert_no_overlap, parse_time


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    train: tuple[Observation, ...]
    validation: tuple[Observation, ...]
    test: tuple[Observation, ...]

    def as_dict(self) -> dict:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "counts": {"train": len(self.train), "validation": len(self.validation), "test": len(self.test)},
        }


def declared_fold_contract(periods: dict[str, tuple[str, str]]) -> dict:
    """Return explicit split boundaries when a campaign has one declared fold."""
    required = {"train", "validation", "test"}
    if set(periods) != required:
        raise ValueError(f"periods must contain exactly {sorted(required)}")
    train_start, train_end = periods["train"]
    validation_start, validation_end = periods["validation"]
    test_start, test_end = periods["test"]
    if not (train_end <= validation_start and validation_end <= test_start):
        raise ValueError("walk-forward periods must be chronological and non-overlapping")
    return {
        "schema_version": 1,
        "folds": [{"fold_id": 1, "train": {"start": train_start, "end": train_end},
                    "validation": {"start": validation_start, "end": validation_end},
                    "test": {"start": test_start, "end": test_end}}],
        "selection_rule": "Parameters are fixed before validation/test; test remains locked.",
    }


def build_walk_forward_folds(
    observations: Iterable[Observation], *, train_ends: list[str], validation_span_days: int,
    test_span_days: int, start: str | None = None,
) -> list[WalkForwardFold]:
    """Build expanding-train, sequential validation/test folds.

    Boundaries are half-open and each observation is assigned to at most one
    fold's test segment. Availability is checked before assignment.
    """
    if not train_ends or validation_span_days <= 0 or test_span_days <= 0:
        raise ValueError("train_ends and positive validation/test spans are required")
    rows = sorted((item.validate() for item in observations), key=lambda item: parse_time(item.decision_time))
    lower = parse_time(start) if start else (parse_time(rows[0].decision_time) if rows else None)
    folds: list[WalkForwardFold] = []
    previous_test_end = None
    from datetime import timedelta
    for fold_id, train_end_text in enumerate(train_ends, 1):
        train_end = parse_time(train_end_text)
        validation_start = train_end
        validation_end = validation_start + timedelta(days=validation_span_days)
        test_start = validation_end
        test_end = test_start + timedelta(days=test_span_days)
        if lower and train_end <= lower:
            raise ValueError("each train end must be after the requested start")
        if previous_test_end and test_start < previous_test_end:
            raise ValueError("walk-forward folds must be chronological and non-overlapping")
        train = tuple(item for item in rows if (lower is None or parse_time(item.decision_time) >= lower) and parse_time(item.decision_time) < train_end)
        validation = tuple(item for item in rows if validation_start <= parse_time(item.decision_time) < validation_end)
        test = tuple(item for item in rows if test_start <= parse_time(item.decision_time) < test_end)
        folds.append(WalkForwardFold(fold_id, (lower or parse_time(rows[0].decision_time)).isoformat(), train_end.isoformat(), validation_start.isoformat(), validation_end.isoformat(), test_start.isoformat(), test_end.isoformat(), train, validation, test))
        previous_test_end = test_end
    assert_no_overlap([type("Split", (), {"observations": fold.test})() for fold in folds])
    return folds
