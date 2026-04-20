from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.constants import PRIORITY_SYSTEM, PRIORITY_TEMPLATE, PRIORITY_USER
from services.generation_v2.models import DocumentSpec
from services.generation_v2.rules import RuleProperty, detect_rule_conflicts, resolve_rules


def _valid_spec_payload() -> dict:
    return {
        "title": "Test",
        "page_layout": {
            "width": {"value": 8.27, "unit": "in"},
            "height": {"value": 11.69, "unit": "in"},
            "margins": {
                "top": {"value": 1.0, "unit": "in"},
                "right": {"value": 1.0, "unit": "in"},
                "bottom": {"value": 1.0, "unit": "in"},
                "left": {"value": 1.0, "unit": "in"},
            },
        },
        "styles": {
            "Normal": {
                "font_name": "Calibri",
                "font_size": {"value": 11, "unit": "pt"},
                "line_spacing": 1.15,
            }
        },
        "header": {"text": "Header", "style": "Normal"},
        "footer": {"text": "Page 1", "style": "Normal"},
        "elements": [
            {
                "type": "paragraph",
                "text": "Hello world",
                "style": "Normal",
                "keep_with_next": False,
                "force_page_break_before": False,
                "overflow_strategy": "split",
            }
        ],
    }


def test_models_raise_validation_error_on_bad_input():
    payload = _valid_spec_payload()
    payload["styles"]["Normal"]["font_size"]["unit"] = "cm"

    with pytest.raises(ValidationError):
        DocumentSpec.model_validate(payload)


def test_rule_resolver_priority_levels():
    properties = [
        RuleProperty("font_size_pt", 10, PRIORITY_SYSTEM, "system_default"),
        RuleProperty("font_size_pt", 11, PRIORITY_TEMPLATE, "template_v1"),
        RuleProperty("font_size_pt", 12, PRIORITY_USER, "user_override"),
        RuleProperty("line_spacing", 1.15, PRIORITY_SYSTEM, "system_default"),
        RuleProperty("line_spacing", 1.5, PRIORITY_TEMPLATE, "template_v1"),
    ]

    merged = resolve_rules(properties)
    assert merged["font_size_pt"] == 12
    assert merged["line_spacing"] == 1.5


def test_conflict_detection_raises_on_contradictory_rules():
    properties = [
        RuleProperty("keep_with_next", True, PRIORITY_TEMPLATE, "template"),
        RuleProperty("force_page_break_before", True, PRIORITY_USER, "user"),
    ]

    with pytest.raises(ValueError, match="Contradictory rules detected"):
        detect_rule_conflicts(properties)


def test_document_spec_round_trip_preserves_data():
    payload = _valid_spec_payload()
    spec = DocumentSpec.model_validate(payload)
    dumped = spec.model_dump()
    spec_roundtrip = DocumentSpec.model_validate(dumped)
    assert spec_roundtrip.model_dump() == dumped
