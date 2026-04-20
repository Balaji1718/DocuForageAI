from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from .errors import VisualValidationError

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None


@dataclass(frozen=True)
class PageDiffFailure:
    page_number: int
    ssim_score: float
    diff_image_path: str
    reason: str


@dataclass(frozen=True)
class VisualValidationResult:
    passed: bool
    page_count_expected: int
    page_count_actual: int
    average_ssim: float
    failures: list[PageDiffFailure]


class LibreOfficeRenderer:
    """Canonical renderer via pinned Docker image running LibreOffice headless."""

    def __init__(
        self,
        docker_image: str = "docuforage/libreoffice-renderer:7.6.4-fixedfonts",
        soffice_cmd: str = "/usr/bin/soffice",
    ) -> None:
        self.docker_image = docker_image
        self.soffice_cmd = soffice_cmd

    async def render_docx_to_png_pages(self, docx_path: Path, output_dir: Path, dpi: int = 150) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        docx_path = docx_path.resolve()
        output_dir = output_dir.resolve()

        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{docx_path.parent}:/work/input:ro",
            "-v",
            f"{output_dir}:/work/output",
            self.docker_image,
            self.soffice_cmd,
            "--headless",
            "--nologo",
            "--norestore",
            "--convert-to",
            f"png:draw_png_Export:Resolution={dpi}",
            "--outdir",
            "/work/output",
            f"/work/input/{docx_path.name}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise VisualValidationError(
                "LibreOffice render failed",
                failures=[
                    PageDiffFailure(
                        page_number=0,
                        ssim_score=0.0,
                        diff_image_path="",
                        reason=(stderr.decode("utf-8", errors="ignore") or stdout.decode("utf-8", errors="ignore"))[:500],
                    )
                ],
            )

        pages = sorted(output_dir.glob("*.png"))
        if not pages:
            raise VisualValidationError(
                "LibreOffice produced no PNG output",
                failures=[PageDiffFailure(page_number=0, ssim_score=0.0, diff_image_path="", reason="no_png_output")],
            )

        return pages


class BaselineStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _key_dir(self, template_id: str, template_version: str, document_hash: str) -> Path:
        safe = f"{template_id}__{template_version}__{document_hash}"
        return self.root / safe

    def store_baseline(
        self,
        *,
        template_id: str,
        template_version: str,
        document_hash: str,
        page_png_paths: list[Path],
        approved: bool,
        approved_by: str | None = None,
    ) -> Path:
        if not approved:
            raise PermissionError("Baseline storage requires explicit human approval")

        key_dir = self._key_dir(template_id, template_version, document_hash)
        key_dir.mkdir(parents=True, exist_ok=True)

        copied: list[str] = []
        for index, src in enumerate(page_png_paths, start=1):
            dst = key_dir / f"baseline_page_{index:03d}.png"
            Image.open(src).save(dst)
            copied.append(dst.name)

        metadata = {
            "template_id": template_id,
            "template_version": template_version,
            "document_hash": document_hash,
            "approved": True,
            "approved_by": approved_by or "unknown",
            "pages": copied,
        }
        (key_dir / "baseline.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return key_dir

    def load_baseline_pages(self, *, template_id: str, template_version: str, document_hash: str) -> list[Path]:
        key_dir = self._key_dir(template_id, template_version, document_hash)
        metadata_path = key_dir / "baseline.json"
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Baseline not found for {template_id}@{template_version} hash={document_hash}"
            )

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        pages = [key_dir / name for name in metadata.get("pages", [])]
        if not pages:
            raise FileNotFoundError("Baseline metadata exists but page set is empty")
        for page in pages:
            if not page.exists():
                raise FileNotFoundError(f"Missing baseline page: {page}")
        return pages


def _to_grayscale(image_path: Path):
    image = Image.open(image_path).convert("L")
    if np is not None:
        return np.asarray(image, dtype="float32")
    return image


def _mean_absolute_diff(a, b) -> float:
    if np is not None:
        diff = np.abs(a - b)
        return float(np.mean(diff))

    diff_img = ImageChops.difference(a, b)
    hist = diff_img.histogram()
    total = sum(i * count for i, count in enumerate(hist))
    count = max(1, sum(hist))
    return float(total / count)


def _ssim_score(a, b) -> float:
    if np is not None:
        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2

        mu_x = float(np.mean(a))
        mu_y = float(np.mean(b))
        sigma_x = float(np.var(a))
        sigma_y = float(np.var(b))
        sigma_xy = float(np.mean((a - mu_x) * (b - mu_y)))

        numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
        denominator = (mu_x**2 + mu_y**2 + c1) * (sigma_x + sigma_y + c2)
        if denominator == 0:
            return 1.0 if numerator == 0 else 0.0
        return float(max(-1.0, min(1.0, numerator / denominator)))

    # Fallback approximation without numpy.
    mad = _mean_absolute_diff(a, b)
    return max(0.0, 1.0 - (mad / 255.0))


def _build_annotated_diff_image(expected_path: Path, actual_path: Path, out_path: Path, threshold: int = 20) -> Path:
    expected = Image.open(expected_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    if expected.size != actual.size:
        actual = actual.resize(expected.size)

    diff = ImageChops.difference(expected, actual).convert("L")
    mask = diff.point(lambda p: 255 if p >= threshold else 0)

    overlay = Image.new("RGB", expected.size, (255, 0, 0))
    highlighted = Image.composite(overlay, actual, mask)
    blended = Image.blend(actual, highlighted, alpha=0.55)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    blended.save(out_path)
    return out_path


async def validate_visual_output(
    *,
    docx_path: Path,
    template_id: str,
    template_version: str,
    document_hash: str,
    renderer: LibreOfficeRenderer,
    baseline_store: BaselineStore,
    work_dir: Path,
    ssim_threshold: float = 0.97,
    raise_on_failure: bool = True,
) -> VisualValidationResult:
    work_dir.mkdir(parents=True, exist_ok=True)
    actual_dir = work_dir / "actual"
    actual_pages = await renderer.render_docx_to_png_pages(docx_path=docx_path, output_dir=actual_dir, dpi=150)

    try:
        baseline_pages = baseline_store.load_baseline_pages(
            template_id=template_id,
            template_version=template_version,
            document_hash=document_hash,
        )
    except FileNotFoundError as exc:
        failures = [
            PageDiffFailure(
                page_number=0,
                ssim_score=0.0,
                diff_image_path="",
                reason=str(exc),
            )
        ]
        if raise_on_failure:
            raise VisualValidationError("Missing visual baseline", failures=failures)
        return VisualValidationResult(
            passed=False,
            page_count_expected=0,
            page_count_actual=len(actual_pages),
            average_ssim=0.0,
            failures=failures,
        )

    failures: list[PageDiffFailure] = []

    if len(actual_pages) != len(baseline_pages):
        failures.append(
            PageDiffFailure(
                page_number=0,
                ssim_score=0.0,
                diff_image_path="",
                reason=f"page_count_mismatch expected={len(baseline_pages)} actual={len(actual_pages)}",
            )
        )

    compare_count = min(len(actual_pages), len(baseline_pages))
    ssim_scores: list[float] = []

    for idx in range(compare_count):
        expected_page = baseline_pages[idx]
        actual_page = actual_pages[idx]

        expected = _to_grayscale(expected_page)
        actual = _to_grayscale(actual_page)

        if np is not None and expected.shape != actual.shape:
            actual_img = Image.fromarray(actual.astype("uint8"), mode="L")
            actual_img = actual_img.resize((expected.shape[1], expected.shape[0]))
            actual = np.asarray(actual_img, dtype="float32")

        if np is None and expected.size != actual.size:
            actual = actual.resize(expected.size)

        ssim = _ssim_score(expected, actual)
        ssim_scores.append(ssim)

        if ssim < ssim_threshold:
            diff_path = work_dir / "diffs" / f"page_{idx+1:03d}_diff.png"
            _build_annotated_diff_image(expected_page, actual_page, diff_path)
            failures.append(
                PageDiffFailure(
                    page_number=idx + 1,
                    ssim_score=ssim,
                    diff_image_path=str(diff_path),
                    reason=f"ssim_below_threshold threshold={ssim_threshold}",
                )
            )

    average_ssim = float(sum(ssim_scores) / len(ssim_scores)) if ssim_scores else 0.0
    passed = len(failures) == 0
    result = VisualValidationResult(
        passed=passed,
        page_count_expected=len(baseline_pages),
        page_count_actual=len(actual_pages),
        average_ssim=average_ssim,
        failures=failures,
    )

    if not passed and raise_on_failure:
        raise VisualValidationError(
            "Visual validation failed",
            failures=[asdict(item) for item in failures],
        )

    return result
