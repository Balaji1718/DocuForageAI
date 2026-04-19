from services.layout_engine_service import (
    correct_layout_from_render_feedback,
    evaluate_layout_acceptance,
    plan_layout_with_acceptance,
    repair_layout_plan,
    simulate_layout,
    solve_layout,
    _analyze_page_content_type,
    _content_aware_capacity_adjustment,
)


def test_solve_layout_and_simulation_basic():
    document_model = {
        "blocks": [
            {"id": "b0", "type": "document", "text": "Root"},
            {"id": "h1", "type": "heading", "text": "Introduction"},
            {"id": "p1", "type": "paragraph", "text": "A" * 400},
            {"id": "h2", "type": "heading", "text": "Body"},
            {"id": "li1", "type": "list_item", "text": "point one"},
            {"id": "tr1", "type": "table_row", "text": "A | B | C"},
        ]
    }
    compiled_rules = {
        "typography": {"line_spacing": "single", "alignment": "justified"},
        "layout": {"max_heading_depth": 3},
    }

    layout = solve_layout(document_model, compiled_rules)
    assert layout["deterministic"] is True
    assert layout["totalPages"] >= 1
    assert len(layout["placements"]) == 5

    simulation = simulate_layout(layout, document_model)
    assert "ok" in simulation
    assert "layoutSimilarityProxy" in simulation
    assert isinstance(simulation["layoutSimilarityProxy"], float)


def test_layout_repair_and_acceptance_flow():
    document_model = {
        "blocks": [
            {"id": "root", "type": "document", "text": "Root"},
            {"id": "h1", "type": "heading", "text": "Section One"},
            {"id": "p1", "type": "paragraph", "text": "A" * 3901},
            {"id": "h2", "type": "heading", "text": "Section Two"},
            {"id": "p2", "type": "paragraph", "text": "B" * 20},
            {"id": "p3", "type": "paragraph", "text": "C" * 20},
        ]
    }

    layout = solve_layout(document_model)
    simulation = simulate_layout(layout, document_model)
    assert simulation["warnings"]

    repaired = repair_layout_plan(layout, document_model)
    repaired_simulation = simulate_layout(repaired, document_model)
    assert repaired["repairApplied"] is True
    assert len(repaired_simulation["warnings"]) < len(simulation["warnings"])

    acceptance = evaluate_layout_acceptance(repaired_simulation)
    assert "accepted" in acceptance
    assert "thresholds" in acceptance

    result = plan_layout_with_acceptance(document_model)
    assert "layoutPlan" in result
    assert "preRenderSimulation" in result
    assert "layoutCorrections" in result


def test_correct_layout_from_render_feedback_tightens_layout():
    document_model = {
        "blocks": [
            {"id": "root", "type": "document", "text": "Root"},
            {"id": "h1", "type": "heading", "text": "Section One"},
            {"id": "p1", "type": "paragraph", "text": "A" * 2600},
            {"id": "h2", "type": "heading", "text": "Section Two"},
            {"id": "p2", "type": "paragraph", "text": "B" * 2600},
        ]
    }

    compiled_rules = {
        "typography": {"line_spacing": "double", "alignment": "justified"},
        "layout": {"heading_numbering": False, "max_heading_depth": 3},
    }
    layout = solve_layout(document_model, compiled_rules)
    corrected = correct_layout_from_render_feedback(
        document_model=document_model,
        compiled_rules=compiled_rules,
        layout_plan=layout,
        render_validation={
            "issues": [
                "PDF page count mismatch: expected 3, got 2",
                "Rendered text similarity below threshold: 74.0",
            ]
        },
    )

    assert corrected["layoutPlan"]["pageCapacityLines"] < layout["pageCapacityLines"]
    assert corrected["preRenderSimulation"]["correctionAttempts"] == 1
    assert corrected["layoutCorrections"][0]["type"] == "render_feedback_correction"


def test_analyze_page_content_type():
    """Verify page content type detection."""
    document_model = {
        "blocks": [
            {"id": "root", "type": "document", "text": "Root"},
            {"id": "h1", "type": "heading", "text": "Heading 1"},
            {"id": "h2", "type": "heading", "text": "Heading 2"},
            {"id": "h3", "type": "heading", "text": "Heading 3"},
            {"id": "p1", "type": "paragraph", "text": "Some text"},
        ]
    }

    layout_plan = {
        "placements": [
            {"page": 1, "blockId": "root"},
            {"page": 1, "blockId": "h1"},
            {"page": 1, "blockId": "h2"},
            {"page": 1, "blockId": "h3"},
            {"page": 1, "blockId": "p1"},
        ]
    }

    # Page 1 has 3 headings + 1 paragraph = 75% headings
    content_type = _analyze_page_content_type(layout_plan, document_model, 1)
    assert content_type == "heading_heavy", f"Expected heading_heavy, got {content_type}"


def test_content_aware_capacity_adjustment_text_heavy():
    """Verify capacity adjustment for text-heavy pages is more aggressive."""
    # Text-heavy scenario: all text pages
    text_heavy_pages = ["text_heavy"] * 3

    # Attempt 1 (feedback-driven)
    cap1, reason1 = _content_aware_capacity_adjustment(48, text_heavy_pages, 1)
    assert cap1 == 45, f"Text-heavy attempt 1 should reduce by ~3, got {cap1}"

    # Attempt 2 (moderate)
    cap2, reason2 = _content_aware_capacity_adjustment(48, text_heavy_pages, 2)
    assert cap2 == 43, f"Text-heavy attempt 2 should reduce by ~5, got {cap2}"


def test_content_aware_capacity_adjustment_heading_heavy():
    """Verify capacity adjustment for heading-heavy pages is less aggressive."""
    # Heading-heavy scenario: mostly headings
    heading_heavy_pages = ["heading_heavy"] * 3

    # Attempt 1 (feedback-driven)
    cap1, reason1 = _content_aware_capacity_adjustment(48, heading_heavy_pages, 1)
    assert cap1 == 47, f"Heading-heavy attempt 1 should reduce by 1, got {cap1}"

    # Attempt 2 (moderate)
    cap2, reason2 = _content_aware_capacity_adjustment(48, heading_heavy_pages, 2)
    assert cap2 == 45, f"Heading-heavy attempt 2 should reduce by 3, got {cap2}"


def test_content_aware_capacity_adjustment_list_heavy():
    """Verify capacity adjustment for list-heavy pages is light."""
    # List-heavy scenario: mostly lists
    list_heavy_pages = ["list_heavy"] * 3

    # Attempt 1 (feedback-driven)
    cap1, reason1 = _content_aware_capacity_adjustment(48, list_heavy_pages, 1)
    assert cap1 == 47, f"List-heavy attempt 1 should reduce by 1, got {cap1}"

    # Attempt 2 (moderate)
    cap2, reason2 = _content_aware_capacity_adjustment(48, list_heavy_pages, 2)
    assert cap2 == 46, f"List-heavy attempt 2 should reduce by 2, got {cap2}"
