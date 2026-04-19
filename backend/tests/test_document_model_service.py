from __future__ import annotations

from services.document_model_service import build_document_model


def test_build_document_model_structure() -> None:
    text = (
        "# Introduction\n"
        "Context paragraph line one.\n"
        "Context paragraph line two.\n\n"
        "## Body\n"
        "- First item\n"
        "1. Ordered item\n"
        "| A | B |\n"
        "![](figure.png)\n\n"
        "## Conclusion\n"
        "Final summary paragraph."
    )

    model = build_document_model("Demo", text, compiled_rules={"deterministic": True})

    assert model["version"] == "1.0"
    assert model["rootId"] == "root"
    assert model["stats"]["headingCount"] >= 3
    assert model["stats"]["paragraphCount"] >= 2
    assert model["stats"]["listItemCount"] >= 2
    assert model["stats"]["tableRowCount"] >= 1
    assert model["stats"]["imageCount"] >= 1
