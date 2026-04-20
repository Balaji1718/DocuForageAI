from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .units import to_emu

MeasurementUnit = Literal["pt", "cm", "mm", "in", "emu"]
OverflowStrategy = Literal["split", "push", "truncate"]


class Measurement(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(..., gt=0)
    unit: MeasurementUnit

    @field_validator("value")
    @classmethod
    def _finite_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Measurement value must be > 0")
        return value

    def as_emu(self) -> int:
        return to_emu(self.value, self.unit)


class MarginSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    top: Measurement
    right: Measurement
    bottom: Measurement
    left: Measurement


class PageLayout(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: Measurement
    height: Measurement
    margins: MarginSpec

    @model_validator(mode="after")
    def _validate_usable_area(self) -> "PageLayout":
        usable_width = self.width.as_emu() - (self.margins.left.as_emu() + self.margins.right.as_emu())
        usable_height = self.height.as_emu() - (self.margins.top.as_emu() + self.margins.bottom.as_emu())
        if usable_width <= 0 or usable_height <= 0:
            raise ValueError("Page usable area must be positive after margins")
        return self


class StyleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    font_name: str = Field(..., min_length=1)
    font_size: Measurement
    line_spacing: float = Field(default=1.15, gt=0)
    space_before: Measurement | None = None
    space_after: Measurement | None = None
    keep_with_next: bool = False
    force_page_break_before: bool = False

    @model_validator(mode="after")
    def _validate_break_conflict(self) -> "StyleSpec":
        if self.keep_with_next and self.force_page_break_before:
            raise ValueError("Style conflict: keep_with_next and force_page_break_before cannot both be true")
        if self.font_size.unit != "pt":
            raise ValueError("font_size must be expressed in points")
        return self


class HeaderFooterSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(default="")
    style: str = Field(default="Normal", min_length=1)


class ParagraphElement(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["paragraph"] = "paragraph"
    text: str = Field(..., min_length=1)
    style: str = Field(default="Normal", min_length=1)
    keep_with_next: bool = False
    force_page_break_before: bool = False
    overflow_strategy: OverflowStrategy = "split"

    @model_validator(mode="after")
    def _validate_flags(self) -> "ParagraphElement":
        if self.keep_with_next and self.force_page_break_before:
            raise ValueError("Paragraph conflict: keep_with_next and force_page_break_before cannot both be true")
        return self


class TableCell(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(..., min_length=1)
    width: Measurement


class TableRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    cells: list[TableCell] = Field(..., min_length=1)


class TableElement(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["table"] = "table"
    rows: list[TableRow] = Field(..., min_length=1)
    overflow_strategy: OverflowStrategy = "push"

    @model_validator(mode="after")
    def _consistent_columns(self) -> "TableElement":
        expected = len(self.rows[0].cells)
        for idx, row in enumerate(self.rows[1:], start=1):
            if len(row.cells) != expected:
                raise ValueError(f"All table rows must have the same number of cells; row {idx} differs")
        return self


class ImageElement(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["image"] = "image"
    source_path: str = Field(..., min_length=1)
    width: Measurement
    height: Measurement
    alt_text: str = Field(default="")
    overflow_strategy: OverflowStrategy = "push"


DocumentElement = ParagraphElement | TableElement | ImageElement


class DocumentSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(..., min_length=1)
    page_layout: PageLayout
    styles: dict[str, StyleSpec] = Field(default_factory=dict)
    header: HeaderFooterSpec = Field(default_factory=HeaderFooterSpec)
    footer: HeaderFooterSpec = Field(default_factory=HeaderFooterSpec)
    elements: list[DocumentElement] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_styles_present(self) -> "DocumentSpec":
        for index, element in enumerate(self.elements):
            if isinstance(element, ParagraphElement) and element.style not in self.styles:
                raise ValueError(f"Element {index} references unknown style '{element.style}'")
        return self


def validate_document_spec(payload: dict) -> DocumentSpec:
    return DocumentSpec.model_validate(payload)


def assert_invalid(payload: dict) -> None:
    try:
        DocumentSpec.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("Expected ValidationError but payload validated successfully")
