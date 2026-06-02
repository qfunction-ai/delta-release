"""Skill lookup helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.models import Skill, SkillTool


async def get_skills_by_ids(
    skill_ids: list[str],
    user_id: str,
    db: AsyncSession,
) -> list[Skill]:
    """Load skill objects by their IDs."""
    if not skill_ids:
        return []

    result = await db.execute(select(Skill).where(Skill.id.in_(skill_ids), Skill.user_id == user_id))
    return list(result.scalars().all())


async def get_skill_tool_ids(
    skill_ids: list[str],
    db: AsyncSession,
) -> list[str]:
    """Look up tool IDs linked to the given skills via the skill_tools join table."""
    if not skill_ids:
        return []

    result = await db.execute(select(SkillTool.tool_id).where(SkillTool.skill_id.in_(skill_ids)))
    return [str(row[0]) for row in result.all()]
