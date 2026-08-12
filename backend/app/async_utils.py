"""Async utilities for running sync functions in threads."""

import asyncio
import json
import logging
from functools import partial
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Exceptions that are transient and worth retrying
TRANSIENT_EXCEPTIONS = (ConnectionError, OSError, TimeoutError)


async def run_sync(func, *args, **kwargs):
    """Run a synchronous function in a thread to avoid blocking the event loop.

    Use this for all Letta client calls, which are synchronous.
    """
    return await asyncio.get_running_loop().run_in_executor(None, partial(func, *args, **kwargs))


async def retry_letta_call(func, *args, max_retries=3, base_delay=1.0, **kwargs):
    """Call a Letta client method with exponential backoff on transient failures.

    Retries on ConnectionError, OSError, and TimeoutError.
    Does NOT retry on HTTP errors or application-level errors.

    Args:
        func: The sync Letta client method to call.
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Base delay in seconds, doubles each retry (default 1.0).

    Returns:
        The result of the successful call.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await run_sync(func, *args, **kwargs)
        except TRANSIENT_EXCEPTIONS as e:
            last_exc = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Letta call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Letta call failed after %d attempts: %s",
                    max_retries + 1,
                    e,
                )
    raise last_exc


async def stream_letta_response(
    client,
    agent_id: str,
    messages: list[dict],
    include_reasoning: bool = False,
    max_steps: int = 10,
    use_streaming: bool = True,
) -> AsyncGenerator[dict, None]:
    """Stream a Letta agent response with retry logic and chunk parsing.

    Handles:
    - Retry loop (4 attempts, exponential backoff) on transient failures
    - StopIteration wrapper for run_in_executor
    - Chunk parsing for content, reasoning, errors, stop_reason, usage_statistics
    - Proper Stream context manager lifecycle

    Args:
        client: The Letta client instance.
        agent_id: The agent ID to send the message to.
        messages: List of message dicts (e.g., [{"role": "user", "content": "..."}]).
        include_reasoning: Whether reasoning is requested (passed through; callers
            decide filtering at the SSE level).
        max_steps: Maximum number of agent steps.
        use_streaming: Whether to use streaming (default True).

    Yields parsed dicts:
        {"type": "content", "content": str, "message_type": str}
        {"type": "reasoning", "content": str, "message_type": str}
        {"type": "error", "content": str, "error_type": str | None}
        {"type": "status", "status": "completed"}
        {"type": "usage", "steps": int}
        {"type": "stop_reason", "stop_reason": str}
    """
    loop = asyncio.get_running_loop()

    # Wrapper to handle StopIteration (can't be raised through run_in_executor)
    def get_next(it):
        try:
            return next(it)
        except StopIteration:
            return None  # Sentinel for end of stream

    # Retry stream initialization on transient failures
    last_stream_exc = None
    for stream_attempt in range(4):  # 1 initial + 3 retries
        try:
            # Use the Stream as a context manager for proper HTTP connection lifecycle
            stream_ctx = client.agents.messages.stream(
                agent_id=agent_id,
                messages=messages,
                max_steps=max_steps,
                stream_tokens=True,
            )
            # Enter the context manager in the executor to avoid blocking
            stream_obj = await loop.run_in_executor(None, stream_ctx.__enter__)
            break
        except TRANSIENT_EXCEPTIONS as e:
            last_stream_exc = e
            if stream_attempt < 3:
                delay = 1.0 * (2**stream_attempt)
                logger.warning(
                    "Stream init failed (attempt %d/4), retrying in %.1fs: %s",
                    stream_attempt + 1,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise last_stream_exc

    iterator = stream_obj.__iter__()

    try:
        while True:
            chunk = await loop.run_in_executor(None, get_next, iterator)
            if chunk is None:
                break

            # Determine message type
            if hasattr(chunk, "message_type"):
                msg_type = chunk.message_type
            elif hasattr(chunk, "type"):
                msg_type = chunk.type
            else:
                msg_type = "unknown"

            if msg_type == "stop_reason" and hasattr(chunk, "stop_reason"):
                yield {"type": "stop_reason", "stop_reason": str(chunk.stop_reason)}
                continue

            if msg_type == "usage_statistics":
                step_count = getattr(chunk, "step_count", 0) or 0
                yield {"type": "usage", "steps": step_count}
                continue

            if msg_type == "error_message":
                error_content = getattr(chunk, "message", str(chunk))
                error_type = getattr(chunk, "error_type", None)
                yield {"type": "error", "content": error_content, "error_type": error_type}
                continue

            # Skip ping messages
            if msg_type == "ping":
                continue

            content = None
            if hasattr(chunk, "content"):
                content = chunk.content
            elif hasattr(chunk, "reasoning"):
                content = chunk.reasoning

            if content:
                if msg_type == "assistant_message":
                    yield {"type": "content", "content": str(content), "message_type": msg_type}
                elif msg_type == "reasoning_message":
                    yield {"type": "reasoning", "content": str(content), "message_type": msg_type}

        yield {"type": "status", "status": "completed"}
    finally:
        # Always exit the context manager to release the HTTP connection
        try:
            await loop.run_in_executor(None, stream_ctx.__exit__, None, None, None)
        except Exception as e:
            logger.warning("Failed to close stream context: %s", e)


def event_to_sse(event: dict, include_reasoning: bool = True) -> str:
    """Convert a parsed stream event dict to an SSE data line.

    Args:
        event: A dict from stream_letta_response with a "type" key.
        include_reasoning: Whether to include reasoning events (default True).

    Returns:
        An SSE-formatted string like "data: {...}\\n\\n", or empty string
        if the event should be skipped.
    """
    if event["type"] == "content":
        return f"data: {json.dumps({'type': 'content', 'content': event['content'], 'message_type': event['message_type']})}\n\n"
    elif event["type"] == "reasoning":
        if include_reasoning:
            return f"data: {json.dumps({'type': 'content', 'content': event['content'], 'message_type': event['message_type']})}\n\n"
        return ""
    elif event["type"] == "error":
        return f"data: {json.dumps({'type': 'error', 'error': event['content']})}\n\n"
    elif event["type"] == "status":
        return f"data: {json.dumps({'type': 'status', 'status': event['status']})}\n\n"
    elif event["type"] == "usage":
        return f"data: {json.dumps({'type': 'usage', 'steps': event['steps']})}\n\n"
    elif event["type"] == "stop_reason":
        return f"data: {json.dumps({'type': 'stop_reason', 'stop_reason': event['stop_reason']})}\n\n"
    elif event["type"] == "security_event":
        return (
            f"data: {json.dumps({'type': 'security_event', 'event': event['event'], 'message': event['message']})}\n\n"
        )
    return ""


def sse_response(generator) -> StreamingResponse:
    """Create a StreamingResponse with standard SSE headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
