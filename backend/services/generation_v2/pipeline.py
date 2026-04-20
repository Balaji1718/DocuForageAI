from __future__ import annotations

import asyncio
import copy
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import LayoutOverflowError, VisualValidationError
from .fonts import FontCache, FontSizeMetrics, build_font_cache
from .layout_simulator import simulate_layout
from .models import DocumentSpec
from .rules import RuleProperty, resolve_rules
from .template_registry import TemplateRegistry, check_registry_backend_health
from .visual_validation import BaselineStore, LibreOfficeRenderer, validate_visual_output
from .writer import write_docx_atomic


check_registry_backend_health()


@dataclass(frozen=True)
class GenerationResult:
    status: str
    output_path: str | None
    document_hash: str | None
    page_count: int
    average_ssim: float
    failures: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None
    annotated_elements: list[dict[str, Any]] = field(default_factory=list)


_FONT_CACHE_SINGLETON: FontCache | None = None


def _dict_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _template_to_page_layout(template_page_layout: dict[str, Any]) -> dict[str, Any]:
    size = template_page_layout.get("size") or {}
    margins = template_page_layout.get("margins") or {}
    return {
        "width": {"value": float(size.get("width_in", 8.5)), "unit": "in"},
        "height": {"value": float(size.get("height_in", 11.0)), "unit": "in"},
        "margins": {
            "top": {"value": float(margins.get("top_in", 1.0)), "unit": "in"},
            "right": {"value": float(margins.get("right_in", 1.0)), "unit": "in"},
            "bottom": {"value": float(margins.get("bottom_in", 1.0)), "unit": "in"},
            "left": {"value": float(margins.get("left_in", 1.0)), "unit": "in"},
        },
    }


def _template_to_styles(template_styles: dict[str, Any]) -> dict[str, Any]:
    styles: dict[str, Any] = {}
    for style_name, props in template_styles.items():
        style_payload: dict[str, Any] = {
            "font_name": str(props.get("font_name", "Calibri")),
            "font_size": {"value": float(props.get("font_size_pt", 11)), "unit": "pt"},
            "line_spacing": float(props.get("line_spacing", 1.15)),
            "keep_with_next": bool(props.get("keep_with_next", False)),
            "force_page_break_before": bool(props.get("force_page_break_before", False)),
        }
        space_before = float(props.get("space_before_pt", 0.0))
        space_after = float(props.get("space_after_pt", 0.0))
        if space_before > 0:
            style_payload["space_before"] = {"value": space_before, "unit": "pt"}
        if space_after > 0:
            style_payload["space_after"] = {"value": space_after, "unit": "pt"}

        styles[style_name] = style_payload
    return styles


def _build_document_payload(raw_input: dict[str, Any], template) -> dict[str, Any]:
    return {
        "title": raw_input.get("title"),
        "page_layout": raw_input.get("page_layout") or _template_to_page_layout(template.page_layout),
        "styles": raw_input.get("styles") or _template_to_styles(template.styles),
        "header": {
            "text": str((template.header_footer.get("header") or {}).get("text") or ""),
            "style": str((template.header_footer.get("header") or {}).get("style") or "Normal"),
        },
        "footer": {
            "text": str((template.header_footer.get("footer") or {}).get("text") or ""),
            "style": str((template.header_footer.get("footer") or {}).get("style") or "Normal"),
        },
        "elements": raw_input.get("elements"),
    }


def _resolve_styles(spec: DocumentSpec, user_rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults = {
        "font_name": "Calibri",
        "font_size_pt": 11.0,
        "line_spacing": 1.15,
        "space_before_pt": 0.0,
        "space_after_pt": 0.0,
        "keep_with_next": False,
        "force_page_break_before": False,
    }

    user_style_rules = (user_rules.get("styles") or {}) if isinstance(user_rules, dict) else {}
    resolved: dict[str, dict[str, Any]] = {}

    for style_name, style_spec in spec.styles.items():
        template_values = {
            "font_name": style_spec.font_name,
            "font_size_pt": style_spec.font_size.value,
            "line_spacing": style_spec.line_spacing,
            "space_before_pt": style_spec.space_before.value if style_spec.space_before else 0.0,
            "space_after_pt": style_spec.space_after.value if style_spec.space_after else 0.0,
            "keep_with_next": style_spec.keep_with_next,
            "force_page_break_before": style_spec.force_page_break_before,
        }

        per_prop: list[RuleProperty] = []
        for key, value in defaults.items():
            per_prop.append(RuleProperty(key, value, priority=0, source="system_default"))
        for key, value in template_values.items():
            per_prop.append(RuleProperty(key, value, priority=1, source=f"template:{style_name}"))

        overrides = user_style_rules.get(style_name) or {}
        for key, value in overrides.items():
            per_prop.append(RuleProperty(key, value, priority=2, source=f"user:{style_name}"))

        merged = resolve_rules(per_prop)
        resolved[style_name] = {
            "font_name": str(merged["font_name"]),
            "font_size_pt": Decimal(str(merged["font_size_pt"])),
            "line_spacing": Decimal(str(merged["line_spacing"])),
            "space_before_pt": Decimal(str(merged["space_before_pt"])),
            "space_after_pt": Decimal(str(merged["space_after_pt"])),
            "keep_with_next": bool(merged["keep_with_next"]),
            "force_page_break_before": bool(merged["force_page_break_before"]),
        }

    return resolved


def _column_width_pt(spec: DocumentSpec) -> Decimal:
    page_width_pt = Decimal(str(spec.page_layout.width.as_emu())) / Decimal("12700")
    left_margin_pt = Decimal(str(spec.page_layout.margins.left.as_emu())) / Decimal("12700")
    right_margin_pt = Decimal(str(spec.page_layout.margins.right.as_emu())) / Decimal("12700")
    return (page_width_pt - left_margin_pt - right_margin_pt).quantize(Decimal("0.0001"))


def _build_runtime_font_cache(spec: DocumentSpec, resolved_styles: dict[str, dict[str, Any]], fonts_dir: Path) -> FontCache:
    global _FONT_CACHE_SINGLETON
    if _FONT_CACHE_SINGLETON is not None:
        return _FONT_CACHE_SINGLETON

    sizes = sorted({v["font_size_pt"] for v in resolved_styles.values()})
    col_width = _column_width_pt(spec)

    bootstrap_cache = build_font_cache(
        fonts_dir=fonts_dir,
        sizes_pt=[Decimal(str(v)) for v in sizes],
        chars_per_line_calibration={},
    )

    calibration: dict[tuple[str, Decimal, Decimal], int] = {}
    for style in resolved_styles.values():
        font_name = style["font_name"]
        size_pt = Decimal(str(style["font_size_pt"])).normalize()
        metrics = bootstrap_cache.get(font_name, size_pt)
        avg_char_width_pt = max(Decimal("0.0001"), metrics.average_char_width_pt)
        chars_per_line = max(10, int(col_width / avg_char_width_pt))
        calibration[(font_name, size_pt, col_width.normalize())] = chars_per_line

    _FONT_CACHE_SINGLETON = build_font_cache(
        fonts_dir=fonts_dir,
        sizes_pt=[Decimal(str(v)) for v in sizes],
        chars_per_line_calibration=calibration,
    )
    return _FONT_CACHE_SINGLETON


def _retry_input_with_overflow_handler(raw_input: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(raw_input)
    for element in updated.get("elements", []):
        if isinstance(element, dict) and element.get("type") == "paragraph":
            element["overflow_strategy"] = "truncate"
    return updated


def _run_once(
    *,
    raw_input: dict[str, Any],
    template_id: str,
    template_version: str,
    user_rules: dict[str, Any],
    template_registry: TemplateRegistry,
    output_path: Path,
    work_dir: Path,
    fonts_dir: Path,
    renderer: LibreOfficeRenderer,
    baseline_store: BaselineStore,
    font_cache: FontCache | None,
    approve_new_baseline: bool,
    approved_by: str,
) -> GenerationResult:
    # (1) Pydantic validation
    template = template_registry.get(template_id, template_version)
    payload = _build_document_payload(raw_input, template)
    spec = DocumentSpec.model_validate(payload)

    # (2) Rule resolution
    resolved_styles = _resolve_styles(spec, user_rules)

    # (3) Layout simulation
    runtime_cache = font_cache or _build_runtime_font_cache(spec, resolved_styles, fonts_dir)
    annotated_elements = simulate_layout(spec, resolved_styles, runtime_cache)

    # (4) Atomic write
    write_result = write_docx_atomic(
        spec=spec,
        template=template,
        annotated_elements=annotated_elements,
        resolved_styles=resolved_styles,
        output_path=output_path,
    )
    document_hash = _dict_sha256(write_result.output_path)

    # (5) Visual validation
    if approve_new_baseline:
        pages = asyncio.run(renderer.render_docx_to_png_pages(write_result.output_path, work_dir / "bootstrap_pages", dpi=150))
        baseline_store.store_baseline(
            template_id=template_id,
            template_version=template_version,
            document_hash=document_hash,
            page_png_paths=pages,
            approved=True,
            approved_by=approved_by,
        )

    visual_result = asyncio.run(
        validate_visual_output(
            docx_path=write_result.output_path,
            template_id=template_id,
            template_version=template_version,
            document_hash=document_hash,
            renderer=renderer,
            baseline_store=baseline_store,
            work_dir=work_dir / "validation",
            ssim_threshold=0.97,
            raise_on_failure=True,
        )
    )

    # (6) Return result
    page_count = max((int(item.get("page", 1)) for item in annotated_elements), default=1)
    return GenerationResult(
        status="completed",
        output_path=str(write_result.output_path),
        document_hash=document_hash,
        page_count=page_count,
        average_ssim=visual_result.average_ssim,
        failures=[],
        message="ok",
        annotated_elements=annotated_elements,
    )


def generate_document(
    raw_input: dict[str, Any],
    template_id: str,
    template_version: str,
    user_rules: dict[str, Any],
    *,
    template_registry: TemplateRegistry,
    output_path: Path,
    work_dir: Path,
    fonts_dir: Path,
    renderer: LibreOfficeRenderer | None = None,
    baseline_store: BaselineStore | None = None,
    font_cache: FontCache | None = None,
    approve_new_baseline: bool = False,
    approved_by: str = "unknown",
) -> GenerationResult:
    renderer = renderer or LibreOfficeRenderer()
    baseline_store = baseline_store or BaselineStore(work_dir / "baselines")

    try:
        return _run_once(
            raw_input=raw_input,
            template_id=template_id,
            template_version=template_version,
            user_rules=user_rules,
            template_registry=template_registry,
            output_path=output_path,
            work_dir=work_dir,
            fonts_dir=fonts_dir,
            renderer=renderer,
            baseline_store=baseline_store,
            font_cache=font_cache,
            approve_new_baseline=approve_new_baseline,
            approved_by=approved_by,
        )
    except ValidationError:
        # Error contract: ValidationError = no retry.
        raise
    except LayoutOverflowError:
        # Error contract: LayoutOverflowError = overflow handler + retry once.
        retried_input = _retry_input_with_overflow_handler(raw_input)
        return _run_once(
            raw_input=retried_input,
            template_id=template_id,
            template_version=template_version,
            user_rules=user_rules,
            template_registry=template_registry,
            output_path=output_path,
            work_dir=work_dir,
            fonts_dir=fonts_dir,
            renderer=renderer,
            baseline_store=baseline_store,
            font_cache=font_cache,
            approve_new_baseline=approve_new_baseline,
            approved_by=approved_by,
        )
    except VisualValidationError as exc:
        # Error contract: VisualValidationError = return failure result, never swallow silently.
        return GenerationResult(
            status="failed",
            output_path=str(output_path) if output_path else None,
            document_hash=None,
            page_count=0,
            average_ssim=0.0,
            failures=exc.failures if isinstance(exc.failures, list) else [],
            message=str(exc),
            annotated_elements=[],
        )
