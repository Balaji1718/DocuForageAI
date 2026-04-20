from __future__ import annotations

import asyncio
import hashlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.errors import DeprecatedTemplateError
from services.generation_v2.fonts import FontCache, FontSizeMetrics
from services.generation_v2.layout_simulator import simulate_layout
from services.generation_v2.models import DocumentSpec
from services.generation_v2.pipeline import generate_document
from services.generation_v2.template_registry import TemplateRegistry
from services.generation_v2.units import pt_to_emu
from services.generation_v2.visual_validation import BaselineStore, validate_visual_output
from services.generation_v2.writer import write_docx_atomic


class DeterministicRenderer:
    def __init__(self, page_count: int = 2) -> None:
        self.page_count = page_count

    async def render_docx_to_png_pages(self, docx_path: Path, output_dir: Path, dpi: int = 150) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(Path(docx_path).read_bytes()).hexdigest()[:16]
        pages = []
        for page_num in range(1, self.page_count + 1):
            img = Image.new("RGB", (900, 1300), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw.text((30, 30), f"{content_hash} :: page {page_num}", fill=(0, 0, 0))
            out = output_dir / f"render_page_{page_num:03d}.png"
            img.save(out)
            pages.append(out)
        return pages


def _font_cache() -> FontCache:
    size = Decimal("11")
    width = Decimal("468")
    return FontCache(
        by_font_size={
            ("Calibri", size): FontSizeMetrics(
                font_name="Calibri",
                size_pt=size,
                ascender=1900,
                descender=-500,
                units_per_em=2048,
                cap_height=1450,
                line_height_ratio=Decimal("1.171875"),
                line_height_pt=Decimal("12.8906"),
                average_advance_width_units=1100,
            )
        },
        chars_per_line_by_key={("Calibri", size, width): 65},
    )


def _registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    reg.register(
        template_id="final",
        version="1.0.0",
        page_layout={
            "size": {"width_in": 8.5, "height_in": 11.0},
            "margins": {"top_in": 1.0, "right_in": 1.0, "bottom_in": 1.0, "left_in": 1.0},
        },
        styles={
            "Normal": {
                "font_name": "Calibri",
                "font_size_pt": 11,
                "line_spacing": 1.15,
                "space_before_pt": 0,
                "space_after_pt": 0,
            },
            "Heading1": {
                "font_name": "Calibri",
                "font_size_pt": 11,
                "line_spacing": 1.15,
                "space_before_pt": 0,
                "space_after_pt": 0,
            },
        },
        header_footer={"header": {"text": "Header"}, "footer": {"text": "Footer"}},
    )
    return reg


def _raw_input_for_integration() -> dict:
    long_text = "lorem ipsum " * 3000
    return {
        "title": "Integration doc",
        "elements": [
            {
                "type": "paragraph",
                "text": "Section 1",
                "style": "Heading1",
                "keep_with_next": True,
                "overflow_strategy": "split",
            },
            {
                "type": "paragraph",
                "text": long_text,
                "style": "Normal",
                "overflow_strategy": "split",
            },
            {
                "type": "table",
                "rows": [
                    {
                        "cells": [
                            {"text": "A1", "width": {"value": 2.0, "unit": "in"}},
                            {"text": "B1", "width": {"value": 2.0, "unit": "in"}},
                            {"text": "C1", "width": {"value": 2.0, "unit": "in"}},
                        ]
                    },
                    {
                        "cells": [
                            {"text": "A2", "width": {"value": 2.0, "unit": "in"}},
                            {"text": "B2", "width": {"value": 2.0, "unit": "in"}},
                            {"text": "C2", "width": {"value": 2.0, "unit": "in"}},
                        ]
                    },
                ],
                "overflow_strategy": "push",
            },
        ],
    }


def test_gate1_validation_error_no_retry(tmp_path: Path):
    reg = _registry()
    renderer = DeterministicRenderer(page_count=1)
    baseline_store = BaselineStore(tmp_path / "base")

    with pytest.raises(ValidationError):
        generate_document(
            raw_input={"elements": []},
            template_id="final",
            template_version="1.0.0",
            user_rules={},
            template_registry=reg,
            output_path=tmp_path / "invalid.docx",
            work_dir=tmp_path / "work",
            fonts_dir=tmp_path / "fonts",
            renderer=renderer,
            baseline_store=baseline_store,
            font_cache=_font_cache(),
        )


def test_gate2_exact_pt_to_emu():
    assert pt_to_emu(12.0) == 152400


def test_gate3_keep_with_next_behavior():
    spec = DocumentSpec.model_validate(
        {
            "title": "kwn",
            "page_layout": {
                "width": {"value": 8.5, "unit": "in"},
                "height": {"value": 11.0, "unit": "in"},
                "margins": {
                    "top": {"value": 1.0, "unit": "in"},
                    "right": {"value": 1.0, "unit": "in"},
                    "bottom": {"value": 1.0, "unit": "in"},
                    "left": {"value": 1.0, "unit": "in"},
                },
            },
            "styles": {
                "Normal": {
                    "font_name": "Calibri",
                    "font_size": {"value": 11, "unit": "pt"},
                    "line_spacing": 1.15,
                },
                "Heading1": {
                    "font_name": "Calibri",
                    "font_size": {"value": 11, "unit": "pt"},
                    "line_spacing": 1.15,
                },
            },
            "elements": [
                {"type": "paragraph", "text": "X" * (65 * 55), "style": "Normal", "overflow_strategy": "split"},
                {
                    "type": "paragraph",
                    "text": "Heading",
                    "style": "Heading1",
                    "keep_with_next": True,
                    "overflow_strategy": "split",
                },
                {"type": "paragraph", "text": "Body" * 30, "style": "Normal", "overflow_strategy": "split"},
            ],
        }
    )

    resolved = {
        "Normal": {
            "font_name": "Calibri",
            "font_size_pt": Decimal("11"),
            "line_spacing": Decimal("1.15"),
            "space_before_pt": Decimal("0"),
            "space_after_pt": Decimal("0"),
        },
        "Heading1": {
            "font_name": "Calibri",
            "font_size_pt": Decimal("11"),
            "line_spacing": Decimal("1.15"),
            "space_before_pt": Decimal("0"),
            "space_after_pt": Decimal("0"),
        },
    }

    annotated = simulate_layout(spec, resolved, _font_cache())
    heading = annotated[1]
    body = annotated[2]
    assert heading["page"] == body["page"]


def test_gate4_deprecated_template_error_hint():
    reg = TemplateRegistry()
    reg.register(
        template_id="x",
        version="1.0.0",
        page_layout={"size": {"width_in": 8.5, "height_in": 11.0}, "margins": {"top_in": 1, "right_in": 1, "bottom_in": 1, "left_in": 1}},
        styles={"Normal": {"font_name": "Calibri", "font_size_pt": 11}},
        header_footer={"header": {"text": "h"}, "footer": {"text": "f"}},
        deprecated=True,
    )
    reg.register(
        template_id="x",
        version="1.1.0",
        page_layout={"size": {"width_in": 8.5, "height_in": 11.0}, "margins": {"top_in": 1, "right_in": 1, "bottom_in": 1, "left_in": 1}},
        styles={"Normal": {"font_name": "Calibri", "font_size_pt": 11}},
        header_footer={"header": {"text": "h"}, "footer": {"text": "f"}},
        deprecated=False,
    )

    with pytest.raises(DeprecatedTemplateError, match="Please migrate to x@1.1.0"):
        reg.get("x", "1.0.0")


def test_gate5_writer_deterministic_hash(tmp_path: Path):
    reg = _registry()
    template = reg.get("final", "1.0.0")
    spec = DocumentSpec.model_validate(
        {
            "title": "hash",
            "page_layout": {
                "width": {"value": 8.5, "unit": "in"},
                "height": {"value": 11.0, "unit": "in"},
                "margins": {
                    "top": {"value": 1.0, "unit": "in"},
                    "right": {"value": 1.0, "unit": "in"},
                    "bottom": {"value": 1.0, "unit": "in"},
                    "left": {"value": 1.0, "unit": "in"},
                },
            },
            "styles": {"Normal": {"font_name": "Calibri", "font_size": {"value": 11, "unit": "pt"}}},
            "elements": [{"type": "paragraph", "text": "same", "style": "Normal"}],
        }
    )

    styles = {"Normal": {"font_name": "Calibri", "font_size_pt": 11, "line_spacing": 1.15, "space_before_pt": 0, "space_after_pt": 0}}
    ann = [{"type": "paragraph", "text": "same", "style": "Normal", "break_before": False}]

    p1 = tmp_path / "a.docx"
    p2 = tmp_path / "b.docx"
    write_docx_atomic(spec=spec, template=template, annotated_elements=ann, resolved_styles=styles, output_path=p1)
    write_docx_atomic(spec=spec, template=template, annotated_elements=ann, resolved_styles=styles, output_path=p2)

    h1 = hashlib.sha256(p1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(p2.read_bytes()).hexdigest()
    assert h1 == h2


def test_gate6_visual_self_ssim_one(tmp_path: Path):
    img = Image.new("RGB", (900, 1300), color=(255, 255, 255))
    p = tmp_path / "p.png"
    img.save(p)

    store = BaselineStore(tmp_path / "base")
    store.store_baseline(
        template_id="t",
        template_version="1.0.0",
        document_hash="h",
        page_png_paths=[p],
        approved=True,
        approved_by="tester",
    )

    doc = tmp_path / "dummy.docx"
    doc.write_bytes(b"x")

    class StaticRenderer:
        async def render_docx_to_png_pages(self, docx_path: Path, output_dir: Path, dpi: int = 150) -> list[Path]:
            output_dir.mkdir(parents=True, exist_ok=True)
            out = output_dir / "render_page_001.png"
            Image.open(p).save(out)
            return [out]

    renderer = StaticRenderer()
    result = asyncio.run(
        validate_visual_output(
            docx_path=doc,
            template_id="t",
            template_version="1.0.0",
            document_hash="h",
            renderer=renderer,
            baseline_store=store,
            work_dir=tmp_path / "work",
            raise_on_failure=False,
        )
    )
    assert result.average_ssim == 1.0


def test_integration_pipeline_end_to_end(tmp_path: Path):
    reg = _registry()
    renderer = DeterministicRenderer(page_count=2)
    store = BaselineStore(tmp_path / "baselines")
    raw_input = _raw_input_for_integration()
    user_rules = {}

    out_path = tmp_path / "integration.docx"

    first = generate_document(
        raw_input=raw_input,
        template_id="final",
        template_version="1.0.0",
        user_rules=user_rules,
        template_registry=reg,
        output_path=out_path,
        work_dir=tmp_path / "run1",
        fonts_dir=tmp_path / "fonts",
        renderer=renderer,
        baseline_store=store,
        font_cache=_font_cache(),
        approve_new_baseline=True,
        approved_by="integration-test",
    )
    assert first.status == "completed"
    assert first.page_count >= 2
    assert first.average_ssim >= 0.97

    second = generate_document(
        raw_input=raw_input,
        template_id="final",
        template_version="1.0.0",
        user_rules=user_rules,
        template_registry=reg,
        output_path=out_path,
        work_dir=tmp_path / "run2",
        fonts_dir=tmp_path / "fonts",
        renderer=renderer,
        baseline_store=store,
        font_cache=_font_cache(),
        approve_new_baseline=False,
    )

    assert second.status == "completed"
    assert second.page_count == first.page_count
    assert second.average_ssim >= 0.97
    assert first.document_hash == second.document_hash
