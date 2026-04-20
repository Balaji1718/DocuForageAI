from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .errors import LayoutOverflowError
from .fonts import FontCache
from .models import DocumentSpec, ParagraphElement, TableElement
from .units import emu_to_pt


@dataclass(frozen=True)
class SimulationConfig:
    page_height_pt: Decimal
    usable_page_height_pt: Decimal
    column_width_pt: Decimal


def _to_decimal(value: int | float | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _paragraph_height_pt(
    paragraph: ParagraphElement,
    style: dict[str, Any],
    font_cache: FontCache,
    column_width_pt: Decimal,
) -> tuple[Decimal, int, Decimal]:
    font_name = str(style.get("font_name"))
    font_size_pt = _to_decimal(style.get("font_size_pt"))

    chars_per_line = font_cache.get_chars_per_line(font_name, font_size_pt, column_width_pt)
    line_count = max(1, math.ceil(len(paragraph.text) / max(1, chars_per_line)))

    metrics = font_cache.get(font_name, font_size_pt)
    line_height_pt = Decimal(str(metrics.line_height_pt))

    line_spacing = _to_decimal(style.get("line_spacing", "1.0"))
    space_before_pt = _to_decimal(style.get("space_before_pt", "0"))
    space_after_pt = _to_decimal(style.get("space_after_pt", "0"))

    paragraph_height = (Decimal(line_count) * line_height_pt * line_spacing) + space_before_pt + space_after_pt
    return paragraph_height, line_count, line_height_pt


def _table_height_pt(
    table: TableElement,
    style: dict[str, Any],
    font_cache: FontCache,
    column_width_pt: Decimal,
) -> tuple[Decimal, list[Decimal]]:
    row_heights: list[Decimal] = []
    for row in table.rows:
        max_height = Decimal("0")
        for cell in row.cells:
            fake_paragraph = ParagraphElement(
                text=cell.text,
                style=style.get("paragraph_style", "Normal"),
                keep_with_next=False,
                force_page_break_before=False,
                overflow_strategy="split",
            )
            cell_height, _, _ = _paragraph_height_pt(fake_paragraph, style, font_cache, column_width_pt)
            if cell_height > max_height:
                max_height = cell_height
        row_heights.append(max_height)
    return sum(row_heights, Decimal("0")), row_heights


def _simulate_overflow_split(text: str, chars_per_line: int, lines_that_fit: int) -> tuple[str, str]:
    allowed_chars = max(1, chars_per_line * max(1, lines_that_fit))
    if len(text) <= allowed_chars:
        return text, ""

    breakpoint = text.rfind(" ", 0, allowed_chars)
    if breakpoint <= 0:
        breakpoint = allowed_chars
    head = text[:breakpoint].rstrip()
    tail = text[breakpoint:].lstrip()
    return head, tail


def _apply_overflow_strategy(
    element: dict[str, Any],
    available_pt: Decimal,
    config: SimulationConfig,
    style: dict[str, Any],
    font_cache: FontCache,
) -> list[dict[str, Any]]:
    strategy = str(element.get("overflow_strategy", "split"))
    if strategy not in {"split", "push", "truncate"}:
        raise LayoutOverflowError(f"Unsupported overflow strategy: {strategy}")

    if element["type"] != "paragraph":
        if strategy == "push":
            element["insert_page_break_before"] = True
            return [element]
        raise LayoutOverflowError("Only paragraph overflow strategies are currently supported")

    text = str(element.get("text", ""))
    font_name = str(style.get("font_name"))
    font_size_pt = _to_decimal(style.get("font_size_pt"))
    chars_per_line = font_cache.get_chars_per_line(font_name, font_size_pt, config.column_width_pt)
    metrics = font_cache.get(font_name, font_size_pt)
    line_height_pt = Decimal(str(metrics.line_height_pt)) * _to_decimal(style.get("line_spacing", "1.0"))
    lines_that_fit = max(1, int(available_pt // max(Decimal("0.0001"), line_height_pt)))

    if strategy == "split":
        head, tail = _simulate_overflow_split(text, chars_per_line, lines_that_fit)
        first = {**element, "text": head, "split_part": "head"}
        second = {**element, "text": tail, "split_part": "tail", "insert_page_break_before": True}
        return [first] + ([second] if tail else [])

    if strategy == "push":
        return [{**element, "insert_page_break_before": True}]

    clipped_chars = max(1, chars_per_line * lines_that_fit)
    clipped = text[: max(1, clipped_chars - 1)].rstrip() + "…"
    truncated = {**element, "text": clipped, "truncated": True}
    return [truncated]


def _usable_page_height_pt(spec: DocumentSpec) -> Decimal:
    page_height_pt = emu_to_pt(spec.page_layout.height.as_emu())
    top_margin = emu_to_pt(spec.page_layout.margins.top.as_emu())
    bottom_margin = emu_to_pt(spec.page_layout.margins.bottom.as_emu())
    return page_height_pt - top_margin - bottom_margin


def _column_width_pt(spec: DocumentSpec) -> Decimal:
    page_width_pt = emu_to_pt(spec.page_layout.width.as_emu())
    left_margin = emu_to_pt(spec.page_layout.margins.left.as_emu())
    right_margin = emu_to_pt(spec.page_layout.margins.right.as_emu())
    return page_width_pt - left_margin - right_margin


def simulate_layout(
    spec: DocumentSpec,
    resolved_styles: dict[str, dict[str, Any]],
    font_cache: FontCache,
) -> list[dict[str, Any]]:
    usable_height = _usable_page_height_pt(spec)
    page_height = emu_to_pt(spec.page_layout.height.as_emu())
    column_width = _column_width_pt(spec)

    config = SimulationConfig(
        page_height_pt=page_height,
        usable_page_height_pt=usable_height,
        column_width_pt=column_width,
    )

    pending_elements: list[dict[str, Any]] = []
    for index, element in enumerate(spec.elements):
        payload = element.model_dump()
        payload["original_index"] = index
        pending_elements.append(payload)

    annotated: list[dict[str, Any]] = []
    cursor = Decimal("0")
    page_number = 1
    i = 0

    while i < len(pending_elements):
        element = pending_elements[i]
        element_type = str(element["type"])

        style_name = str(element.get("style") or "Normal")
        style = resolved_styles.get(style_name)
        if style is None:
            style = resolved_styles.get("Normal")
        if style is None:
            raise LayoutOverflowError(f"Missing resolved style: {style_name}")

        if element_type == "paragraph":
            paragraph = ParagraphElement.model_validate(element)
            estimated_height, line_count, line_height_pt = _paragraph_height_pt(paragraph, style, font_cache, column_width)
            estimation_meta = {
                "line_count": line_count,
                "line_height_pt": float(line_height_pt),
            }
        elif element_type == "table":
            table = TableElement.model_validate(element)
            estimated_height, row_heights = _table_height_pt(table, style, font_cache, column_width)
            estimation_meta = {
                "row_heights_pt": [float(v) for v in row_heights],
            }
        else:
            estimated_height = Decimal("12")
            estimation_meta = {}

        keep_with_next = bool(element.get("keep_with_next", False)) and i + 1 < len(pending_elements)
        keep_bundle_height = estimated_height

        if keep_with_next:
            next_element = pending_elements[i + 1]
            next_style_name = str(next_element.get("style") or "Normal")
            next_style = resolved_styles.get(next_style_name) or resolved_styles.get("Normal")
            if next_style is None:
                raise LayoutOverflowError(f"Missing resolved style for keep_with_next: {next_style_name}")
            if next_element["type"] == "paragraph":
                next_height, _, _ = _paragraph_height_pt(ParagraphElement.model_validate(next_element), next_style, font_cache, column_width)
            elif next_element["type"] == "table":
                next_height, _ = _table_height_pt(TableElement.model_validate(next_element), next_style, font_cache, column_width)
            else:
                next_height = Decimal("12")
            keep_bundle_height += next_height

        force_page_break_before = bool(element.get("force_page_break_before", False)) or bool(element.get("insert_page_break_before", False))
        break_before = force_page_break_before

        if not break_before:
            if keep_with_next and (cursor + keep_bundle_height > usable_height):
                break_before = True
            elif cursor + estimated_height > usable_height:
                break_before = True

        if break_before:
            page_number += 1
            cursor = Decimal("0")

        if estimated_height > usable_height:
            strategy = str(element.get("overflow_strategy", "split"))
            if strategy == "push":
                if cursor > 0:
                    page_number += 1
                    cursor = Decimal("0")
                annotated_element = {
                    **element,
                    "insert_page_break_before": True,
                    "page": page_number,
                    "estimated_height_pt": float(estimated_height),
                    "break_before": True,
                    "overflowed": True,
                    "estimation": estimation_meta,
                }
                annotated.append(annotated_element)
                cursor = usable_height
                i += 1
                continue

            available = max(Decimal("1"), usable_height - cursor)
            replacement = _apply_overflow_strategy(element, available, config, style, font_cache)
            pending_elements = pending_elements[:i] + replacement + pending_elements[i + 1 :]
            continue

        annotated_element = {
            **element,
            "page": page_number,
            "estimated_height_pt": float(estimated_height),
            "break_before": bool(break_before),
            "estimation": estimation_meta,
        }
        annotated.append(annotated_element)
        cursor += estimated_height
        i += 1

    return annotated
