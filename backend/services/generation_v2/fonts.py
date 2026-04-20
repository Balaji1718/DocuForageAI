from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from fontTools.ttLib import TTFont


_FONT_CACHE_POPULATED: dict[str, int] = {}
FONT_CACHE = MappingProxyType(_FONT_CACHE_POPULATED)


@dataclass(frozen=True)
class FontFaceMetrics:
    font_name: str
    ascender: int
    descender: int
    units_per_em: int
    cap_height: int
    line_height_ratio: Decimal
    average_advance_width_units: int


@dataclass(frozen=True)
class FontSizeMetrics:
    font_name: str
    size_pt: Decimal
    ascender: int
    descender: int
    units_per_em: int
    cap_height: int
    line_height_ratio: Decimal
    line_height_pt: Decimal
    average_advance_width_units: int

    @property
    def average_char_width_pt(self) -> Decimal:
        return (
            Decimal(self.average_advance_width_units)
            / Decimal(self.units_per_em)
            * self.size_pt
        ).quantize(Decimal("0.0001"))


@dataclass(frozen=True)
class FontCache:
    by_font_size: Mapping[tuple[str, Decimal], FontSizeMetrics]
    chars_per_line_by_key: Mapping[tuple[str, Decimal, Decimal], int]

    def get(self, font_name: str, size_pt: float | int | Decimal | str) -> FontSizeMetrics:
        key = (font_name, Decimal(str(size_pt)).normalize())
        if key not in self.by_font_size:
            raise KeyError(f"Font metrics not found for {font_name} at {size_pt}pt")
        return self.by_font_size[key]

    def get_chars_per_line(
        self,
        font_name: str,
        size_pt: float | int | Decimal | str,
        column_width_pt: float | int | Decimal | str,
    ) -> int:
        normalized_size = Decimal(str(size_pt)).normalize()
        normalized_width = Decimal(str(column_width_pt)).normalize()
        key = (
            font_name,
            normalized_size,
            normalized_width,
        )
        if key in self.chars_per_line_by_key:
            return int(self.chars_per_line_by_key[key])

        # Use nearest calibrated width for same font+size when exact width key is unavailable.
        candidates = [
            (width, value)
            for (f_name, f_size, width), value in self.chars_per_line_by_key.items()
            if f_name == font_name and f_size == normalized_size
        ]
        if not candidates:
            raise KeyError(
                "Chars-per-line calibration not found for "
                f"font={font_name}, size={size_pt}pt, width={column_width_pt}pt"
            )

        nearest_width, nearest_value = min(candidates, key=lambda item: abs(item[0] - normalized_width))
        _ = nearest_width  # explicit for readability in trace/debugging
        return int(nearest_value)


def _iter_font_files(fonts_dir: Path) -> list[Path]:
    if not fonts_dir.exists() or not fonts_dir.is_dir():
        return []
    files = [
        path
        for path in fonts_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    ]
    return sorted(files)


def _load_font_face(font_path: Path) -> FontFaceMetrics:
    with TTFont(font_path) as font:
        hhea = font["hhea"]
        head = font["head"]
        os2 = font.get("OS/2")
        name_table = font["name"]

        font_name = font_path.stem
        for record in name_table.names:
            if record.nameID == 4:
                try:
                    font_name = str(record.toUnicode()).strip() or font_name
                    break
                except Exception:  # noqa: BLE001
                    continue

        ascender = int(hhea.ascent)
        descender = int(hhea.descent)
        units_per_em = int(head.unitsPerEm)

        if units_per_em <= 0:
            raise ValueError(f"Invalid units_per_em in font {font_path}")

        if os2 is not None and hasattr(os2, "sCapHeight") and int(getattr(os2, "sCapHeight") or 0) > 0:
            cap_height = int(os2.sCapHeight)
        else:
            cap_height = max(1, int(Decimal(ascender) * Decimal("0.7")))

        hmtx = font["hmtx"]
        cmap = font.getBestCmap() or {}
        sample_text = "ETAOINSHRDLUetaoinshrdlu0123456789 .,;:-_()[]{}"
        advance_widths: list[int] = []
        for ch in sample_text:
            glyph_name = cmap.get(ord(ch))
            if not glyph_name:
                continue
            advance, _lsb = hmtx[glyph_name]
            if int(advance) > 0:
                advance_widths.append(int(advance))

        if not advance_widths:
            default_glyph = ".notdef" if ".notdef" in hmtx else next(iter(hmtx.keys()))
            default_advance, _lsb = hmtx[default_glyph]
            average_advance_width_units = max(1, int(default_advance))
        else:
            average_advance_width_units = max(1, int(round(sum(advance_widths) / len(advance_widths))))

        line_height_ratio = (Decimal(ascender) - Decimal(descender)) / Decimal(units_per_em)

        return FontFaceMetrics(
            font_name=font_name,
            ascender=ascender,
            descender=descender,
            units_per_em=units_per_em,
            cap_height=cap_height,
            line_height_ratio=line_height_ratio,
            average_advance_width_units=average_advance_width_units,
        )


def build_font_cache(
    fonts_dir: Path,
    sizes_pt: list[float | int | Decimal | str],
    chars_per_line_calibration: dict[tuple[str, float | int | Decimal | str, float | int | Decimal | str], int] | None = None,
) -> FontCache:
    normalized_sizes = [Decimal(str(size)).normalize() for size in sizes_pt]
    if not normalized_sizes:
        raise ValueError("sizes_pt must contain at least one size")

    cache: dict[tuple[str, Decimal], FontSizeMetrics] = {}
    for font_file in _iter_font_files(fonts_dir):
        face = _load_font_face(font_file)
        for size_pt in normalized_sizes:
            line_height_pt = (face.line_height_ratio * size_pt).quantize(Decimal("0.0001"))
            entry = FontSizeMetrics(
                font_name=face.font_name,
                size_pt=size_pt,
                ascender=face.ascender,
                descender=face.descender,
                units_per_em=face.units_per_em,
                cap_height=face.cap_height,
                line_height_ratio=face.line_height_ratio,
                line_height_pt=line_height_pt,
                average_advance_width_units=face.average_advance_width_units,
            )
            cache[(face.font_name, size_pt)] = entry

    calibration_raw = chars_per_line_calibration or {}
    calibration: dict[tuple[str, Decimal, Decimal], int] = {}
    for (font_name, size_pt, column_width_pt), chars_per_line in calibration_raw.items():
        if int(chars_per_line) <= 0:
            raise ValueError("chars_per_line calibration values must be > 0")
        calibration[(font_name, Decimal(str(size_pt)).normalize(), Decimal(str(column_width_pt)).normalize())] = int(chars_per_line)

    return FontCache(
        by_font_size=MappingProxyType(cache),
        chars_per_line_by_key=MappingProxyType(calibration),
    )
