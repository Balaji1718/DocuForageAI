from __future__ import annotations

import re


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:120]


def chunk_text(text: str, size: int = 8000) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
