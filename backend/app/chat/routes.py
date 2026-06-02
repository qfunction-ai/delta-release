"""Chat routes — direct agent conversation with optional tools/skills."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.prompts import extract_message_parts
from app.agents.run_prep import prepare_chat_run
from app.async_utils import event_to_sse, sse_response, stream_letta_response
from app.auth.dependencies import get_current_user, resolve_agent_user, verify_service_token
from app.auth.models import User
from app.chat.schemas import ChatHistoryMessage, ChatHistoryResponse, ChatRequest, ChatResponse
from app.config import get_settings
from app.constants import LETTA_ERRORS
from app.database import get_db, get_owned_or_404
from app.errors import safe_error
from app.letta_client import call_letta, get_letta_client
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Message type → display role mapping
_ROLE_MAP = {"user_message": "user", "assistant_message": "assistant"}


def _extract_message_content(msg) -> str:
    """Extract text content from a Letta message, handling multi-modal lists."""
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        content = " ".join(part.text if hasattr(part, "text") else str(part) for part in content)
    return content or ""


@router.get("/history/{agent_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch message history for an agent from Letta."""
    # Verify agent belongs to user
    await get_owned_or_404(
        db,
        Agent,
        agent_id,
        current_user.id,
        id_field="letta_agent_id",
    )

    client = get_letta_client()
    letta_messages = await call_letta(
        client.agents.messages.list,
        agent_id=agent_id,
        limit=100,
        order="asc",
        raise_on_error=False,
    )
    if letta_messages is None:
        return ChatHistoryResponse(messages=[])

    # First pass: collect reasoning by step_id so we can attach it
    # to the corresponding assistant_message below.
    reasoning_by_step: dict[str, str] = {}
    for msg in letta_messages:
        msg_type = getattr(msg, "message_type", None)
        if msg_type != "reasoning_message":
            continue
        step_id = getattr(msg, "step_id", None)
        if not step_id:
            continue
        reasoning_text = getattr(msg, "reasoning", "") or ""
        if step_id in reasoning_by_step:
            reasoning_by_step[step_id] += "\n" + reasoning_text
        else:
            reasoning_by_step[step_id] = reasoning_text

    # Second pass: build history, attaching reasoning to assistant messages.
    history = []
    for msg in letta_messages:
        msg_type = getattr(msg, "message_type", None)
        role = _ROLE_MAP.get(msg_type)
        if role is None:
            continue
        content = _extract_message_content(msg)
        # Strip skill prompt prefix from user messages so the user
        # sees their original text, not the injected skill context.
        if role == "user":
            from app.agents.prompts import SKILL_PROMPT_END

            idx = content.find(SKILL_PROMPT_END)
            if idx != -1:
                content = content[idx + len(SKILL_PROMPT_END) :]
        reasoning = None
        if role == "assistant":
            step_id = getattr(msg, "step_id", None)
            if step_id and step_id in reasoning_by_step:
                reasoning = reasoning_by_step[step_id]
        history.append(
            ChatHistoryMessage(
                role=role,
                content=content,
                date=msg.date.isoformat() if getattr(msg, "date", None) else "",
                reasoning=reasoning,
            )
        )

    return ChatHistoryResponse(messages=history)


@router.post("/message", response_model=ChatResponse)
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    chat: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to an agent synchronously."""
    # Verify agent belongs to user
    await get_owned_or_404(
        db,
        Agent,
        chat.agent_id,
        current_user.id,
        id_field="letta_agent_id",
    )

    # Layer 2: scan for secrets in user message (warn only, don't block)
    from shared.code_safety import scan_for_secrets

    secret_warnings = scan_for_secrets(chat.message)

    rendered_message, client = await prepare_chat_run(
        agent_id=chat.agent_id,
        tool_ids=chat.tool_ids or [],
        skill_ids=chat.skill_ids or [],
        user_id=str(current_user.id),
        db=db,
        message=chat.message,
    )

    try:
        response = await call_letta(
            client.agents.messages.create,
            agent_id=chat.agent_id,
            messages=[{"role": "user", "content": rendered_message}],
            max_steps=get_settings().max_steps,
        )
    except LETTA_ERRORS:
        raise  # call_letta already raises HTTPException with safe detail

    # Separate reasoning from assistant response
    assistant_output, reasoning_output = extract_message_parts(
        response.messages, include_reasoning=chat.include_reasoning
    )

    return ChatResponse(
        output=assistant_output,
        reasoning_output=reasoning_output,
        secret_warnings=secret_warnings or None,
    )


@router.post("/stream")
@limiter.limit("10/minute")
async def stream_message(
    request: Request,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to an agent with SSE streaming."""

    async def event_generator():
        # Verify agent belongs to user
        try:
            await get_owned_or_404(
                db,
                Agent,
                req.agent_id,
                current_user.id,
                id_field="letta_agent_id",
            )
        except HTTPException:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Agent not found'})}\n\n"
            return

        # Layer 2: scan for secrets in user message (warn only, don't block)
        from shared.code_safety import scan_for_secrets as _scan_for_secrets

        secret_warnings = _scan_for_secrets(req.message)
        if secret_warnings:
            yield f"data: {json.dumps({'type': 'secret_warning', 'warnings': secret_warnings})}\n\n"

        rendered_message, client = await prepare_chat_run(
            agent_id=req.agent_id,
            tool_ids=req.tool_ids or [],
            skill_ids=req.skill_ids or [],
            user_id=str(current_user.id),
            db=db,
            message=req.message,
        )

        # Commit the DB transaction before streaming starts.
        # prepare_chat_run may INSERT rows (e.g., user_settings) or UPDATE
        # rows (e.g., lesson times_used). If we don't commit before the
        # stream, the transaction stays open for the entire duration of the
        # agent response (which can be 30+ seconds for multi-step runs).
        # Concurrent requests that touch the same tables will block on the
        # uncommitted transaction's locks.
        await db.commit()

        yield f"data: {json.dumps({'type': 'status', 'status': 'running'})}\n\n"

        try:
            event_count = 0
            async for event in stream_letta_response(
                client,
                req.agent_id,
                [{"role": "user", "content": rendered_message}],
                include_reasoning=req.include_reasoning,
                max_steps=get_settings().max_steps,
            ):
                event_count += 1
                sse_line = event_to_sse(event, include_reasoning=req.include_reasoning)
                if sse_line:
                    yield sse_line
            logger.info("stream_message: stream completed, %d events", event_count)

        except LETTA_ERRORS as e:
            logger.error("stream_message: letta error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error(str(e), 'letta')})}\n\n"
        except Exception as e:
            logger.error("stream_message: unexpected error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Internal streaming error'})}\n\n"

    return sse_response(event_generator())


@router.post("/eval", response_model=ChatResponse)
async def eval_chat(
    request: Request,
    chat: ChatRequest,
    _auth=Depends(verify_service_token),
    db: AsyncSession = Depends(get_db),
):
    """Service-to-service chat for the eval container.

    Goes through the full Delta middleware stack (settings check, tool
    attachment, skill insertion) so evals test the actual system behavior,
    not just the raw agent.

    Requires X-Service-Token header for authentication.
    Only works for agents whose owners have eval_enabled=True in settings.
    """
    agent = await resolve_agent_user(request, chat.agent_id, db)

    # Authorization: only allow eval access if the user has opted in
    from app.settings.service import get_or_create_settings

    user_settings = await get_or_create_settings(str(agent.user_id), db)
    if not user_settings.eval_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Eval access denied: user has not enabled eval for their agents",
        )

    rendered_message, client = await prepare_chat_run(
        agent_id=chat.agent_id,
        tool_ids=chat.tool_ids or [],
        skill_ids=chat.skill_ids or [],
        user_id=str(agent.user_id),
        db=db,
        message=chat.message,
    )

    try:
        response = await call_letta(
            client.agents.messages.create,
            agent_id=chat.agent_id,
            messages=[{"role": "user", "content": rendered_message}],
            max_steps=get_settings().max_steps,
        )
    except LETTA_ERRORS:
        raise  # call_letta already raises HTTPException with safe detail

    assistant_output, reasoning_output = extract_message_parts(
        response.messages, include_reasoning=chat.include_reasoning
    )

    return ChatResponse(
        output=assistant_output,
        reasoning_output=reasoning_output,
    )
