"""Criterion 6: X-API-Key must match AGENT_API_KEY, otherwise 401."""
import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import settings


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    expected = settings.agent_api_key
    if not x_api_key or not expected or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return x_api_key
