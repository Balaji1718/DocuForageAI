from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .constants import CM_PER_INCH, EMU_PER_INCH, MM_PER_INCH, PT_PER_INCH


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_emu(value: float | int | str | Decimal, unit: str) -> int:
    amount = to_decimal(value)
    normalized = unit.strip().lower()
    if normalized == "emu":
        return int(amount.to_integral_value(rounding=ROUND_HALF_UP))
    if normalized == "pt":
        inches = amount / PT_PER_INCH
    elif normalized == "in":
        inches = amount
    elif normalized == "cm":
        inches = amount / CM_PER_INCH
    elif normalized == "mm":
        inches = amount / MM_PER_INCH
    else:
        raise ValueError(f"Unsupported measurement unit: {unit}")
    emu = inches * EMU_PER_INCH
    return int(emu.to_integral_value(rounding=ROUND_HALF_UP))


def pt_to_emu(value: float | int | str | Decimal) -> int:
    return to_emu(value, "pt")


def emu_to_pt(value_emu: int) -> Decimal:
    emu = Decimal(value_emu)
    inches = emu / EMU_PER_INCH
    return (inches * PT_PER_INCH).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
