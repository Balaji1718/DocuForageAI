from __future__ import annotations

import re
from typing import Any


def _new_block(block_id: str, kind: str, level: int | None, text: str, parent_id: str | None) -> dict[str, Any]:
    return {
        "id": block_id,
        "type": kind,
        "level": level,
        "text": text,
        "parentId": parent_id,
        "children": [],
    }


def build_document_model(title: str, structured_text: str, compiled_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic block-based DOM-like structure from generated markdown-ish text."""
    lines = structured_text.splitlines()
    blocks: list[dict[str, Any]] = []

    root_id = "root"
    blocks.append(_new_block(root_id, "document", 0, title.strip() or "Untitled", None))

    heading_stack: list[dict[str, Any]] = [blocks[0]]
    paragraph_buffer: list[str] = []
    block_counter = 1

    def _append_block(kind: str, level: int | None, text: str, parent_id: str | None) -> dict[str, Any]:
        nonlocal block_counter
        block_id = f"b{block_counter}"
        block_counter += 1
        block = _new_block(block_id, kind, level, text, parent_id)
        blocks.append(block)
        return block

    def _flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        text = " ".join(paragraph_buffer).strip()
        if text:
            parent = heading_stack[-1]["id"] if heading_stack else root_id
            _append_block("paragraph", None, text, parent)
        paragraph_buffer = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            _flush_paragraph()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        bullet = re.match(r"^[-*•]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        table_sep = "|" in stripped and len([c for c in stripped if c == "|"]) >= 2
        image = re.match(r"^!\[[^\]]*\]\(([^)]+)\)", stripped)

        if heading:
            _flush_paragraph()
            level = len(heading.group(1))
            text = heading.group(2).strip()

            while len(heading_stack) > 1 and int(heading_stack[-1].get("level") or 0) >= level:
                heading_stack.pop()

            parent_id = heading_stack[-1]["id"] if heading_stack else root_id
            node = _append_block("heading", level, text, parent_id)
            heading_stack.append(node)
            continue

        if bullet:
            _flush_paragraph()
            parent_id = heading_stack[-1]["id"] if heading_stack else root_id
            _append_block("list_item", None, bullet.group(1).strip(), parent_id)
            continue

        if ordered:
            _flush_paragraph()
            parent_id = heading_stack[-1]["id"] if heading_stack else root_id
            _append_block("ordered_list_item", None, ordered.group(1).strip(), parent_id)
            continue

        if image:
            _flush_paragraph()
            parent_id = heading_stack[-1]["id"] if heading_stack else root_id
            _append_block("image", None, image.group(1).strip(), parent_id)
            continue

        if table_sep:
            _flush_paragraph()
            parent_id = heading_stack[-1]["id"] if heading_stack else root_id
            _append_block("table_row", None, stripped, parent_id)
            continue

        paragraph_buffer.append(stripped)

    _flush_paragraph()

    # Build children lists deterministically.
    by_id = {block["id"]: block for block in blocks}
    for block in blocks:
        parent_id = block.get("parentId")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(block["id"])

    stats = {
        "totalBlocks": len(blocks),
        "headingCount": len([b for b in blocks if b["type"] == "heading"]),
        "paragraphCount": len([b for b in blocks if b["type"] == "paragraph"]),
        "listItemCount": len([b for b in blocks if b["type"] in {"list_item", "ordered_list_item"}]),
        "tableRowCount": len([b for b in blocks if b["type"] == "table_row"]),
        "imageCount": len([b for b in blocks if b["type"] == "image"]),
    }

    return {
        "version": "1.0",
        "title": title,
        "rootId": root_id,
        "blocks": blocks,
        "stats": stats,
        "constraints": {
            "compiledRules": compiled_rules or {},
        },
    }
