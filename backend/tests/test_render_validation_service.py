from pathlib import Path

from doc_generator import build_docx, build_pdf
from services.render_validation_service import validate_rendered_artifacts


def test_render_validation_matches_generated_artifacts(tmp_path: Path):
    structured_text = """# Introduction
This is the intro paragraph.

## Body
- first item
- second item

## Conclusion
Final wrap-up paragraph.
"""
    docx_path = tmp_path / "report.docx"
    pdf_path = tmp_path / "report.pdf"

    build_docx(
        title="Render Check",
        rules="Use standard academic structure",
        structured_text=structured_text,
        out_path=docx_path,
        layout_plan={"placements": [{"page": 1}], "totalPages": 1, "hardConstraintsApplied": []},
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {"heading_numbering": True, "max_heading_depth": 3}},
    )
    build_pdf(
        title="Render Check",
        rules="Use standard academic structure",
        structured_text=structured_text,
        out_path=pdf_path,
        layout_plan={"placements": [{"page": 1}], "totalPages": 1, "hardConstraintsApplied": []},
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {"heading_numbering": True, "max_heading_depth": 3}},
    )

    result = validate_rendered_artifacts(
        structured_text=structured_text,
        pdf_path=pdf_path,
        docx_path=docx_path,
        document_model={
            "blocks": [
                {"id": "root", "type": "document", "text": "Render Check"},
                {"id": "b1", "type": "heading", "text": "Introduction"},
                {"id": "b2", "type": "paragraph", "text": "This is the intro paragraph."},
                {"id": "b3", "type": "heading", "text": "Body"},
                {"id": "b4", "type": "list_item", "text": "first item"},
                {"id": "b5", "type": "list_item", "text": "second item"},
                {"id": "b6", "type": "heading", "text": "Conclusion"},
                {"id": "b7", "type": "paragraph", "text": "Final wrap-up paragraph."},
            ]
        },
        layout_plan={"placements": [{"page": 1}], "totalPages": 1},
        compiled_rules={"render_thresholds": {"minSimilarity": 10.0, "minHeadingMatchRatio": 0.0}},
    )

    assert result["accepted"] is True
    assert result["similarity"]["aggregate"] > 0
    assert "visual" in result
    assert result["visual"]["averageScore"] >= 0
    assert result["documentMetrics"]["docxParagraphs"] > 0
    assert result["documentMetrics"]["pdfPages"] >= 1


def test_per_page_visual_acceptance_policy(tmp_path: Path):
    """Verify that per-page visual threshold is enforced: no single page can have low visual fidelity."""
    structured_text = """# Section 1
Paragraph in section 1.

## Subsection 1.1
Details here.

# Section 2
Paragraph in section 2.

## Subsection 2.1
More details here.
"""
    docx_path = tmp_path / "report.docx"
    pdf_path = tmp_path / "report.pdf"

    build_docx(
        title="Per-Page Test",
        rules="Multi-page structure",
        structured_text=structured_text,
        out_path=docx_path,
        layout_plan={
            "placements": [
                {"page": 1},
                {"page": 2},
            ],
            "totalPages": 2,
            "pageCapacityLines": 48,
            "hardConstraintsApplied": [],
        },
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {"heading_numbering": True}},
    )
    build_pdf(
        title="Per-Page Test",
        rules="Multi-page structure",
        structured_text=structured_text,
        out_path=pdf_path,
        layout_plan={
            "placements": [
                {"page": 1},
                {"page": 2},
            ],
            "totalPages": 2,
            "pageCapacityLines": 48,
            "hardConstraintsApplied": [],
        },
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {"heading_numbering": True}},
    )

    result = validate_rendered_artifacts(
        structured_text=structured_text,
        pdf_path=pdf_path,
        docx_path=docx_path,
        document_model={
            "blocks": [
                {"id": "root", "type": "document", "text": "Per-Page Test"},
                {"id": "b1", "type": "heading", "text": "Section 1"},
                {"id": "b2", "type": "paragraph", "text": "Paragraph in section 1."},
                {"id": "b3", "type": "heading", "text": "Subsection 1.1"},
                {"id": "b4", "type": "paragraph", "text": "Details here."},
                {"id": "b5", "type": "heading", "text": "Section 2"},
                {"id": "b6", "type": "paragraph", "text": "Paragraph in section 2."},
                {"id": "b7", "type": "heading", "text": "Subsection 2.1"},
                {"id": "b8", "type": "paragraph", "text": "More details here."},
            ]
        },
        layout_plan={
            "placements": [{"page": 1}, {"page": 2}],
            "totalPages": 2,
            "pageCapacityLines": 48,
        },
        compiled_rules={
            "render_thresholds": {"minSimilarity": 10.0, "minHeadingMatchRatio": 0.0, "minVisualSimilarityPerPage": 65.0},
        },
    )

    # Verify visual metrics are present
    assert "visual" in result
    assert "pageScores" in result["visual"]
    assert len(result["visual"]["pageScores"]) >= 1
    
    # Verify per-page scores are calculated
    for page_score in result["visual"]["pageScores"]:
        assert "page" in page_score
        assert "score" in page_score
        assert 0 <= page_score["score"] <= 100
    
    # If any page failed, failed_pages should be reported
    if result["visual"]["failedPages"]:
        assert not result["accepted"], "Should reject if any page fails visual fidelity"
        assert any("Pages with low visual fidelity" in issue for issue in result.get("issues", [])), \
            "Should report failed pages in issues"


def test_adaptive_visual_threshold_by_content_type(tmp_path: Path):
    """Verify that visual thresholds adapt based on page content composition."""
    # Create a simple document
    structured_text = """# Heading 1
# Heading 2
# Heading 3
Some intro text here.
"""
    
    docx_path = tmp_path / "report.docx"
    pdf_path = tmp_path / "report.pdf"

    build_docx(
        title="Adaptive Threshold Test",
        rules="Test adaptive thresholds",
        structured_text=structured_text,
        out_path=docx_path,
        layout_plan={
            "placements": [{"page": 1}],
            "totalPages": 1,
            "pageCapacityLines": 48,
            "hardConstraintsApplied": [],
        },
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {}},
    )
    build_pdf(
        title="Adaptive Threshold Test",
        rules="Test adaptive thresholds",
        structured_text=structured_text,
        out_path=pdf_path,
        layout_plan={
            "placements": [{"page": 1}],
            "totalPages": 1,
            "pageCapacityLines": 48,
            "hardConstraintsApplied": [],
        },
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {}},
    )

    # Page with heading-dominant content (3 headings, 1 paragraph)
    heading_heavy_layout = {
        "placements": [{"page": 1}],
        "totalPages": 1,
        "pageCapacityLines": 48,
    }

    result = validate_rendered_artifacts(
        structured_text=structured_text,
        pdf_path=pdf_path,
        docx_path=docx_path,
        document_model={
            "blocks": [
                {"id": "root", "type": "document", "text": "Adaptive Threshold Test"},
                {"id": "b1", "type": "heading", "text": "Heading 1"},
                {"id": "b2", "type": "heading", "text": "Heading 2"},
                {"id": "b3", "type": "heading", "text": "Heading 3"},
                {"id": "b4", "type": "paragraph", "text": "Some intro text here."},
            ]
        },
        layout_plan=heading_heavy_layout,
        compiled_rules={"render_thresholds": {"minSimilarity": 10.0, "minHeadingMatchRatio": 0.0}},
    )

    # Verify adaptive thresholds are calculated and applied
    assert "visual" in result
    assert "pageScores" in result["visual"]
    
    for page_score in result["visual"]["pageScores"]:
        # Verify adaptive threshold is present and reasonable
        assert "adaptiveThreshold" in page_score
        adaptive = page_score["adaptiveThreshold"]
        assert 55.0 <= adaptive <= 75.0, f"Adaptive threshold {adaptive} out of expected range"
        
        # For heading-heavy page, threshold should be lower (60%)
        heading_count = page_score["expected"]["headingCount"]
        paragraph_count = page_score["expected"]["paragraphCount"]
        list_count = page_score["expected"]["listCount"]
        total = heading_count + paragraph_count + list_count
        
        if total > 0:
            heading_ratio = heading_count / total
            if heading_ratio >= 0.5:
                assert adaptive == 60.0, f"Heading-heavy page should have threshold 60%, got {adaptive}"


def test_adaptive_threshold_text_heavy_page():
    """Verify text-heavy pages get higher visual similarity threshold."""
    from services.render_validation_service import _adaptive_page_threshold
    
    # Text-heavy: 60% paragraphs
    text_heavy = {
        "headingCount": 1,
        "paragraphCount": 6,
        "listCount": 0,
    }
    assert _adaptive_page_threshold(text_heavy) == 70.0, "Text-heavy page should have 70% threshold"
    
    # List-heavy: 60% lists
    list_heavy = {
        "headingCount": 1,
        "paragraphCount": 1,
        "listCount": 6,
    }
    assert _adaptive_page_threshold(list_heavy) == 62.0, "List-heavy page should have 62% threshold"
    
    # Mixed content
    mixed = {
        "headingCount": 2,
        "paragraphCount": 2,
        "listCount": 2,
    }
    assert _adaptive_page_threshold(mixed) == 65.0, "Mixed content should have 65% threshold"


def test_render_validation_includes_structured_feedback_and_rule_penalty(tmp_path: Path):
    structured_text = """# Introduction
Intro paragraph with background and setup.

## Body
This body section intentionally avoids bullet points and citation markers.

## Conclusion
Closing remarks without reference section.
"""
    docx_path = tmp_path / "rule_penalty.docx"
    pdf_path = tmp_path / "rule_penalty.pdf"

    build_docx(
        title="Rule Penalty Test",
        rules="Use bullets and references",
        structured_text=structured_text,
        out_path=docx_path,
        layout_plan={"placements": [{"page": 1}], "totalPages": 1, "hardConstraintsApplied": []},
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {}},
    )
    build_pdf(
        title="Rule Penalty Test",
        rules="Use bullets and references",
        structured_text=structured_text,
        out_path=pdf_path,
        layout_plan={"placements": [{"page": 1}], "totalPages": 1, "hardConstraintsApplied": []},
        compiled_rules={"typography": {"line_spacing": "single", "alignment": "justified"}, "layout": {}},
    )

    result = validate_rendered_artifacts(
        structured_text=structured_text,
        pdf_path=pdf_path,
        docx_path=docx_path,
        document_model={
            "blocks": [
                {"id": "root", "type": "document", "text": "Rule Penalty Test"},
                {"id": "b1", "type": "heading", "text": "Introduction"},
                {"id": "b2", "type": "paragraph", "text": "Intro paragraph with background and setup."},
                {"id": "b3", "type": "heading", "text": "Body"},
                {"id": "b4", "type": "paragraph", "text": "This body section intentionally avoids bullet points."},
                {"id": "b5", "type": "heading", "text": "Conclusion"},
                {"id": "b6", "type": "paragraph", "text": "Closing remarks without reference section."},
            ]
        },
        layout_plan={"placements": [{"page": 1}], "totalPages": 1},
        compiled_rules={
            "render_thresholds": {"minSimilarity": 10.0, "minHeadingMatchRatio": 0.0},
            "content_constraints": {"require_bullets": True, "include_references": True},
            "typography": {"citation_style": "APA"},
        },
    )

    assert "structuredFeedback" in result
    assert "componentScores" in result
    assert "ruleCompliance" in result
    assert result["score"] <= 100.0
    assert len(result["ruleCompliance"]["violations"]) >= 1
    assert result["ruleCompliance"]["penalty"] > 0
    assert isinstance(result["suggestions"], list)
