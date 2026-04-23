"""
Test suite for rule resolver (Phase 2: Rules merging and storage).
Tests rule priority system, validation, and storage record creation.
"""

from __future__ import annotations
import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.rule_resolver import (
    resolve_rules,
    create_rules_record,
    validate_rules,
    diff_rules,
    SYSTEM_DEFAULTS,
)


class TestRuleResolver:
    """Tests for rule resolution and merging."""

    def test_system_defaults_only(self):
        """Test resolution with no extracted or user rules."""
        rules = resolve_rules()

        # Should have all system defaults
        assert rules["body_font"] == "Times New Roman"
        assert rules["body_size_halfpt"] == 24  # 12pt
        assert rules["page_width_dxa"] == 11906  # A4 width
        assert rules["page_height_dxa"] == 16838  # A4 height
        assert rules["margin_top_dxa"] == 1440  # 1"
        print("✓ System defaults loaded correctly")

    def test_extracted_rules_override_defaults(self):
        """Test that extracted rules override system defaults."""
        extracted = {
            "body_font": "Arial",
            "body_size_halfpt": 22,
            "page_width_dxa": 11906,  # A4
        }
        rules = resolve_rules(extracted_rules=extracted)

        assert rules["body_font"] == "Arial"  # From extracted
        assert rules["body_size_halfpt"] == 22  # From extracted
        assert rules["page_width_dxa"] == 11906  # From extracted
        assert rules["margin_top_dxa"] == 1440  # Still from defaults
        print("✓ Extracted rules override defaults")

    def test_user_overrides_highest_priority(self):
        """Test that user overrides have highest priority."""
        extracted = {"body_font": "Arial", "body_size_halfpt": 22}
        overrides = {"body_size_halfpt": 26, "margin_top_dxa": 2160}

        rules = resolve_rules(extracted_rules=extracted, user_overrides=overrides)

        assert rules["body_font"] == "Arial"  # From extracted
        assert rules["body_size_halfpt"] == 26  # From overrides (highest)
        assert rules["margin_top_dxa"] == 2160  # From overrides
        print("✓ User overrides have highest priority")

    def test_none_values_not_applied(self):
        """Test that None values don't override valid values."""
        extracted = {"body_font": None, "body_size_halfpt": 22}
        rules = resolve_rules(extracted_rules=extracted)

        assert rules["body_font"] == "Times New Roman"  # Defaults, extracted was None
        assert rules["body_size_halfpt"] == 22  # From extracted
        print("✓ None values don't override valid values")

    def test_nested_dict_merge(self):
        """Test that nested dicts (like headings) merge correctly."""
        extracted = {
            "headings": {
                "1": {"font": "Calibri Light", "size_halfpt": 40},
            }
        }
        rules = resolve_rules(extracted_rules=extracted)

        # Should have all heading levels with merged values
        assert rules["headings"]["1"]["font"] == "Calibri Light"  # Extracted
        assert rules["headings"]["1"]["size_halfpt"] == 40  # Extracted
        assert rules["headings"]["1"]["bold"] == True  # Still from default
        assert rules["headings"]["2"]["font"] == "Calibri"  # Still default
        print("✓ Nested dicts merge correctly")

    def test_all_schema_keys_present(self):
        """Test that all system default keys are in resolved rules."""
        rules = resolve_rules()

        for key in SYSTEM_DEFAULTS.keys():
            assert key in rules, f"Missing key: {key}"

        print(f"✓ All {len(SYSTEM_DEFAULTS)} schema keys present")

    def test_metadata_added_to_resolved(self):
        """Test that resolution metadata is added."""
        rules = resolve_rules()

        assert "_resolved_at" in rules
        assert "_sources" in rules
        assert rules["_sources"]["system_defaults"] == True
        assert rules["_sources"]["extracted_rules"] == False
        print("✓ Resolution metadata added correctly")


class TestValidation:
    """Tests for rule validation."""

    def test_valid_rules(self):
        """Test validation of correct rules."""
        rules = resolve_rules()
        is_valid, warnings = validate_rules(rules)

        assert is_valid == True
        assert len(warnings) == 0
        print("✓ Valid rules pass validation")

    def test_invalid_page_width(self):
        """Test detection of invalid page width."""
        rules = resolve_rules()
        rules["page_width_dxa"] = 2000  # Too small

        is_valid, warnings = validate_rules(rules)

        assert is_valid == False
        assert any("page width" in w.lower() for w in warnings)
        print("✓ Invalid page width detected")

    def test_invalid_font_size(self):
        """Test detection of invalid font sizes."""
        rules = resolve_rules()
        rules["body_size_halfpt"] = 200  # Too large (100pt)

        is_valid, warnings = validate_rules(rules)

        assert is_valid == False
        assert any("font size" in w.lower() and "large" in w.lower() for w in warnings)
        print("✓ Invalid font size detected")

    def test_negative_margin(self):
        """Test detection of negative margins."""
        rules = resolve_rules()
        rules["margin_left_dxa"] = -500

        is_valid, warnings = validate_rules(rules)

        assert is_valid == False
        assert any("negative" in w.lower() for w in warnings)
        print("✓ Negative margin detected")

    def test_missing_required_key(self):
        """Test detection of missing required keys."""
        rules = resolve_rules()
        del rules["body_font"]

        is_valid, warnings = validate_rules(rules)

        assert is_valid == False
        assert any("missing" in w.lower() for w in warnings)
        print("✓ Missing required key detected")


class TestStorageRecord:
    """Tests for creating storage records."""

    def test_create_basic_record(self):
        """Test creating a storage record."""
        rules = resolve_rules()
        record = create_rules_record(rules, document_name="test.docx")

        assert "rules_id" in record
        assert record["rules_id"] is not None
        assert record["document_name"] == "test.docx"
        assert record["status"] == "active"
        assert "created_at" in record
        assert record["rules"] == rules
        print("✓ Storage record created correctly")

    def test_record_has_metadata(self):
        """Test that record includes all metadata."""
        rules = resolve_rules()
        record = create_rules_record(
            rules,
            document_name="sample.docx",
            document_type="business",
            notes="My custom rules",
        )

        assert record["document_type"] == "business"
        assert record["notes"] == "My custom rules"
        assert record["document_name"] == "sample.docx"
        print("✓ Record metadata complete")

    def test_unique_rule_ids(self):
        """Test that each record gets unique ID."""
        rules = resolve_rules()
        record1 = create_rules_record(rules)
        record2 = create_rules_record(rules)

        assert record1["rules_id"] != record2["rules_id"]
        print("✓ Unique rule IDs generated")


class TestDiff:
    """Tests for rules diffing."""

    def test_diff_identical_rules(self):
        """Test diff of identical rules."""
        rules1 = resolve_rules()
        rules2 = resolve_rules()

        diff = diff_rules(rules1, rules2)

        # Exclude metadata fields that will differ
        filtered_diff = {k: v for k, v in diff.items() if not k.startswith("_")}
        assert len(filtered_diff) == 0
        print("✓ Identical rules show no diff")

    def test_diff_changed_values(self):
        """Test diff detecting changed values."""
        rules1 = resolve_rules()
        rules2 = resolve_rules(extracted_rules={"body_font": "Arial", "body_size_halfpt": 20})

        diff = diff_rules(rules1, rules2)

        assert "body_font" in diff
        assert diff["body_font"]["before"] == "Times New Roman"
        assert diff["body_font"]["after"] == "Arial"

        assert "body_size_halfpt" in diff
        assert diff["body_size_halfpt"]["before"] == 24
        assert diff["body_size_halfpt"]["after"] == 20
        print("✓ Diff detects changed values")


class TestPriority:
    """Tests for rule priority system."""

    def test_priority_system_complete(self):
        """Test complete priority chain: defaults -> extracted -> overrides."""
        extracted = {
            "body_font": "Calibri",
            "body_size_halfpt": 22,
            "margin_left_dxa": 1800,
        }
        overrides = {
            "body_size_halfpt": 24,  # Override extracted
            "margin_top_dxa": 1800,  # Override default
        }

        rules = resolve_rules(extracted_rules=extracted, user_overrides=overrides)

        # body_font: from extracted (not in overrides)
        assert rules["body_font"] == "Calibri"

        # body_size_halfpt: from overrides (highest priority)
        assert rules["body_size_halfpt"] == 24

        # margin_left_dxa: from extracted (overrides default)
        assert rules["margin_left_dxa"] == 1800

        # margin_top_dxa: from overrides (overrides default)
        assert rules["margin_top_dxa"] == 1800

        # margin_right_dxa: from default (no override)
        assert rules["margin_right_dxa"] == 1800

        print("✓ Complete priority chain works correctly")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("RULE RESOLVER TESTS (Phase 2)")
    print("="*70 + "\n")

    # Run with pytest if available
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], cwd=Path(__file__).parent.parent)
    exit(result.returncode)
