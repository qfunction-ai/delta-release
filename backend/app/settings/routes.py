"""User settings routes — configuration that gates agent capabilities."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, resolve_agent_user, verify_service_token
from app.auth.models import User
from app.database import get_db
from app.settings.models import UserSettings
from app.settings.schemas import UserSettingsResponse, UserSettingsUpdate
from app.settings.service import get_or_create_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

_UPDATABLE_FIELDS = ("agent_tool_creation", "eval_enabled", "web_search_enabled", "docs_fetch_enabled")


def _apply_settings_update(settings: UserSettings, data: UserSettingsUpdate) -> None:
    """Apply non-None fields from an update schema to the settings model."""
    for field in _UPDATABLE_FIELDS:
        val = getattr(data, field, None)
        if val is not None:
            setattr(settings, field, val)


@router.get("/", response_model=UserSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user settings. Auto-creates defaults on first access."""
    settings = await get_or_create_settings(str(current_user.id), db)
    return settings


@router.put("/", response_model=UserSettingsResponse)
async def update_settings(
    settings_data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user settings. Only provided fields are changed."""
    settings = await get_or_create_settings(str(current_user.id), db)

    _apply_settings_update(settings, settings_data)

    await db.flush()
    return settings


@router.put("/eval", response_model=UserSettingsResponse)
async def eval_update_settings(
    request: Request,
    settings_data: UserSettingsUpdate,
    agent_id: str = Query("", alias="agent_id"),
    _auth=Depends(verify_service_token),
    db: AsyncSession = Depends(get_db),
):
    """Service-to-service settings update for the eval container.

    Resolves the user from the agent_id, then updates their settings.
    All toggle fields are accepted — the service token is the trust
    boundary, not the endpoint. The eval container needs to control
    agent_tool_creation and web_search_enabled to test toggle behavior.

    Requires X-Service-Token header for authentication.
    """
    if not agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agent_id query parameter is required")

    # Resolve agent and set user_id for audit logging
    agent = await resolve_agent_user(request, agent_id, db)

    settings = await get_or_create_settings(str(agent.user_id), db)

    _apply_settings_update(settings, settings_data)

    await db.flush()
    return settings
