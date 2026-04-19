from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=True, default=str))
