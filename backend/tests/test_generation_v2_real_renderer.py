from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from docx import Document

from services.generation_v2.visual_validation import BaselineStore, LibreOfficeRenderer, validate_visual_output

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_REAL_RENDER_TESTS") != "1",
    reason="Set RUN_REAL_RENDER_TESTS=1 to run Docker+LibreOffice integration tests.",
)
def test_real_docker_renderer_self_compare_ssim_one(tmp_path: Path):
    fixture_docx = tmp_path / "fixture.docx"

    doc = Document()
    doc.add_paragraph("Real renderer fixture document")
    doc.save(fixture_docx)

    renderer = LibreOfficeRenderer(
        docker_image=os.getenv("LO_RENDERER_IMAGE", "docuforage-lo-renderer:test"),
    )
    baseline_store = BaselineStore(tmp_path / "baselines")

    first_pages = asyncio.run(
        renderer.render_docx_to_png_pages(
            docx_path=fixture_docx,
            output_dir=tmp_path / "baseline_pages",
            dpi=150,
        )
    )

    baseline_store.store_baseline(
        template_id="real-render",
        template_version="1.0.0",
        document_hash="fixture-hash",
        page_png_paths=first_pages,
        approved=True,
        approved_by="ci-real-render",
    )

    result = asyncio.run(
        validate_visual_output(
            docx_path=fixture_docx,
            template_id="real-render",
            template_version="1.0.0",
            document_hash="fixture-hash",
            renderer=renderer,
            baseline_store=baseline_store,
            work_dir=tmp_path / "validation",
            ssim_threshold=1.0,
            raise_on_failure=False,
        )
    )

    assert result.passed is True
    assert result.average_ssim == 1.0
