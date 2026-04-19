from __future__ import annotations

from services.validation_service import enforce_and_validate


def test_validation_fails_with_placeholder_sections() -> None:
    text = "# Title\n\n## Introduction\nBrief intro."
    enforced, report = enforce_and_validate(text, ["Introduction", "Body", "Conclusion"])

    assert "## Body" in enforced
    assert report["ok"] is False
    assert any("placeholder" in msg.lower() for msg in report["errors"])


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
