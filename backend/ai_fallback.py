"""Multi-AI fallback: Groq → OpenRouter → Cohere → rule-based formatter."""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

log = logging.getLogger("docuforge.ai")

TIMEOUT = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))


def _system_prompt(rules: str, chunk_index: int, total_chunks: int) -> str:
    chunk_note = (
        f"This is chunk {chunk_index} of {total_chunks}; format only this part consistently."
        if total_chunks > 1
        else ""
    )
    return (
        "You are DocuForge AI, an academic document compiler. "
        "Transform the user's raw content into a well-structured academic report section "
        "following the formatting rules. Use clear hierarchical headings prefixed with "
        "'# ', '## ', '### ' (Markdown style). Use blank lines between paragraphs. "
        "Do not invent facts. Preserve the user's information.\n\n"
        f"FORMATTING RULES:\n{rules or '(none provided — use standard academic structure)'}\n\n"
        f"{chunk_note}"
    ).strip()


def _user_prompt(title: str, content: str) -> str:
    return f"TITLE: {title}\n\nCONTENT:\n{content}\n\nProduce the structured section now."


def _try_groq(title: str, rules: str, content: str, ci: int, tc: int) -> Optional[str]:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": _system_prompt(rules, ci, tc)},
                    {"role": "user", "content": _user_prompt(title, content)},
                ],
                "temperature": 0.3,
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log.warning("Groq returned %s: %s", r.status_code, r.text[:300])
    except Exception as e:  # noqa: BLE001
        log.warning("Groq error: %s", e)
    return None


def _try_openrouter(title: str, rules: str, content: str, ci: int, tc: int) -> Optional[str]:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://docuforge.ai",
                "X-Title": "DocuForge AI",
            },
            json={
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [
                    {"role": "system", "content": _system_prompt(rules, ci, tc)},
                    {"role": "user", "content": _user_prompt(title, content)},
                ],
                "temperature": 0.3,
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log.warning("OpenRouter returned %s: %s", r.status_code, r.text[:300])
    except Exception as e:  # noqa: BLE001
        log.warning("OpenRouter error: %s", e)
    return None


def _try_cohere(title: str, rules: str, content: str, ci: int, tc: int) -> Optional[str]:
    key = os.getenv("COHERE_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.cohere.com/v1/chat",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "command-r",
                "preamble": _system_prompt(rules, ci, tc),
                "message": _user_prompt(title, content),
                "temperature": 0.3,
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            return (data.get("text") or "").strip() or None
        log.warning("Cohere returned %s: %s", r.status_code, r.text[:300])
    except Exception as e:  # noqa: BLE001
        log.warning("Cohere error: %s", e)
    return None


def _rule_based(title: str, rules: str, content: str) -> str:
    """Deterministic fallback: detect headings, paragraphs, and list items."""
    lines = [ln.rstrip() for ln in content.splitlines()]
    out: list[str] = [f"# {title}", ""]
    if rules.strip():
        out += ["## Formatting Notes", rules.strip(), ""]

    out.append("## Introduction")
    out.append(
        "This report has been compiled by DocuForge AI from the supplied source material. "
        "The sections below preserve the original information while applying a consistent academic structure."
    )
    out.append("")
    out.append("## Body")

    paragraph: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if paragraph:
                out.append(" ".join(paragraph))
                out.append("")
                paragraph = []
            continue
        # Heading-ish?
        if re.match(r"^(#{1,3}\s+)", stripped) or (len(stripped) < 80 and stripped.endswith(":")):
            if paragraph:
                out.append(" ".join(paragraph))
                out.append("")
                paragraph = []
            head = stripped.rstrip(":")
            if not head.startswith("#"):
                head = "### " + head
            out.append(head)
            out.append("")
        elif re.match(r"^[-*•]\s+", stripped):
            if paragraph:
                out.append(" ".join(paragraph))
                out.append("")
                paragraph = []
            out.append("- " + re.sub(r"^[-*•]\s+", "", stripped))
        else:
            paragraph.append(stripped)
    if paragraph:
        out.append(" ".join(paragraph))
        out.append("")

    out.append("## Conclusion")
    out.append("The above content has been organized according to the provided formatting rules.")
    return "\n".join(out)


def generate_with_fallback(
    title: str,
    rules: str,
    content: str,
    chunk_index: int = 1,
    total_chunks: int = 1,
) -> str:
    for fn, name in (
        (_try_groq, "groq"),
        (_try_openrouter, "openrouter"),
        (_try_cohere, "cohere"),
    ):
        result = fn(title, rules, content, chunk_index, total_chunks)
        if result:
            log.info("AI provider used: %s", name)
            return result
    log.info("All AI providers failed/unavailable; using rule-based formatter.")
    return _rule_based(title, rules, content)
