"""Pip sidecar package management — HTTP client for the pip-sidecar service."""

import logging
import os

import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.constants import DEFAULT_PIPSIDECAR_URL, PIPSIDECAR_INSTALL_TIMEOUT

logger = logging.getLogger(__name__)

PIPSIDECAR_URL = os.environ.get("DELTA_PIPSIDECAR_URL", DEFAULT_PIPSIDECAR_URL)


async def sidecar_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an authenticated HTTP request to the pip sidecar."""
    settings = get_settings()
    headers = kwargs.pop("headers", {})
    if settings.service_token:
        headers["X-Service-Token"] = settings.service_token
    try:
        async with httpx.AsyncClient(timeout=PIPSIDECAR_INSTALL_TIMEOUT) as client:
            response = await client.request(method, f"{PIPSIDECAR_URL}{path}", headers=headers, **kwargs)
            return response
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Package manager service is not available",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Package manager service timed out",
        )
