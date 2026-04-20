from __future__ import annotations

from dataclasses import dataclass

from .constants import PRIORITY_SYSTEM, PRIORITY_TEMPLATE, PRIORITY_USER


@dataclass(frozen=True)
class RuleProperty:
    property_name: str
    value: object
    priority: int
    source: str


def detect_rule_conflicts(properties: list[RuleProperty]) -> None:
    by_name: dict[str, list[RuleProperty]] = {}
    for item in properties:
        by_name.setdefault(item.property_name, []).append(item)

    keep_values = by_name.get("keep_with_next", [])
    break_values = by_name.get("force_page_break_before", [])

    keep_true = [p for p in keep_values if bool(p.value) is True]
    break_true = [p for p in break_values if bool(p.value) is True]

    if keep_true and break_true:
        keep_src = ", ".join(sorted({p.source for p in keep_true}))
        break_src = ", ".join(sorted({p.source for p in break_true}))
        raise ValueError(
            "Contradictory rules detected: keep_with_next=True conflicts with "
            f"force_page_break_before=True (sources: keep_with_next=[{keep_src}], "
            f"force_page_break_before=[{break_src}])"
        )


def resolve_rules(properties: list[RuleProperty]) -> dict[str, object]:
    detect_rule_conflicts(properties)

    merged: dict[str, tuple[int, object, str]] = {}
    for item in properties:
        if item.priority not in {PRIORITY_SYSTEM, PRIORITY_TEMPLATE, PRIORITY_USER}:
            raise ValueError(f"Invalid priority {item.priority} for property {item.property_name}")
        existing = merged.get(item.property_name)
        if existing is None or item.priority >= existing[0]:
            merged[item.property_name] = (item.priority, item.value, item.source)

    return {key: value for key, (_priority, value, _source) in merged.items()}
