"""Multi-AI fallback: Groq → OpenRouter → Cohere → rule-based formatter."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
import re
from typing import Optional

import requests
from utils.log_events import log_event

log = logging.getLogger("docuforge.ai")

TIMEOUT = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))


def _post_with_retry(url: str, headers: dict, payload: dict) -> Optional[requests.Response]:
    for attempt in range(2):
        try:
            return requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            if attempt == 1:
                log_event(
                    log,
                    logging.WARNING,
                    "provider_request_failed",
                    url=url,
                    retry_attempt=attempt + 1,
                    reason=str(exc),
                )
                return None
            log_event(
                log,
                logging.WARNING,
                "provider_request_retry",
                url=url,
                retry_attempt=attempt + 1,
                reason=str(exc),
            )
    return None


def _status_category(code: int) -> str:
    if code == 429:
        return "rate_limited"
    if 500 <= code <= 599:
        return "provider_server_error"
    if code in {401, 403}:
        return "auth_error"
    if 400 <= code <= 499:
        return "request_error"
    return "unknown"


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
        "If reference-alignment instructions are present, mimic only structure/style, never copy wording. "
        "Use coherent academic flow and, when appropriate, include Introduction, Body, "
        "and Conclusion sections in this chunk without inventing facts. "
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
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": _system_prompt(rules, ci, tc)},
            {"role": "user", "content": _user_prompt(title, content)},
        ],
        "temperature": 0.3,
    }
    r = _post_with_retry(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload=payload,
    )
    if r is None:
        return None
    try:
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log_event(
            log,
            logging.WARNING,
            "provider_response_error",
            provider="groq",
            status=r.status_code,
            category=_status_category(r.status_code),
            details=r.text[:300],
        )
    except Exception as e:  # noqa: BLE001
        log_event(log, logging.WARNING, "provider_parse_error", provider="groq", reason=str(e))
    return None


def _try_openrouter(title: str, rules: str, content: str, ci: int, tc: int) -> Optional[str]:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    payload = {
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "messages": [
            {"role": "system", "content": _system_prompt(rules, ci, tc)},
            {"role": "user", "content": _user_prompt(title, content)},
        ],
        "temperature": 0.3,
    }
    r = _post_with_retry(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://docuforge.ai",
            "X-Title": "DocuForge AI",
        },
        payload=payload,
    )
    if r is None:
        return None
    try:
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log_event(
            log,
            logging.WARNING,
            "provider_response_error",
            provider="openrouter",
            status=r.status_code,
            category=_status_category(r.status_code),
            details=r.text[:300],
        )
    except Exception as e:  # noqa: BLE001
        log_event(log, logging.WARNING, "provider_parse_error", provider="openrouter", reason=str(e))
    return None


def _try_cohere(title: str, rules: str, content: str, ci: int, tc: int) -> Optional[str]:
    key = os.getenv("COHERE_API_KEY")
    if not key:
        return None
    payload = {
        "model": "command-r",
        "preamble": _system_prompt(rules, ci, tc),
        "message": _user_prompt(title, content),
        "temperature": 0.3,
    }
    r = _post_with_retry(
        "https://api.cohere.com/v1/chat",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload=payload,
    )
    if r is None:
        return None
    try:
        if r.status_code == 200:
            data = r.json()
            return (data.get("text") or "").strip() or None
        log_event(
            log,
            logging.WARNING,
            "provider_response_error",
            provider="cohere",
            status=r.status_code,
            category=_status_category(r.status_code),
            details=r.text[:300],
        )
    except Exception as e:  # noqa: BLE001
        log_event(log, logging.WARNING, "provider_parse_error", provider="cohere", reason=str(e))
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


def _quality_score(text: str) -> float:
    lower = text.lower()
    score = 0.0

    for token, pts in (("introduction", 25), ("body", 20), ("conclusion", 25)):
        if token in lower:
            score += pts

    heading_hits = len(re.findall(r"^#{1,3}\s+.+$", text, flags=re.MULTILINE))
    score += min(heading_hits * 4, 20)

    bullet_hits = len(re.findall(r"^\s*[-*]\s+", text, flags=re.MULTILINE))
    score += min(bullet_hits * 1.5, 10)

    # Prefer outputs with meaningful but not excessively verbose size.
    score += min(len(text) / 200, 20)
    if len(text) < 300:
        score -= 20

    return score


def generate_with_collaboration(
    title: str,
    rules: str,
    content: str,
    chunk_index: int = 1,
    total_chunks: int = 1,
) -> str:
    providers = [
        ("groq", _try_groq),
        ("openrouter", _try_openrouter),
        ("cohere", _try_cohere),
    ]

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        future_to_name = {
            pool.submit(fn, title, rules, content, chunk_index, total_chunks): name
            for name, fn in providers
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                value = future.result()
                if value:
                    results[name] = value
                    log_event(log, logging.INFO, "provider_candidate_generated", provider=name)
            except Exception as exc:  # noqa: BLE001
                log_event(
                    log,
                    logging.WARNING,
                    "provider_collaboration_failure",
                    provider=name,
                    reason=str(exc),
                )

    if not results:
        log_event(
            log,
            logging.INFO,
            "provider_collaboration_empty",
            reason="no_provider_output",
            fallback="rule_chain",
        )
        return generate_with_fallback(title, rules, content, chunk_index, total_chunks)

    scored = {name: _quality_score(text) for name, text in results.items()}
    best_name = max(scored, key=scored.get)
    log_event(
        log,
        logging.INFO,
        "provider_selection",
        candidates=sorted(results.keys()),
        selected=best_name,
        score=round(scored[best_name], 2),
    )
    return results[best_name]


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
            log_event(log, logging.INFO, "provider_used", provider=name, mode="fallback_chain")
            return result
    log_event(log, logging.INFO, "rule_based_fallback_used", reason="all_providers_failed_or_unavailable")
    return _rule_based(title, rules, content)
