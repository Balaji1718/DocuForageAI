"""Phase 7A: Rule Override Presets - Testing preset application and backend handling."""
from __future__ import annotations

from routes.report_routes import _build_rule_overrides


def test_preset_academic_values_convert_correctly():
    """Verify academic preset values are properly converted to backend format."""
    preset_overrides = {
        "bodyFont": "Times New Roman",
        "bodySizePt": "12",
        "marginTopIn": "1.0",
        "marginLeftIn": "1.0",
        "marginBottomIn": "1.0",
        "marginRightIn": "1.0",
        "lineSpacingPt": "24.0",
    }

    result = _build_rule_overrides(preset_overrides)

    assert result["body_font"] == "Times New Roman"
    assert result["body_size_halfpt"] == 24  # 12pt * 2
    assert result["margin_top_dxa"] == 1440  # 1 inch * 1440 twips/inch
    assert result["margin_left_dxa"] == 1440
    assert result["margin_bottom_dxa"] == 1440
    assert result["margin_right_dxa"] == 1440
    assert result["body_line_spacing_val"] == 480  # 24pt * 20 twips/pt


def test_preset_formal_values_convert_correctly():
    """Verify formal preset values are properly converted."""
    preset_overrides = {
        "bodyFont": "Calibri",
        "bodySizePt": "11",
        "marginTopIn": "0.75",
        "marginLeftIn": "0.75",
        "marginBottomIn": "0.75",
        "marginRightIn": "0.75",
        "lineSpacingPt": "16.5",
    }

    result = _build_rule_overrides(preset_overrides)

    assert result["body_font"] == "Calibri"
    assert result["body_size_halfpt"] == 22  # 11pt * 2
    assert result["margin_top_dxa"] == 1080  # 0.75 inch * 1440
    assert result["body_line_spacing_val"] == 330  # 16.5pt * 20


def test_preset_compact_values_convert_correctly():
    """Verify compact preset values are properly converted."""
    preset_overrides = {
        "bodyFont": "Arial",
        "bodySizePt": "10",
        "marginTopIn": "0.5",
        "marginLeftIn": "0.5",
        "marginBottomIn": "0.5",
        "marginRightIn": "0.5",
        "lineSpacingPt": "12.0",
    }

    result = _build_rule_overrides(preset_overrides)

    assert result["body_font"] == "Arial"
    assert result["body_size_halfpt"] == 20  # 10pt * 2
    assert result["margin_top_dxa"] == 720  # 0.5 inch * 1440
    assert result["body_line_spacing_val"] == 240  # 12pt * 20


def test_preset_generous_spacing_values():
    """Verify generous spacing preset values."""
    preset_overrides = {
        "bodyFont": "Calibri",
        "bodySizePt": "12",
        "marginTopIn": "1.5",
        "marginLeftIn": "1.5",
        "marginBottomIn": "1.5",
        "marginRightIn": "1.5",
        "lineSpacingPt": "24.0",
    }

    result = _build_rule_overrides(preset_overrides)

    assert result["body_font"] == "Calibri"
    assert result["body_size_halfpt"] == 24
    assert result["margin_top_dxa"] == 2160  # 1.5 inch * 1440
    assert result["body_line_spacing_val"] == 480


def test_preset_minimal_spacing_values():
    """Verify minimal spacing preset values."""
    preset_overrides = {
        "bodyFont": "Courier",
        "bodySizePt": "10",
        "marginTopIn": "0.25",
        "marginLeftIn": "0.25",
        "marginBottomIn": "0.25",
        "marginRightIn": "0.25",
        "lineSpacingPt": "12.0",
    }

    result = _build_rule_overrides(preset_overrides)

    assert result["body_font"] == "Courier"
    assert result["body_size_halfpt"] == 20
    assert result["margin_top_dxa"] == 360  # 0.25 inch * 1440
    assert result["body_line_spacing_val"] == 240


def test_partial_preset_with_partial_overrides():
    """Verify that presets can be partially applied with existing overrides."""
    existing = {
        "bodyFont": "Garamond",
        "bodySizePt": "14",
    }

    partial_preset = {
        "marginTopIn": "1.25",
        "marginLeftIn": "1.25",
        "lineSpacingPt": "18.0",
    }

    result = _build_rule_overrides({**existing, **partial_preset})

    assert result["body_font"] == "Garamond"
    assert result["body_size_halfpt"] == 28  # 14pt * 2
    assert result["margin_top_dxa"] == 1800  # 1.25 inch * 1440
    assert result["body_line_spacing_val"] == 360  # 18pt * 20


def test_empty_preset_values_are_ignored():
    """Verify that empty preset values don't override existing settings."""
    result = _build_rule_overrides({
        "bodyFont": "",
        "bodySizePt": "",
        "marginTopIn": "",
    })

    assert "body_font" not in result
    assert "body_size_halfpt" not in result
    assert "margin_top_dxa" not in result


def test_invalid_preset_values_are_skipped():
    """Verify that invalid preset values don't cause errors."""
    result = _build_rule_overrides({
        "bodyFont": "ValidFont",
        "bodySizePt": "invalid_number",
        "marginTopIn": "not_a_float",
    })

    assert result["body_font"] == "ValidFont"
    assert "body_size_halfpt" not in result
    assert "margin_top_dxa" not in result


def test_fractional_margins_and_spacing():
    """Verify fractional values are handled correctly."""
    result = _build_rule_overrides({
        "marginTopIn": "1.333",
        "lineSpacingPt": "13.5",
    })

    assert result["margin_top_dxa"] == 1920  # 1.333 * 1440 ≈ 1920 (rounded)
    assert result["body_line_spacing_val"] == 270  # 13.5 * 20
