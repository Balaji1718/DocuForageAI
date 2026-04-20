from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.visual_validation import BaselineStore, validate_visual_output


class FakeRenderer:
    def __init__(self, pages: list[Path]) -> None:
        self.pages = pages

    async def render_docx_to_png_pages(self, docx_path: Path, output_dir: Path, dpi: int = 150) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        output = []
        for idx, page in enumerate(self.pages, start=1):
            dst = output_dir / f"render_page_{idx:03d}.png"
            Image.open(page).save(dst)
            output.append(dst)
        return output


def _mk_page(path: Path, text: str, text_offset: tuple[int, int] = (20, 20)) -> Path:
    img = Image.new("RGB", (900, 1300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text(text_offset, text, fill=(20, 20, 20))
    img.save(path)
    return path


def _mk_page_with_block(path: Path, text: str, text_offset: tuple[int, int] = (20, 20)) -> Path:
    img = Image.new("RGB", (900, 1300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text(text_offset, text, fill=(20, 20, 20))
    draw.rectangle([(80, 300), (820, 980)], fill=(0, 0, 0))
    img.save(path)
    return path


def test_document_against_itself_ssim_one(tmp_path: Path):
    baseline_dir = tmp_path / "baselines"
    store = BaselineStore(baseline_dir)

    page1 = _mk_page(tmp_path / "page1.png", "Identical Document")

    store.store_baseline(
        template_id="tpl",
        template_version="1.0.0",
        document_hash="abc",
        page_png_paths=[page1],
        approved=True,
        approved_by="tester",
    )

    renderer = FakeRenderer([page1])
    result = asyncio.run(
        validate_visual_output(
            docx_path=tmp_path / "dummy.docx",
            template_id="tpl",
            template_version="1.0.0",
            document_hash="abc",
            renderer=renderer,
            baseline_store=store,
            work_dir=tmp_path / "work1",
            raise_on_failure=False,
        )
    )

    assert result.passed is True
    assert result.average_ssim == 1.0


def test_changed_font_like_shift_produces_low_ssim_and_diff_image(tmp_path: Path):
    baseline_dir = tmp_path / "baselines"
    store = BaselineStore(baseline_dir)

    baseline = _mk_page(tmp_path / "baseline.png", "Font Style A", text_offset=(20, 20))
    changed = _mk_page_with_block(tmp_path / "changed.png", "Font Style A", text_offset=(120, 80))

    store.store_baseline(
        template_id="tpl",
        template_version="2.0.0",
        document_hash="xyz",
        page_png_paths=[baseline],
        approved=True,
        approved_by="tester",
    )

    renderer = FakeRenderer([changed])
    result = asyncio.run(
        validate_visual_output(
            docx_path=tmp_path / "dummy.docx",
            template_id="tpl",
            template_version="2.0.0",
            document_hash="xyz",
            renderer=renderer,
            baseline_store=store,
            work_dir=tmp_path / "work2",
            raise_on_failure=False,
        )
    )

    assert result.passed is False
    assert result.failures
    assert result.failures[0].ssim_score < 0.97

    diff_path = Path(result.failures[0].diff_image_path)
    assert diff_path.exists()
    assert diff_path.stat().st_size > 0


def test_page_count_change_detected_as_failure(tmp_path: Path):
    baseline_dir = tmp_path / "baselines"
    store = BaselineStore(baseline_dir)

    baseline = _mk_page(tmp_path / "base.png", "Single Page")
    current1 = _mk_page(tmp_path / "current1.png", "Single Page")
    current2 = _mk_page(tmp_path / "current2.png", "Additional Page")

    store.store_baseline(
        template_id="tpl",
        template_version="3.0.0",
        document_hash="pages",
        page_png_paths=[baseline],
        approved=True,
        approved_by="tester",
    )

    renderer = FakeRenderer([current1, current2])
    result = asyncio.run(
        validate_visual_output(
            docx_path=tmp_path / "dummy.docx",
            template_id="tpl",
            template_version="3.0.0",
            document_hash="pages",
            renderer=renderer,
            baseline_store=store,
            work_dir=tmp_path / "work3",
            raise_on_failure=False,
        )
    )

    assert result.passed is False
    reasons = [f.reason for f in result.failures]
    assert any("page_count_mismatch" in r for r in reasons)
