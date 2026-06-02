"""Settings business logic — decoupled from routes for cross-module reuse."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.models import UserSettings


async def get_or_create_settings(
    user_id: str,
    db: AsyncSession,
) -> UserSettings:
    """Get existing settings or create defaults for a user.

    Extracted from routes so that other modules (tools, agents, chat, docs)
    can call it without importing from the routes layer.
    """
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        await db.flush()
    return settings
