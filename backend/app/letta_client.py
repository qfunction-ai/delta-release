import logging
from functools import lru_cache

from fastapi import HTTPException, status
from letta_client import BadRequestError, Letta

from app.async_utils import run_sync
from app.config import get_settings
from app.constants import LETTA_ERRORS
from app.errors import letta_error_detail

logger = logging.getLogger(__name__)

# Letta agent calls can take several minutes (multi-step reasoning,
# tool calls, embedding lookups). The SDK default read timeout of 60s
# is too aggressive — agent runs routinely exceed that.
_LETTA_TIMEOUT = 300  # 5 minutes

# Timeout for HTTP proxy requests to the Letta container (audit log
# queries, file reads, policy reads). Shorter than the SDK timeout
# because these are simple REST calls, not agent runs.
LETTA_PROXY_TIMEOUT = 30.0


def letta_base_url() -> str:
    """Get the Letta base URL for direct HTTP calls.

    Use this for httpx-based proxy requests. The SDK client
    gets its URL from get_letta_client() instead.
    """
    return get_settings().letta_base_url


@lru_cache
def get_letta_client() -> Letta:
    """Get a singleton Letta client.

    The client is created once and cached for the process lifetime.
    This means the base_url and timeout are fixed at first call — if
    the Letta URL changes (e.g., container restart), the process must
    be restarted to pick up the new URL. This is intentional: the
    client is used across hundreds of requests and recreating it per
    request would add unnecessary overhead.
    """
    settings = get_settings()
    return Letta(
        base_url=settings.letta_base_url,
        timeout=_LETTA_TIMEOUT,
    )


async def call_letta(func, *args, raise_on_error: bool = True, **kwargs):
    """Call a Letta client method with standard error handling.

    Wraps run_sync() with error handling. The caller should pass a bound
    method from a Letta client instance (e.g., client.agents.messages.create).

    Args:
        func: A bound Letta client method.
        *args: Positional arguments for the method.
        raise_on_error: If True (default), raises HTTPException on failure.
            If False, returns None on failure and logs the error. Use this for
            non-fatal operations like attaching tools or inserting passages.
        **kwargs: Keyword arguments for the method.

    Returns:
        The result of the successful call, or None if raise_on_error=False
        and the call failed.

    Raises:
        HTTPException(400): On BadRequestError (user-actionable validation).
        HTTPException(503): On other Letta failures when raise_on_error=True.
    """
    try:
        return await run_sync(func, *args, **kwargs)
    except LETTA_ERRORS as e:
        if raise_on_error:
            # 400 errors are validation errors the user can fix
            if isinstance(e, BadRequestError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=letta_error_detail(e),
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=letta_error_detail(e),
            )
        logger.debug("Letta call failed (non-fatal): %s", e)
        return None
