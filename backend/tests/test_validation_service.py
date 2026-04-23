from __future__ import annotations

from services.validation_service import enforce_and_validate


def test_validation_fails_with_placeholder_sections() -> None:
    text = "# Title\n\n## Introduction\nBrief intro."
    enforced, report = enforce_and_validate(text, ["Introduction", "Body", "Conclusion"])

    assert enforced == text
    assert report["ok"] is False
    assert any("missing required section heading" in msg.lower() for msg in report["errors"])


def test_validation_passes_with_structured_content() -> None:
    text = (
        "# Title\n\n"
        "## Introduction\n"
        "This introduction establishes context and scope for the academic analysis while "
        "framing the argument with clear motivation and concise definitions.\n\n"
        "## Body\n"
        "The body section develops core claims with evidence, methodological explanation, "
        "comparative reasoning, and discussion of implications across multiple paragraphs. "
        "It also includes limitations, assumptions, and practical interpretation for the reader.\n\n"
        "## Conclusion\n"
        "The conclusion synthesizes the analysis, reinforces findings, and states the final "
        "position with explicit alignment to the original objective."
    )
    _enforced, report = enforce_and_validate(text, ["Introduction", "Body", "Conclusion"])

    assert report["ok"] is True
    assert report["qualityScore"] > 60


def test_validation_returns_component_scores_and_structured_feedback() -> None:
    text = (
        "# Title\n\n"
        "## Introduction\n"
        "This introduction provides sufficient background context, defines objectives, and explains"
        " the analytical framing with enough detail to satisfy structure checks and readability needs.\n\n"
        "## Body\n"
        "- Evidence point one with explanation and implications.\n"
        "- Evidence point two with comparative analysis and methodological caveats.\n"
        "The body expands arguments with coherent paragraphs, references to observations, and a"
        " balanced discussion of assumptions, limitations, and practical outcomes for stakeholders.\n\n"
        "## Conclusion\n"
        "The conclusion synthesizes findings, reiterates key claims, and closes with clear alignment"
        " to the report objective and recommendations for next actions.\n\n"
        "## References\n"
        "(Smith, 2024)\n"
    )
    _enforced, report = enforce_and_validate(
        text,
        ["Introduction", "Body", "Conclusion"],
        compiled_rules={
            "content_constraints": {"require_bullets": True, "include_references": True},
            "typography": {"citation_style": "APA"},
        },
    )

    assert "componentScores" in report
    assert "componentMetrics" in report
    assert "structuredFeedback" in report
    assert "weakSections" in report
    assert "ruleViolations" in report

    for key in ["structureScore", "formattingScore", "ruleComplianceScore"]:
        assert 0.0 <= report["componentScores"][key] <= 100.0

    feedback = report["structuredFeedback"]
    assert "score" in feedback
    assert "issues" in feedback
    assert "suggestions" in feedback
    assert isinstance(feedback["issues"], list)
    assert isinstance(feedback["suggestions"], list)


def test_validation_strips_xml_artifact_numbers_before_validation() -> None:
    text = (
        "# Title\n\n"
        "## Introduction\n"
        "This introduction contains an XML artifact number 1234567 that should be stripped while still providing "
        "enough context, detail, and explanation to satisfy the section validator after cleanup.\n\n"
        "## Body\n"
        "The body section remains sufficiently long with multiple sentences, discussion points, and supporting "
        "detail so that validation remains stable after the cleanup step removes the leaked numeric token.\n\n"
        "## Conclusion\n"
        "The conclusion wraps up the report with enough words, closes the argument clearly, and avoids leaving any "
        "artifact number traces in the final validated output."
    )

    enforced, report = enforce_and_validate(text, ["Introduction", "Body", "Conclusion"])

    assert enforced == text
    assert report["ok"] is True
    assert report.get("has_xml_artifact_numbers") is True
    assert report.get("xml_artifact_number_count") == 1
