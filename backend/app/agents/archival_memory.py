"""Archival memory helpers — dedup, skill/lesson insertion, search tool attachment."""

import logging

from sqlalchemy import select

from app.letta_client import call_letta

logger = logging.getLogger(__name__)


async def _passage_tags_exist(client, agent_id: str, tags: list[str]) -> bool:
    """Check if an archival memory passage with the given tags already exists.

    Uses tag-based search to avoid inserting duplicate skills/lessons
    into archival memory on repeated executions.
    """
    result = await call_letta(
        client.agents.passages.search,
        agent_id=agent_id,
        query=tags[-1] if tags else "",
        tags=tags,
        tag_match_mode="all",
        top_k=1,
        raise_on_error=False,
    )
    if result is None:
        # If we can't check, proceed with insert (fail open)
        return False
    # PassageSearchResponse has .results list; fall back to list for test mocks
    results = getattr(result, "results", result) if not isinstance(result, list) else result
    return len(results) > 0


async def ensure_archival_memory_search(client, agent_id: str) -> None:
    """Attach archival_memory_search tool to agent if not already present.

    v2 agents don't include archival_memory_search in their base tools
    (it was deprecated from the default set), but skills are inserted into
    archival memory, so the agent needs this tool to search for them.
    """
    tools = await call_letta(client.tools.list, raise_on_error=False)
    if tools is None:
        return  # Non-fatal — agent may not be able to search skills

    for tool in tools.items:
        if tool.name == "archival_memory_search":
            await call_letta(
                client.agents.tools.attach,
                agent_id=agent_id,
                tool_id=tool.id,
                raise_on_error=False,
            )
            break


async def insert_skills_into_archival_memory(
    agent_id: str,
    skills: list,
    client,
    db=None,
) -> list[str]:
    """Insert skill content and text files into an agent's archival memory.

    For each skill, inserts the SKILL.md content as the primary passage.
    Then inserts any text-based skill files (scripts, references, etc.)
    as separate passages with granular tags. Binary files are skipped —
    LLMs can't read them.

    Args:
        agent_id: The Letta agent ID.
        skills: List of Skill ORM objects.
        client: Letta client instance.
        db: Optional AsyncSession for querying skill files.
            If not provided, skill files won't be inserted.

    Returns list of skill names that were successfully inserted.
    """

    inserted = []
    for skill in skills:
        # Skip if this skill already exists in archival memory
        if await _passage_tags_exist(client, agent_id, ["skills", skill.name]):
            logger.debug("Skill '%s' already in archival memory, skipping insert", skill.name)
            inserted.append(skill.name)  # Still count as available
            continue

        content = skill.content
        if not content:
            continue

        # Insert the main SKILL.md content
        passage_text = (
            f"[Skill: {skill.name}]\n"
            f"To use this skill, follow ALL steps below in order. Do not skip any step.\n"
            f"---\n"
            f"{content}\n"
            f"---\n"
            f"End of skill: {skill.name}"
        )

        result = await call_letta(
            client.agents.passages.create,
            agent_id=agent_id,
            text=passage_text,
            tags=["skills", skill.name],
            raise_on_error=False,
        )
        if result is not None:
            inserted.append(skill.name)

        # Insert text-based skill files as separate passages
        if db is not None:
            try:
                from app.skills.models import SkillFile

                file_result = await db.execute(select(SkillFile).where(SkillFile.skill_id == skill.id))
                skill_files = file_result.scalars().all()

                for sf in skill_files:
                    # Only insert text files — binary files are useless to LLMs
                    if sf.content_text is None:
                        continue

                    # Skip if this file already exists in archival memory
                    file_tags = ["skills", skill.name, "files", sf.path]
                    if await _passage_tags_exist(client, agent_id, file_tags):
                        logger.debug("Skill file '%s' already in archival memory, skipping", sf.path)
                        continue

                    file_passage = (
                        f"[Skill File: {skill.name}/{sf.path}]\n"
                        f"---\n"
                        f"{sf.content_text}\n"
                        f"---\n"
                        f"End of skill file: {sf.path}"
                    )

                    await call_letta(
                        client.agents.passages.create,
                        agent_id=agent_id,
                        text=file_passage,
                        tags=file_tags,
                        raise_on_error=False,
                    )
            except Exception:
                logger.warning("Failed to insert skill files for '%s'", skill.name, exc_info=True)
                # Non-fatal — main skill content was already inserted

    return inserted


async def insert_lessons_into_archival_memory(
    agent_id: str,
    lessons: list,
    client,
) -> list[str]:
    """Insert lesson content into an agent's archival memory.

    Returns list of lesson categories that were successfully inserted.
    """

    inserted = []
    for lesson in lessons:
        # Skip if this lesson already exists in archival memory
        if await _passage_tags_exist(client, agent_id, ["lessons", lesson.category]):
            logger.debug("Lesson '%s' already in archival memory, skipping insert", lesson.category)
            inserted.append(lesson.category)  # Still count as available
            continue

        passage_text = (
            f"[Lesson: {lesson.category}]\n"
            f"Past execution experience — learn from this.\n"
            f"---\n"
            f"{lesson.content}\n"
            f"---\n"
            f"End of lesson: {lesson.category}"
        )

        result = await call_letta(
            client.agents.passages.create,
            agent_id=agent_id,
            text=passage_text,
            tags=["lessons", lesson.category],
            raise_on_error=False,
        )
        if result is not None:
            inserted.append(lesson.category)

    return inserted
