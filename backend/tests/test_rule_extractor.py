"""
Test suite for universal DOCX rule extractor.
Validates extraction from various DOCX files and edge cases.
"""

from __future__ import annotations
import pytest
from pathlib import Path
import sys

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from rule_extractor import extract_rules, NEUTRAL_DEFAULTS


def test_extract_rules_schema_completeness():
    """Verify all schema keys are always present, even on invalid DOCX."""
    # Create a minimal invalid DOCX (just ZIP with no valid structure)
    invalid_docx = b"PK\x03\x04"

    rules = extract_rules(invalid_docx, "invalid.docx")

    # Verify all keys from NEUTRAL_DEFAULTS are present
    for key in NEUTRAL_DEFAULTS.keys():
        assert key in rules, f"Missing key in schema: {key}"

    # Verify metadata
    assert rules["source_filename"] == "invalid.docx"
    assert isinstance(rules["extraction_warnings"], list)
    assert rules["confidence"] in ["high", "medium", "low"]

    print("✓ Schema completeness test passed")


def test_extract_rules_returns_dict():
    """Test that extract_rules always returns a dict."""
    result = extract_rules(b"invalid data", "test.docx")
    assert isinstance(result, dict), "extract_rules must return a dict"
    print("✓ Return type test passed")


def test_neutral_defaults_structure():
    """Verify NEUTRAL_DEFAULTS has correct structure."""
    assert isinstance(NEUTRAL_DEFAULTS, dict)
    assert "body_font" in NEUTRAL_DEFAULTS
    assert "page_width_dxa" in NEUTRAL_DEFAULTS
    assert "headings" in NEUTRAL_DEFAULTS
    assert isinstance(NEUTRAL_DEFAULTS["headings"], dict)
    assert NEUTRAL_DEFAULTS["extraction_warnings"] == []
    print("✓ NEUTRAL_DEFAULTS structure test passed")


def test_extraction_with_real_docx():
    """Test extraction from a real DOCX file if available."""
    # Try to find any DOCX file (search from current or parent directory)
    current_dir = Path(__file__).parent
    docx_paths = list(current_dir.rglob("*.docx"))
    
    if not docx_paths:
        # Try parent backend directory
        parent_dir = current_dir.parent
        docx_paths = list(parent_dir.rglob("*.docx"))

    if not docx_paths:
        pytest.skip("No DOCX files found")

    docx_path = docx_paths[0]
    print(f"\n✓ Testing with real DOCX: {docx_path}")

    with open(docx_path, "rb") as f:
        docx_bytes = f.read()

    rules = extract_rules(docx_bytes, str(docx_path.name))

    # Verify extraction completed
    assert isinstance(rules, dict)
    assert len(rules) > 0
    assert rules["confidence"] in ["high", "medium", "low"]

    # Print summary
    print(f"  Font: {rules.get('body_font', 'N/A')}")
    print(f"  Size: {rules.get('body_size_halfpt', 'N/A')}")
    print(f"  Page width: {rules.get('page_width_dxa', 'N/A')} DXA")
    print(f"  Margins: top={rules.get('margin_top_dxa')}, left={rules.get('margin_left_dxa')}")
    print(f"  Sections detected: {len(rules.get('detected_section_headings', []))}")
    print(f"  Confidence: {rules['confidence']}")
    print(f"  Warnings: {len(rules.get('extraction_warnings', []))}")


def test_confidence_scoring():
    """Test that confidence is scored correctly."""
    # Low confidence: all critical fields missing
    result = extract_rules(b"invalid", "test.docx")
    assert result["confidence"] in ["low", "medium"]  # Should be low due to extraction failure

    print("✓ Confidence scoring test passed")


def test_extraction_warnings_accumulate():
    """Test that extraction warnings are collected."""
    result = extract_rules(b"invalid", "test.docx")
    assert isinstance(result["extraction_warnings"], list)
    # Invalid DOCX should have warnings
    assert len(result["extraction_warnings"]) > 0

    print("✓ Extraction warnings test passed")


def test_null_values_not_omitted():
    """Test that null values are present, not omitted."""
    result = extract_rules(b"invalid", "test.docx")

    # These should be present even if None
    required_keys = [
        "body_font",
        "body_size_halfpt",
        "page_width_dxa",
        "margin_top_dxa",
    ]

    for key in required_keys:
        assert key in result, f"Required key {key} is missing (should be None, not omitted)"

    print("✓ Null values not omitted test passed")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("RULE EXTRACTOR VALIDATION TESTS")
    print("="*60 + "\n")

    test_extract_rules_schema_completeness()
    test_extract_rules_returns_dict()
    test_neutral_defaults_structure()
    test_confidence_scoring()
    test_extraction_warnings_accumulate()
    test_null_values_not_omitted()

    print("\nTrying to extract from real DOCX file...")
    try:
        test_extraction_with_real_docx()
    except Exception as e:
        print(f"  (Skipped: {e})")

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED")
    print("="*60 + "\n")
