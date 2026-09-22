"""Explicit provider-capability claim checks for dataset workflows."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


def assess_capabilities(capabilities: Iterable[Any], *, provider_names: Iterable[str],
                        required_fields: Iterable[str] = ("interval_support", "corporate_action_support", "point_in_time_support")) -> dict[str, Any]:
    """Return a conservative capability report; never infer unsupported claims."""
    required = tuple(required_fields)
    wanted = sorted({str(name) for name in provider_names})
    indexed = {}
    for capability in capabilities:
        data = asdict(capability) if is_dataclass(capability) else dict(capability)
        indexed[str(data.get("provider"))] = data
    items = []
    for provider in wanted:
        data = indexed.get(provider)
        missing = [field for field in required if not data or not str(data.get(field, "")).strip()]
        items.append({"provider": provider, "status": "DECLARED" if data and not missing else "UNRESOLVED", "missing_fields": missing})
    blocked = [item for item in items if item["status"] != "DECLARED"]
    return {"schema_version": 1, "status": "READY" if wanted and not blocked else "CAPABILITY_UNRESOLVED",
            "providers": wanted, "required_fields": list(required), "items": items,
            "guardrails": ["Declared capability is not proof of data sufficiency", "No provider substitution", "Point-in-time claims require explicit provider declaration"]}
