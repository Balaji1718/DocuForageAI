"""
Rule Resolver - Merge formatting rules from multiple sources with priority system.
Combines system defaults, extracted rules, and user overrides.

Priority: System Defaults < Extracted Rules < User Overrides
"""

from __future__ import annotations
from typing import Any, Optional
import uuid
from datetime import datetime


# System-wide defaults (fallback values)
SYSTEM_DEFAULTS = {
    # PAGE - A4 size (8.27" × 11.69")
    "page_width_dxa": 11906,
    "page_height_dxa": 16838,
    "margin_top_dxa": 1440,      # 1.0"
    "margin_bottom_dxa": 1440,   # 1.0"
    "margin_left_dxa": 1800,     # 1.25"
    "margin_right_dxa": 1800,    # 1.25"
    "margin_header_dxa": 720,    # 0.5"
    "margin_footer_dxa": 720,    # 0.5"

    # BODY TEXT - Times New Roman, 12pt, 1.5x spacing
    "body_font": "Times New Roman",
    "body_size_halfpt": 24,      # 12pt
    "body_alignment": "both",     # Justified
    "body_line_spacing_val": 360, # 1.5x (240 = single, 360 = 1.5x, 480 = double)
    "body_line_spacing_rule": "auto",
    "body_space_before": 0,
    "body_space_after": 120,     # 10pt after paragraph
    "body_first_line_indent_dxa": 0,
    "body_line_spacing_factors": {
        "single": 1.0,
        "1": 1.0,
        "1.0": 1.0,
        "1.5": 1.5,
        "double": 2.0,
    },

    # COVER / SIGNATURE TYPOGRAPHY
    "cover_title_size_pt": 20.0,
    "cover_title_leading_factor": 1.15,
    "cover_title_alignment": "center",
    "cover_title_space_after_pt": 12.0,
    "cover_title_bold": True,
    "cover_subtitle_size_pt": 10.0,
    "cover_subtitle_leading_factor": 1.1,
    "cover_subtitle_alignment": "center",
    "cover_subtitle_space_after_pt": 10.0,
    "cover_subtitle_italic": True,
    "cover_summary_size_pt": 9.0,
    "cover_summary_leading_factor": 1.05,
    "cover_summary_alignment": "center",
    "cover_summary_space_after_pt": 8.0,
    "signature_alignment": "center",
    "signature_label_size_pt": 10.0,
    "signature_label_bold": True,
    "signature_line_size_pt": 10.0,
    "signature_name_size_pt": 9.0,
    "signature_name_italic": False,
    "signature_block_space_before_pt": 18.0,
    "heading_leading_factor": 1.2,
    "list_left_indent_pt": 18.0,
    "list_block_spacing_pt": 6.0,

    # HEADINGS - Calibri, decreasing sizes, bold
    "headings": {
        "1": {"font": "Calibri", "size_halfpt": 36, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 240, "space_after": 120, "numbering": False},
        "2": {"font": "Calibri", "size_halfpt": 32, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 200, "space_after": 100, "numbering": False},
        "3": {"font": "Calibri", "size_halfpt": 28, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 160, "space_after": 80, "numbering": False},
        "4": {"font": "Calibri", "size_halfpt": 26, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 120, "space_after": 60, "numbering": False},
        "5": {"font": "Calibri", "size_halfpt": 24, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 100, "space_after": 50, "numbering": False},
        "6": {"font": "Calibri", "size_halfpt": 22, "bold": True, "italic": False, "underline": False, "caps": False, "small_caps": False, "alignment": "left", "space_before": 80, "space_after": 40, "numbering": False},
    },

    # PAGE NUMBERING
    "has_page_numbers": False,
    "page_number_alignment": "center",
    "prelim_page_format": "lowerRoman",
    "body_page_format": "decimal",
    "page_number_section_restart": False,

    # DOCUMENT STRUCTURE
    "detected_section_headings": [],
    "has_toc": False,
    "has_list_of_figures": False,
    "has_bulleted_lists": False,
    "has_numbered_lists": False,

    # ELEMENTS
    "table_count": 0,
    "tables_use_borders": True,
    "image_count": 0,
    "has_cover_image": False,
    "footer_count": 0,
    "header_count": 0,

    # QUALITY FLAGS
    "has_markdown_leak": False,
    "has_xml_artifact_numbers": False,
    "has_mixed_fonts": False,
    "has_inconsistent_sizes": False,
    "font_substitution_detected": False,

    # METADATA
    "source_filename": None,
    "extraction_warnings": [],
    "confidence": "high",
}


def _deep_merge_dict(target: dict, source: dict) -> None:
    """
    Deep merge source dict into target dict in-place.
    Recursively merges nested dicts instead of replacing them.
    """
    for key, value in source.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            _deep_merge_dict(target[key], value)
        else:
            target[key] = value


def resolve_rules(
    extracted_rules: Optional[dict[str, Any]] = None,
    user_overrides: Optional[dict[str, Any]] = None,
    system_defaults: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Merge formatting rules from multiple sources with priority system.

    Priority Order (lowest to highest):
    1. System defaults
    2. Extracted rules (from uploaded DOCX)
    3. User overrides (from UI/API)

    Args:
        extracted_rules: Dict from extract_rules() function
        user_overrides: User-provided rule overrides
        system_defaults: Custom system defaults (uses built-in if None)

    Returns:
        Merged rules dict with all keys present, prioritized correctly
    """
    # Use built-in system defaults if none provided
    if system_defaults is None:
        system_defaults = SYSTEM_DEFAULTS.copy()
    else:
        # Merge with built-in to ensure all keys present
        merged_defaults = SYSTEM_DEFAULTS.copy()
        merged_defaults.update(system_defaults)
        system_defaults = merged_defaults

    # Start with system defaults
    resolved = system_defaults.copy()

    # Merge in extracted rules (overrides defaults)
    if extracted_rules:
        for key, value in extracted_rules.items():
            # Only override if value is not None
            if value is not None:
                if isinstance(value, dict) and key in resolved and isinstance(resolved[key], dict):
                    # For nested dicts (like headings), deep merge
                    _deep_merge_dict(resolved[key], value)
                else:
                    resolved[key] = value

    # Merge in user overrides (highest priority)
    if user_overrides:
        for key, value in user_overrides.items():
            if value is not None:
                if isinstance(value, dict) and key in resolved and isinstance(resolved[key], dict):
                    _deep_merge_dict(resolved[key], value)
                else:
                    resolved[key] = value

    # Add resolution metadata
    resolved["_resolved_at"] = datetime.now().isoformat()
    resolved["_sources"] = {
        "system_defaults": True,
        "extracted_rules": bool(extracted_rules),
        "user_overrides": bool(user_overrides),
    }

    return resolved


def create_rules_record(
    rules: dict[str, Any],
    document_name: str = "",
    document_type: str = "generic",
    notes: str = "",
) -> dict[str, Any]:
    """
    Create a storable rules record with metadata.

    Args:
        rules: Resolved rules dict from resolve_rules()
        document_name: Original document filename
        document_type: Category (academic, business, legal, medical, etc.)
        notes: User notes about these rules

    Returns:
        Rules record ready for Firestore storage
    """
    return {
        "rules_id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat(),
        "document_name": document_name,
        "document_type": document_type,
        "notes": notes,
        "rules": rules,
        "status": "active",
    }


def validate_rules(rules: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate resolved rules for correctness.

    Returns:
        (is_valid, list_of_warnings)
    """
    warnings = []

    # Check required keys
    required_keys = [
        "page_width_dxa",
        "page_height_dxa",
        "margin_top_dxa",
        "body_font",
        "body_size_halfpt",
    ]
    for key in required_keys:
        if key not in rules:
            warnings.append(f"Missing required key: {key}")
        elif rules[key] is None:
            warnings.append(f"Required key is None: {key}")

    # Check value ranges
    if rules.get("page_width_dxa") and rules["page_width_dxa"] < 3000:
        warnings.append("Page width suspiciously small (< 2 inches)")

    if rules.get("body_size_halfpt") and rules["body_size_halfpt"] < 16:
        warnings.append("Body font size very small (< 8pt)")

    if rules.get("body_size_halfpt") and rules["body_size_halfpt"] > 96:
        warnings.append("Body font size very large (> 48pt)")

    # Check margins
    margins = [
        rules.get("margin_top_dxa"),
        rules.get("margin_bottom_dxa"),
        rules.get("margin_left_dxa"),
        rules.get("margin_right_dxa"),
    ]
    for margin in margins:
        if margin and margin < 0:
            warnings.append("Negative margin detected")
        if margin and margin > 5400:  # > 3.75 inches
            warnings.append("Unusually large margin detected")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def diff_rules(rules1: dict[str, Any], rules2: dict[str, Any]) -> dict[str, Any]:
    """
    Find differences between two rules dicts.

    Args:
        rules1: First rules dict
        rules2: Second rules dict (to compare against)

    Returns:
        Dict showing what changed: {key: (old_value, new_value)}
    """
    changes = {}

    all_keys = set(rules1.keys()) | set(rules2.keys())

    for key in all_keys:
        val1 = rules1.get(key)
        val2 = rules2.get(key)

        if val1 != val2:
            changes[key] = {
                "before": val1,
                "after": val2,
            }

    return changes


# Example usage
if __name__ == "__main__":
    print("Rule Resolver - Examples\n")
    print("=" * 70)

    # Example 1: System defaults only
    print("\n1. SYSTEM DEFAULTS ONLY:")
    rules = resolve_rules()
    print(f"   Page: {rules['page_width_dxa']} × {rules['page_height_dxa']} DXA")
    print(f"   Font: {rules['body_font']} {rules['body_size_halfpt']/2}pt")
    print(f"   Margins: T={rules['margin_top_dxa']//1440}\" L={rules['margin_left_dxa']//1440}\"")

    # Example 2: Extracted rules + defaults
    print("\n2. EXTRACTED RULES (overrides defaults):")
    extracted = {
        "page_width_dxa": 11906,  # A4
        "body_font": "Arial",
        "body_size_halfpt": 22,  # 11pt
        "margin_left_dxa": 2160,  # 1.5"
    }
    rules2 = resolve_rules(extracted_rules=extracted)
    print(f"   Page: {rules2['page_width_dxa']} DXA (from extracted)")
    print(f"   Font: {rules2['body_font']} (from extracted)")
    print(f"   Margins: T={rules2['margin_top_dxa']//1440}\" (system default)")

    # Example 3: All three sources
    print("\n3. EXTRACTED + USER OVERRIDES:")
    overrides = {
        "body_size_halfpt": 26,  # 13pt - user wants bigger
        "margin_top_dxa": 2160,  # 1.5" - user wants more space
    }
    rules3 = resolve_rules(extracted_rules=extracted, user_overrides=overrides)
    print(f"   Font: {rules3['body_font']} {rules3['body_size_halfpt']/2}pt (Arial 13pt - user override)")
    print(f"   Margins: T={rules3['margin_top_dxa']//1440}\" (user override)")

    # Example 4: Validation
    print("\n4. VALIDATION:")
    is_valid, warnings = validate_rules(rules3)
    print(f"   Valid: {is_valid}")
    if warnings:
        for w in warnings:
            print(f"   ⚠️  {w}")
    else:
        print(f"   ✅ No warnings")

    # Example 5: Create storable record
    print("\n5. CREATE STORAGE RECORD:")
    record = create_rules_record(
        rules3,
        document_name="sample.docx",
        document_type="business",
        notes="Standard business report format",
    )
    print(f"   rules_id: {record['rules_id']}")
    print(f"   created_at: {record['created_at']}")
    print(f"   status: {record['status']}")

    print("\n" + "=" * 70)
