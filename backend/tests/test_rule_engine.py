from __future__ import annotations

from services.rule_compiler import build_compiled_rules_guidance, compile_rules
from services.rule_service import parse_rules_text


def test_rule_parser_extracts_sections_and_structure() -> None:
    rules = (
        "Use formal academic tone. Include Introduction, Methodology, Results, Conclusion, References. "
        "Use APA citation, justified alignment, double spacing, and numbered headings. "
        "You must include bullet points for key findings."
    )

    parsed = parse_rules_text(rules)

    assert "Introduction" in parsed["required_sections"]
    assert "Conclusion" in parsed["required_sections"]
    assert parsed["formatting"]["citation_style"] == "APA"
    assert parsed["formatting"]["alignment"] == "justified"
    assert parsed["formatting"]["line_spacing"] == "double"
    assert parsed["structural_requirements"]["include_references"] is True
    assert len(parsed["constraints"]["hard"]) >= 1


def test_rule_compiler_builds_deterministic_schema() -> None:
    parsed = parse_rules_text(
        "Include Introduction, Body, Conclusion. Use formal tone, numbered headings, and APA style."
    )
    compiled = compile_rules(parsed)

    assert compiled["deterministic"] is True
    assert compiled["version"] == "1.0"
    assert len(compiled["sections"]) >= 3
    assert compiled["layout"]["heading_numbering"] is True

    guidance = build_compiled_rules_guidance(compiled)
    assert "Compiled constraints" in guidance
    assert "Required section order" in guidance


def test_rule_compiler_latest_instruction_wins() -> None:
    parsed = parse_rules_text(
        "Use APA citation. Then use MLA citation. "
        "Use double spacing. Finally use single spacing. "
        "Use justified alignment and later left align text."
    )
    compiled = compile_rules(parsed)

    assert compiled["typography"]["citation_style"] == "MLA"
    assert compiled["typography"]["line_spacing"] == "single"
    assert compiled["typography"]["alignment"] == "left"

    trace = compiled["conflict_resolution"]["trace"]
    fields = {item["field"] for item in trace}
    assert "citation_style" in fields
    assert "line_spacing" in fields
    assert "alignment" in fields
