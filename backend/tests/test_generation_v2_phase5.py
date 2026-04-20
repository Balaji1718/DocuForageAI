from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.models import DocumentSpec
from services.generation_v2.template_registry import TemplateRegistry
from services.generation_v2.writer import write_docx_atomic


def _spec() -> DocumentSpec:
    return DocumentSpec.model_validate(
        {
            "title": "Writer Test",
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
                }
            },
            "elements": [
                {"type": "paragraph", "text": "Heading", "style": "Normal", "overflow_strategy": "split"}
            ],
        }
    )


def _template():
    reg = TemplateRegistry()
    return reg.register(
        template_id="writer",
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
            }
        },
        header_footer={"header": {"text": "Header"}, "footer": {"text": "Footer"}},
    )


def _styles() -> dict:
    return {
        "Normal": {
            "font_name": "Calibri",
            "font_size_pt": 11,
            "line_spacing": 1.15,
            "space_before_pt": 0,
            "space_after_pt": 0,
        }
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_two_runs_identical_output_hash(tmp_path: Path):
    spec = _spec()
    template = _template()
    annotated = [
        {"type": "paragraph", "text": "Hello deterministic", "style": "Normal", "break_before": False}
    ]

    file1 = tmp_path / "out1.docx"
    file2 = tmp_path / "out2.docx"

    write_docx_atomic(spec=spec, template=template, annotated_elements=annotated, resolved_styles=_styles(), output_path=file1)
    write_docx_atomic(spec=spec, template=template, annotated_elements=annotated, resolved_styles=_styles(), output_path=file2)

    assert _sha256(file1) == _sha256(file2)


def test_exception_mid_write_keeps_original_file_intact(monkeypatch, tmp_path: Path):
    spec = _spec()
    template = _template()
    annotated = [{"type": "paragraph", "text": "original", "style": "Normal", "break_before": False}]
    out = tmp_path / "stable.docx"

    write_docx_atomic(spec=spec, template=template, annotated_elements=annotated, resolved_styles=_styles(), output_path=out)
    before_hash = _sha256(out)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("services.generation_v2.writer._build_document_from_annotated", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        write_docx_atomic(spec=spec, template=template, annotated_elements=annotated, resolved_styles=_styles(), output_path=out)

    after_hash = _sha256(out)
    assert before_hash == after_hash


def test_three_column_table_has_fixed_layout_and_explicit_widths(tmp_path: Path):
    spec = _spec()
    template = _template()
    table_element = {
        "type": "table",
        "rows": [
            {
                "cells": [
                    {"text": "A", "width": {"value": 2.0, "unit": "in"}},
                    {"text": "B", "width": {"value": 2.0, "unit": "in"}},
                    {"text": "C", "width": {"value": 2.0, "unit": "in"}},
                ]
            },
            {
                "cells": [
                    {"text": "D", "width": {"value": 2.0, "unit": "in"}},
                    {"text": "E", "width": {"value": 2.0, "unit": "in"}},
                    {"text": "F", "width": {"value": 2.0, "unit": "in"}},
                ]
            },
        ],
        "break_before": False,
    }

    out = tmp_path / "table.docx"
    write_docx_atomic(spec=spec, template=template, annotated_elements=[table_element], resolved_styles=_styles(), output_path=out)

    with zipfile.ZipFile(out, "r") as zf:
        xml_content = zf.read("word/document.xml")

    root = ET.fromstring(xml_content)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    layouts = root.findall(".//w:tblLayout", ns)
    assert layouts
    layout_types = [n.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type") for n in layouts]
    assert "fixed" in layout_types

    tcw_nodes = root.findall(".//w:tcW", ns)
    assert tcw_nodes
    width_values = {n.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}w") for n in tcw_nodes}
    # 2.0in == 2880 twips.
    assert "2880" in width_values

    valign_nodes = root.findall(".//w:vAlign", ns)
    assert valign_nodes
    v_values = {n.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") for n in valign_nodes}
    assert "top" in v_values
