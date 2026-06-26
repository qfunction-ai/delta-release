import logging
import re

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_settings
from app.database import check_unique_for_user, get_db, get_owned_or_404, list_owned
from app.errors import sanitize_error_detail
from app.github import build_github_headers, parse_github_url
from app.rate_limit import limiter
from app.skills.github_fetch import (
    extract_description_from_frontmatter,
    fetch_github_skill,
)
from app.utils import read_upload_with_limit
from app.skills.importer import parse_skill_zip, persist_skill
from app.skills.models import Skill, SkillFile, SkillTool
from app.skills.schemas import (
    SkillContentResponse,
    SkillCreate,
    SkillFileResponse,
    SkillGithubCreate,
    SkillResponse,
    SkillUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

_SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_skill_name(name: str) -> None:
    """Raise HTTPException 400 if skill name format is invalid."""
    if not _SKILL_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill name '{name}': must contain only letters, numbers, underscores, and hyphens",
        )


async def _validate_tool_ownership(
    tool_ids: list[str],
    user_id: str,
    db: AsyncSession,
) -> list[str]:
    """Verify each tool_id belongs to the given user.

    Raises HTTPException 404 if any tool is not found or does not belong
    to the user. Returns the validated tool IDs.
    """
    from app.tools.models import Tool

    validated = []
    for tid in tool_ids:
        result = await db.execute(select(Tool).where(Tool.id == tid, Tool.user_id == user_id))
        tool = result.scalar_one_or_none()
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool {tid} not found",
            )
        validated.append(tid)
    return validated


@router.get("/", response_model=list[SkillResponse])
async def list_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's skills."""
    skills = await list_owned(db, Skill, current_user.id)
    # Batch-load all SkillTool records for this user's skills in one query
    # instead of N+1 queries (one per skill).
    if skills:
        skill_ids = [s.id for s in skills]
        result = await db.execute(
            select(SkillTool.skill_id, SkillTool.tool_id).where(SkillTool.skill_id.in_(skill_ids))
        )
        # Group by skill_id
        tool_map: dict[str, list[str]] = {}
        for skill_id, tool_id in result.all():
            tool_map.setdefault(str(skill_id), []).append(str(tool_id))
        for skill in skills:
            skill.tool_ids = tool_map.get(str(skill.id), [])
    else:
        for skill in skills:
            skill.tool_ids = []
    return skills


@router.post("/", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_skill(
    request: Request,
    skill_data: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new skill from raw content."""
    validate_skill_name(skill_data.name)
    await check_unique_for_user(db, Skill, current_user.id, "name", skill_data.name, error_label="Skill")

    validated_tool_ids = None
    if skill_data.tool_ids:
        validated_tool_ids = await _validate_tool_ownership(skill_data.tool_ids, str(current_user.id), db)

    description = extract_description_from_frontmatter(skill_data.content)
    skill = await persist_skill(
        current_user.id,
        skill_data.name,
        description,
        "manual",
        skill_data.content,
        db,
        tool_ids=validated_tool_ids,
    )
    skill.tool_ids = validated_tool_ids or []
    return skill


@router.post("/upload", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def upload_skill(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a zipped skill directory (.zip or .skill file)."""
    settings = get_settings()
    zip_bytes = await read_upload_with_limit(file, settings.max_upload_size)

    try:
        name, description, skill_content, extra_files = parse_skill_zip(zip_bytes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=sanitize_error_detail(str(e)))

    validate_skill_name(name)
    await check_unique_for_user(db, Skill, current_user.id, "name", name, error_label="Skill")

    skill = await persist_skill(
        current_user.id, name, description, "upload", skill_content, db, extra_files=extra_files
    )
    skill.tool_ids = []
    return skill


@router.post("/github", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_skill_from_github(
    request: Request,
    skill_data: SkillGithubCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a skill from a GitHub URL pointing to a skill directory."""
    owner, repo, branch, sub_path = parse_github_url(skill_data.github_url)

    gh_headers = build_github_headers()

    name, description, skill_content, extra_files, has_tool_yaml = await fetch_github_skill(
        owner, repo, branch, sub_path, gh_headers
    )

    validate_skill_name(name)
    await check_unique_for_user(db, Skill, current_user.id, "name", name, error_label="Skill")

    skill = await persist_skill(
        current_user.id, name, description, "github", skill_content, db, extra_files=extra_files
    )

    # Co-create tool if tool.yaml exists in the same directory
    tool_response = None
    tool_status = None
    if has_tool_yaml:
        from app.tools.github import fetch_github_tool
        from app.tools.helpers import register_and_store_tool
        from app.tools.schemas import ToolResponse as ToolRespSchema

        try:
            tool_name, tool_desc, source_code, json_schema, tags, pip_reqs, _ = await fetch_github_tool(
                owner, repo, branch, sub_path, gh_headers
            )
        except (httpx.HTTPError, HTTPException) as e:
            logger.warning("Failed to fetch tool.yaml from GitHub: %s", e)
            tool_status = "fetch_failed"
        else:
            try:
                tool = await register_and_store_tool(
                    name=tool_name,
                    description=tool_desc,
                    source_code=source_code,
                    json_schema=json_schema,
                    tags=tags,
                    pip_requirements=pip_reqs,
                    user_id=str(current_user.id),
                    db=db,
                    source="github",
                    raise_on_error=False,
                )
                if tool is not None:
                    tool_response = ToolRespSchema.from_orm_with_tags(tool)
                    db.add(SkillTool(skill_id=skill.id, tool_id=tool.id))
                    await db.flush()
                    skill.tool_ids = [str(tool.id)]
                    tool_status = "created"
            except HTTPException as e:
                if e.status_code == 409:
                    # Tool already exists — link the existing one instead
                    from app.tools.models import Tool

                    result = await db.execute(
                        select(Tool).where(
                            Tool.name == tool_name,
                            Tool.user_id == current_user.id,
                        )
                    )
                    existing_tool = result.scalar_one_or_none()
                    if existing_tool is not None:
                        tool_response = ToolRespSchema.from_orm_with_tags(existing_tool)
                        db.add(SkillTool(skill_id=skill.id, tool_id=existing_tool.id))
                        await db.flush()
                        skill.tool_ids = [str(existing_tool.id)]
                        tool_status = "linked_existing"
                    else:
                        tool_status = "conflict"
                        logger.warning("Tool name conflict but no existing tool found: %s", tool_name)
                else:
                    logger.warning("Failed to co-create tool from tool.yaml: %s", e.detail)
                    tool_status = "failed"
            except (httpx.HTTPError, SQLAlchemyError) as e:
                logger.warning("Failed to co-create tool from tool.yaml: %s", e)
                tool_status = "failed"

    if not hasattr(skill, "tool_ids"):
        skill.tool_ids = []

    return {
        "skill": SkillResponse.model_validate(skill),
        "tool": tool_response,
        "tool_status": tool_status,
    }


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get skill metadata."""
    skill = await get_owned_or_404(db, Skill, skill_id, current_user.id)
    # Attach tool_ids from skill_tools join table
    result = await db.execute(select(SkillTool.tool_id).where(SkillTool.skill_id == skill.id))
    skill.tool_ids = [str(row[0]) for row in result.all()]
    return skill


@router.get("/{skill_id}/content", response_model=SkillContentResponse)
async def get_skill_content(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get skill content and list of attached files."""
    skill = await get_owned_or_404(db, Skill, skill_id, current_user.id)

    if not skill.content:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Skill content not available")

    result = await db.execute(select(SkillFile).where(SkillFile.skill_id == skill.id).order_by(SkillFile.path))
    files = result.scalars().all()

    file_responses = [
        SkillFileResponse(
            id=f.id,
            skill_id=f.skill_id,
            path=f.path,
            mime_type=f.mime_type,
            size=len(f.content_text.encode("utf-8"))
            if f.content_text
            else len(f.content_bytes)
            if f.content_bytes
            else 0,
        )
        for f in files
    ]

    tool_result = await db.execute(select(SkillTool.tool_id).where(SkillTool.skill_id == skill.id))
    tool_ids = [str(row[0]) for row in tool_result.all()]

    return SkillContentResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        content=skill.content,
        files=file_responses,
        tool_ids=tool_ids,
    )


@router.get("/{skill_id}/files/{file_id}")
async def get_skill_file(
    skill_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download an individual skill file by ID."""
    # Verify the user owns the skill
    await get_owned_or_404(db, Skill, skill_id, current_user.id)

    result = await db.execute(select(SkillFile).where(SkillFile.id == file_id, SkillFile.skill_id == skill_id))
    sf = result.scalar_one_or_none()
    if not sf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill file not found")

    from fastapi.responses import Response

    from app.sanitize import sanitize_filename, validate_mime_type

    content = sf.content_text.encode("utf-8") if sf.content_text is not None else sf.content_bytes
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill file has no content")

    filename = sanitize_filename(sf.path)
    mime = validate_mime_type(sf.mime_type)
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    skill_data: SkillUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a skill."""
    skill = await get_owned_or_404(db, Skill, skill_id, current_user.id)

    if skill_data.name is not None and skill_data.name != skill.name:
        # Validate name format (same as create)
        validate_skill_name(skill_data.name)
        await check_unique_for_user(
            db, Skill, current_user.id, "name", skill_data.name, exclude_id=skill_id, error_label="Skill"
        )
        skill.name = skill_data.name

    if skill_data.description is not None:
        skill.description = skill_data.description

    if skill_data.content is not None:
        skill.content = skill_data.content
        skill.description = extract_description_from_frontmatter(skill_data.content)

    if skill_data.tool_ids is not None:
        validated_tool_ids = await _validate_tool_ownership(skill_data.tool_ids, str(current_user.id), db)
        # Replace skill-tool links
        existing = await db.execute(select(SkillTool).where(SkillTool.skill_id == skill.id))
        for st in existing.scalars().all():
            await db.delete(st)
        # Flush deletes before inserting new links to avoid unique constraint violation
        # on (skill_id, tool_id) when the same tool_id is being re-linked
        await db.flush()
        for tid in validated_tool_ids:
            db.add(SkillTool(skill_id=skill.id, tool_id=tid))

    await db.flush()

    # Attach tool_ids for the response schema
    if skill_data.tool_ids is not None:
        skill.tool_ids = validated_tool_ids
    else:
        result = await db.execute(select(SkillTool.tool_id).where(SkillTool.skill_id == skill.id))
        skill.tool_ids = [str(row[0]) for row in result.all()]

    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a skill."""
    skill = await get_owned_or_404(db, Skill, skill_id, current_user.id)
    await db.delete(skill)
