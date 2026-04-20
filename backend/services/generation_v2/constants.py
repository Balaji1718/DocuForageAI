from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

EMU_PER_INCH = Decimal("914400")
PT_PER_INCH = Decimal("72")
MM_PER_INCH = Decimal("25.4")
CM_PER_INCH = Decimal("2.54")

PRIORITY_SYSTEM = 0
PRIORITY_TEMPLATE = 1
PRIORITY_USER = 2

FIXED_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
