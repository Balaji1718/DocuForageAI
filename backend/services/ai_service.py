from __future__ import annotations

import logging

from ai_fallback import generate_with_fallback
from utils.helpers import chunk_text

log = logging.getLogger("docuforge.ai.service")


def generate_structured_text(
    title: str,
    rules: str,
    content: str,
    chunk_size: int = 8000,
    retries: int = 1,
) -> str:
    chunks = chunk_text(content, chunk_size)
    sections: list[str] = []

    for idx, chunk in enumerate(chunks, start=1):
        for attempt in range(retries + 1):
            try:
                section = generate_with_fallback(
                    title=title,
                    rules=rules,
                    content=chunk,
                    chunk_index=idx,
                    total_chunks=len(chunks),
                )
                sections.append(section)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= retries:
                    log.exception("AI generation failed after retry for chunk %s: %s", idx, exc)
                    raise
                log.warning(
                    "AI generation failed for chunk %s (attempt %s/%s): %s",
                    idx,
                    attempt + 1,
                    retries + 1,
                    exc,
                )

    return "\n\n".join(sections)
