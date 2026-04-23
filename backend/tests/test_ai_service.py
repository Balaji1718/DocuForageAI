from __future__ import annotations

from services.ai_service import generate_structured_text


def test_feedback_aware_partial_regeneration(monkeypatch):
    calls: list[dict] = []

    def _fake_generate_with_collaboration(*, title, rules, content, chunk_index, total_chunks):
        calls.append(
            {
                "title": title,
                "rules": rules,
                "content": content,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
            }
        )

        # First pass generation (weak body section)
        if "PARTIAL REGENERATION TASK" not in rules and "STRICT OUTPUT ENFORCEMENT" not in rules:
            return (
                "# Introduction\n"
                "This introduction provides enough context, motivation, scope, and framing details to satisfy"
                " structure requirements for a formal report draft.\n\n"
                "## Body\n"
                "Too short.\n\n"
                "## Conclusion\n"
                "This conclusion summarizes implications, restates key findings, and closes the report with"
                " clear alignment to objectives and next actions."
            )

        # Partial regeneration pass for Body
        if "PARTIAL REGENERATION TASK" in rules:
            assert "Missing headings detected" in rules
            assert "Poor structure detected" in rules
            return (
                "## Body\n"
                "- Core finding one with rationale and impact.\n"
                "- Core finding two with comparative evidence and caveats.\n"
                "This section expands the analysis with methodological details, assumptions, constraints,"
                " practical implications, implementation notes, and recommendations for further study"
                " across relevant stakeholders and operational contexts."
            )

        # Full retry should not be needed in this test
        return "# Introduction\nFallback"

    monkeypatch.setattr("services.ai_service.generate_with_collaboration", _fake_generate_with_collaboration)
    monkeypatch.setattr(
        "services.ai_service.parse_rules_text",
        lambda _rules: {"required_sections": ["Introduction", "Body", "Conclusion"], "formatting": {}},
    )
    monkeypatch.setattr("services.ai_service.compile_rules", lambda _parsed: {"content_constraints": {}})
    monkeypatch.setattr("services.ai_service.build_compiled_rules_guidance", lambda _compiled: "Rules")
    monkeypatch.setattr("services.ai_service.parse_reference_content", lambda _content, _mime: {"enabled": False})
    monkeypatch.setattr("services.ai_service.build_reference_guidance", lambda _ref: "Ref")

    text, parsed_rules, _parsed_reference, report = generate_structured_text(
        title="Targeted Correction",
        rules="Use structure",
        content="Source content",
        reference_content="",
        reference_mime_type="text/plain",
        chunk_size=8000,
        retries=0,
    )

    assert parsed_rules["required_sections"] == ["Introduction", "Body", "Conclusion"]
    assert report["ok"] is True
    assert report.get("partialRegeneration") is True
    assert "Core finding one" in text
    assert "Too short." not in text
    assert any("PARTIAL REGENERATION TASK" in item["rules"] for item in calls)


def test_section_plan_applies_modes(monkeypatch):
    def _fake_generate_with_collaboration(*, title, rules, content, chunk_index, total_chunks):
        return (
            "# Introduction\n"
            "This introduction covers context, goals, assumptions, and expected outcomes for this report.\n\n"
            "## Methodology\n"
            "The methodology explains steps, data handling, decision criteria, and validation checkpoints in detail.\n\n"
            "## Conclusion\n"
            "This conclusion summarizes results and closes the narrative with implementation implications."
        )

    monkeypatch.setattr("services.ai_service.generate_with_collaboration", _fake_generate_with_collaboration)
    monkeypatch.setattr(
        "services.ai_service.parse_rules_text",
        lambda _rules: {"required_sections": ["Introduction", "Body", "Conclusion"], "formatting": {}},
    )
    monkeypatch.setattr("services.ai_service.compile_rules", lambda _parsed: {"content_constraints": {}})
    monkeypatch.setattr("services.ai_service.build_compiled_rules_guidance", lambda _compiled: "Rules")
    monkeypatch.setattr("services.ai_service.parse_reference_content", lambda _content, _mime: {"enabled": False})
    monkeypatch.setattr("services.ai_service.build_reference_guidance", lambda _ref: "Ref")
    monkeypatch.setattr(
        "services.ai_service.enforce_and_validate",
        lambda text, _required_sections, compiled_rules=None: (
            text,
            {
                "ok": True,
                "errors": [],
                "warnings": [],
                "qualityScore": 100,
                "weakSections": [],
                "issues": [],
                "suggestions": [],
            },
        ),
    )

    text, _parsed_rules, _parsed_reference, report = generate_structured_text(
        title="Section Plan",
        rules="Use structure",
        content="Source content",
        reference_content="",
        reference_mime_type="text/plain",
        section_plan=[
            {"title": "Introduction", "mode": "auto_generate"},
            {"title": "Analyst Notes", "mode": "user_provides"},
            {"title": "Methodology", "mode": "auto_generate"},
            {"title": "Conclusion", "mode": "skip"},
        ],
        chunk_size=8000,
        retries=0,
    )

    assert report["ok"] is True
    assert "## Introduction" in text
    assert "## Methodology" in text
    assert "## Analyst Notes" in text
    assert "user-provided content" in text
    assert "## Conclusion" not in text


def test_section_plan_generates_sections_independently(monkeypatch):
    calls: list[dict] = []

    def _fake_generate_with_collaboration(*, title, rules, content, chunk_index, total_chunks):
        calls.append(
            {
                "title": title,
                "rules": rules,
                "content": content,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
            }
        )
        if "Introduction" in rules:
            return "## Introduction\nIndependent introduction content."
        if "Methodology" in rules:
            return "## Methodology\nIndependent methodology content."
        return "## Fallback\nUnexpected section."

    monkeypatch.setattr("services.ai_service.generate_with_collaboration", _fake_generate_with_collaboration)
    monkeypatch.setattr("services.ai_service.ENABLE_LARGE_CONTENT_REFINEMENT", False)
    monkeypatch.setattr(
        "services.ai_service.parse_rules_text",
        lambda _rules: {"required_sections": ["Introduction", "Methodology"], "formatting": {}},
    )
    monkeypatch.setattr("services.ai_service.compile_rules", lambda _parsed: {"content_constraints": {}})
    monkeypatch.setattr("services.ai_service.build_compiled_rules_guidance", lambda _compiled: "Rules")
    monkeypatch.setattr("services.ai_service.parse_reference_content", lambda _content, _mime: {"enabled": False})
    monkeypatch.setattr("services.ai_service.build_reference_guidance", lambda _ref: "Ref")
    monkeypatch.setattr(
        "services.ai_service.enforce_and_validate",
        lambda text, _required_sections, compiled_rules=None: (
            text,
            {
                "ok": True,
                "errors": [],
                "warnings": [],
                "qualityScore": 100,
                "weakSections": [],
                "issues": [],
                "suggestions": [],
            },
        ),
    )

    text, _parsed_rules, _parsed_reference, report = generate_structured_text(
        title="Section By Section",
        rules="Use structure",
        content="Source content",
        reference_content="",
        reference_mime_type="text/plain",
        section_plan=[
            {"title": "Introduction", "mode": "auto_generate"},
            {"title": "User Notes", "mode": "user_provides"},
            {"title": "Methodology", "mode": "auto_generate"},
            {"title": "Appendix", "mode": "skip"},
        ],
        chunk_size=8000,
        retries=0,
    )

    assert report["ok"] is True
    assert len(calls) == 2
    assert all(call["chunk_index"] == 1 for call in calls)
    assert all(call["total_chunks"] == 1 for call in calls)
    assert "Generate only the 'Introduction' section" in calls[0]["rules"]
    assert "Generate only the 'Methodology' section" in calls[1]["rules"]
    assert "## Introduction" in text
    assert "## Methodology" in text
    assert "## User Notes" in text
    assert "## Appendix" not in text
