from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth

log = logging.getLogger("docuforge.auth")


def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = fb_auth.verify_id_token(token)
        return decoded
    except Exception as exc:  # pragma: no cover
        log.warning("Token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token")
