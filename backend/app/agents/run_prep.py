"""Run preparation helpers — shared logic for workflow and chat execution."""

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.archival_memory import (
    ensure_archival_memory_search,
    insert_lessons_into_archival_memory,
    insert_skills_into_archival_memory,
)
from app.agents.lessons import get_lessons_for_workflow
from app.agents.prompts import build_lesson_prompt_prefix, build_skill_inline_block, build_skill_prompt_prefix
from app.agents.skills import get_skill_tool_ids, get_skills_by_ids
from app.agents.tools import attach_tools_to_agent, ensure_fetch_docs, ensure_propose_tool, ensure_web_search
from app.constants import RUN_PENDING, RUN_RUNNING
from app.workflows.models import Workflow, WorkflowRun


async def _fetch_skill_files(skill_ids: list[str], db) -> dict[str, list[tuple[str, str]]]:
    """Fetch text-based skill files for the given skill IDs.

    Returns a dict mapping skill_id -> list of (path, content_text) tuples.
    Only includes text files — binary files are useless to LLMs.
    """
    from sqlalchemy import select

    from app.skills.models import SkillFile

    result = {}
    for sid in skill_ids:
        file_result = await db.execute(
            select(SkillFile.path, SkillFile.content_text)
            .where(SkillFile.skill_id == sid, SkillFile.content_text.isnot(None))
            .order_by(SkillFile.path)
        )
        rows = file_result.all()
        if rows:
            result[sid] = [(row[0], row[1]) for row in rows]
    return result


async def inject_skill_context(prompt: str, skills, db) -> str:
    """Prepend skill prompt prefix and inline content to a prompt/message.

    Shared by workflow creation, workflow updates, workflow run prep,
    and chat run prep. Returns the prompt with skill context prepended.
    """
    if not skills:
        return prompt
    skill_files = await _fetch_skill_files([str(s.id) for s in skills], db)
    return build_skill_prompt_prefix([s.name for s in skills]) + build_skill_inline_block(skills, skill_files) + prompt


async def prepare_prompt_context(
    workflow: Workflow,
    agent_id: str,
    prompt: str,
    client,
    db: AsyncSession,
) -> str:
    """Insert skills and lessons into archival memory, prepend prompt prefixes.

    Shared by both the route handler (via prepare_workflow_run) and the
    scheduler (execute_scheduled_workflow). Returns the prompt with
    skill/lesson prefixes prepended.

    Side effects:
    - Inserts skill and lesson passages into the agent's archival memory
    - Attaches archival_memory_search tool if needed
    - Increments lesson.times_used for each loaded lesson
    - Calls db.flush() to persist times_used changes
    """
    # Insert skills into archival memory AND inject content inline
    skill_ids = workflow.skill_ids_list or []
    if skill_ids:
        skills = await get_skills_by_ids(skill_ids, str(workflow.user_id), db)
        if skills:
            # Still insert into archival memory for future reference
            await ensure_archival_memory_search(client, agent_id)
            await insert_skills_into_archival_memory(agent_id, skills, client, db=db)
            # Fetch skill files and inject everything directly into the prompt
            prompt = await inject_skill_context(prompt, skills, db)

    # Insert lessons from past runs into archival memory
    lessons = await get_lessons_for_workflow(str(workflow.id), db)
    if lessons:
        await ensure_archival_memory_search(client, agent_id)
        inserted_lessons = await insert_lessons_into_archival_memory(agent_id, lessons, client)
        if inserted_lessons:
            prompt = build_lesson_prompt_prefix(len(inserted_lessons)) + prompt
            # Track usage
            for lesson in lessons:
                lesson.times_used += 1
            await db.flush()

    return prompt


async def prepare_workflow_run(
    workflow: Workflow,
    variables: dict,
    user_id: str,
    db: AsyncSession,
) -> tuple[str, WorkflowRun, object]:
    """Shared preparation for sync and streaming workflow execution.

    Handles: render prompt, insert skills, insert lessons, create run record,
    attach tools, set status to running.

    Returns: (rendered_prompt, run_record, letta_client)
    """
    from app.letta_client import get_letta_client
    from app.workflows.template import render_template

    rendered_prompt = render_template(workflow.prompt_template, variables)

    # Insert skills/lessons into archival memory
    client = get_letta_client()
    rendered_prompt = await prepare_prompt_context(workflow, workflow.agent_id, rendered_prompt, client, db)

    run = WorkflowRun(
        workflow_id=workflow.id,
        status=RUN_PENDING,
        input_variables=json.dumps(variables),
        rendered_prompt=rendered_prompt,
    )
    db.add(run)
    await db.flush()

    # Attach tools if specified (including skill-linked tools)
    tool_ids = workflow.tool_ids_list or []
    skill_ids = workflow.skill_ids_list or []
    skill_tool_ids: list[str] = []
    if skill_ids:
        skill_tool_ids = await get_skill_tool_ids(skill_ids, db)
    all_tool_ids = list(dict.fromkeys(tool_ids + skill_tool_ids))
    if all_tool_ids:
        await attach_tools_to_agent(client, workflow.agent_id, all_tool_ids, user_id, db)

    # Attach propose_tool if setting is enabled
    await ensure_propose_tool(client, workflow.agent_id, user_id, db)

    # Attach web_search if setting is enabled
    await ensure_web_search(client, workflow.agent_id, user_id, db)

    # Attach fetch_docs if setting is enabled
    await ensure_fetch_docs(client, workflow.agent_id, user_id, db)

    # Mark as running
    run.status = RUN_RUNNING
    run.started_at = datetime.now(timezone.utc)
    await db.flush()

    return rendered_prompt, run, client


async def prepare_chat_run(
    agent_id: str,
    tool_ids: list[str],
    skill_ids: list[str],
    user_id: str,
    db: AsyncSession,
    message: str,
) -> tuple[str, object]:
    """Shared preparation for sync and streaming chat execution.

    Handles: attach tools, attach propose_tool, insert skills into
    archival memory, prepend skill prompt prefix.

    Returns: (rendered_message, letta_client)
    """
    from app.letta_client import get_letta_client

    client = get_letta_client()
    rendered_message = message

    # Look up skill-linked tools and merge with user-selected tools
    skills = None
    skill_tool_ids: list[str] = []
    if skill_ids:
        skills = await get_skills_by_ids(skill_ids, user_id, db)
        if skills:
            skill_tool_ids = await get_skill_tool_ids([str(s.id) for s in skills], db)

    # Merge user-selected + skill-linked tools (dedup, preserve order)
    all_tool_ids = list(dict.fromkeys(tool_ids + skill_tool_ids))

    # Attach tools
    if all_tool_ids:
        await attach_tools_to_agent(client, agent_id, all_tool_ids, user_id, db)

    # Attach propose_tool if setting is enabled
    tool_status_note = await ensure_propose_tool(client, agent_id, user_id, db)
    if tool_status_note:
        rendered_message = tool_status_note + rendered_message

    # Attach web_search if setting is enabled
    web_status_note = await ensure_web_search(client, agent_id, user_id, db)
    if web_status_note:
        rendered_message = web_status_note + rendered_message

    # Attach fetch_docs if setting is enabled
    docs_status_note = await ensure_fetch_docs(client, agent_id, user_id, db)
    if docs_status_note:
        rendered_message = docs_status_note + rendered_message

    # Insert skills into archival memory AND inject content inline
    if skills:
        # Still insert into archival memory for future reference
        await ensure_archival_memory_search(client, agent_id)
        await insert_skills_into_archival_memory(agent_id, skills, client, db=db)
        # Fetch skill files and inject everything directly into the message
        rendered_message = await inject_skill_context(rendered_message, skills, db)

    return rendered_message, client
