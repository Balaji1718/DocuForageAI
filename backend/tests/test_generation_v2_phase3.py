from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.fonts import FontCache, FontSizeMetrics
from services.generation_v2.layout_simulator import simulate_layout
from services.generation_v2.models import DocumentSpec


def _cache() -> FontCache:
    by_font_size = {
        ("Calibri", Decimal("12")): FontSizeMetrics(
            font_name="Calibri",
            size_pt=Decimal("12"),
            ascender=1900,
            descender=-500,
            units_per_em=2048,
            cap_height=1450,
            line_height_ratio=Decimal("1.171875"),
            line_height_pt=Decimal("14.0625"),
            average_advance_width_units=1100,
        )
    }
    chars = {
        ("Calibri", Decimal("12"), Decimal("468")): 65,
        ("Calibri", Decimal("12"), Decimal("200")): 26,
    }
    return FontCache(by_font_size=by_font_size, chars_per_line_by_key=chars)


def _styles() -> dict:
    return {
        "Normal": {
            "font_name": "Calibri",
            "font_size_pt": Decimal("12"),
            "line_spacing": Decimal("1.0"),
            "space_before_pt": Decimal("0"),
            "space_after_pt": Decimal("0"),
        },
        "Heading1": {
            "font_name": "Calibri",
            "font_size_pt": Decimal("12"),
            "line_spacing": Decimal("1.0"),
            "space_before_pt": Decimal("0"),
            "space_after_pt": Decimal("0"),
        },
    }


def _doc(elements: list[dict]) -> DocumentSpec:
    return DocumentSpec.model_validate(
        {
            "title": "Layout test",
            "page_layout": {
                "width": {"value": 8.5, "unit": "in"},
                "height": {"value": 11.0, "unit": "in"},
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
                    "font_size": {"value": 12, "unit": "pt"},
                    "line_spacing": 1.0,
                },
                "Heading1": {
                    "font_name": "Calibri",
                    "font_size": {"value": 12, "unit": "pt"},
                    "line_spacing": 1.0,
                },
            },
            "elements": elements,
        }
    )


def test_simulator_matches_manual_calculation_within_five_percent():
    cache = _cache()
    styles = _styles()

    para_text = "A" * (65 * 20)  # 20 lines at calibrated 65 chars/line.
    elements = [
        {"type": "paragraph", "text": para_text, "style": "Normal", "overflow_strategy": "split"},
        {"type": "paragraph", "text": para_text, "style": "Normal", "overflow_strategy": "split"},
        {"type": "paragraph", "text": para_text, "style": "Normal", "overflow_strategy": "split"},
    ]

    spec = _doc(elements)
    annotated = simulate_layout(spec, styles, cache)

    estimated_total = sum(item["estimated_height_pt"] for item in annotated)
    line_height = 14.0625
    manual_total = 3 * (20 * line_height)

    err_pct = abs(estimated_total - manual_total) / manual_total * 100
    assert err_pct <= 5.0

    # with ~281pt each and 648pt usable area, 3rd item should move to page 2
    pages = [item["page"] for item in annotated]
    assert pages == [1, 1, 2]


def test_keep_with_next_pulls_heading_to_same_page_as_following_paragraph():
    cache = _cache()
    styles = _styles()

    filler = "X" * (65 * 45)  # approx 632.8pt, leaving little room on page 1
    heading = "Heading"
    body = "B" * (65 * 2)

    spec = _doc(
        [
            {"type": "paragraph", "text": filler, "style": "Normal", "overflow_strategy": "split"},
            {
                "type": "paragraph",
                "text": heading,
                "style": "Heading1",
                "keep_with_next": True,
                "overflow_strategy": "split",
            },
            {"type": "paragraph", "text": body, "style": "Normal", "overflow_strategy": "split"},
        ]
    )

    annotated = simulate_layout(spec, styles, cache)
    heading_item = annotated[1]
    body_item = annotated[2]

    assert heading_item["page"] == body_item["page"]
    assert heading_item["break_before"] is True


def test_overflow_handler_split_push_truncate_for_long_paragraph():
    cache = _cache()
    styles = _styles()

    # Force narrow text width calibration (26 chars/line), huge text so paragraph > full page.
    long_text = "word " * 600

    base_page_layout = {
        "width": {"value": 4.78, "unit": "in"},
        "height": {"value": 11.0, "unit": "in"},
        "margins": {
            "top": {"value": 1.0, "unit": "in"},
            "right": {"value": 1.0, "unit": "in"},
            "bottom": {"value": 1.0, "unit": "in"},
            "left": {"value": 1.0, "unit": "in"},
        },
    }

    def make_doc(strategy: str) -> DocumentSpec:
        return DocumentSpec.model_validate(
            {
                "title": "Overflow",
                "page_layout": base_page_layout,
                "styles": {
                    "Normal": {
                        "font_name": "Calibri",
                        "font_size": {"value": 12, "unit": "pt"},
                        "line_spacing": 1.0,
                    }
                },
                "elements": [
                    {
                        "type": "paragraph",
                        "text": long_text,
                        "style": "Normal",
                        "overflow_strategy": strategy,
                    }
                ],
            }
        )

    split_out = simulate_layout(make_doc("split"), styles, cache)
    push_out = simulate_layout(make_doc("push"), styles, cache)
    trunc_out = simulate_layout(make_doc("truncate"), styles, cache)

    assert len(split_out) >= 2
    assert any(item.get("split_part") == "head" for item in split_out)
    assert any(item.get("split_part") == "tail" for item in split_out)

    assert len(push_out) == 1
    assert push_out[0].get("insert_page_break_before") is True

    assert len(trunc_out) == 1
    assert trunc_out[0].get("truncated") is True
    assert trunc_out[0]["text"].endswith("…")
