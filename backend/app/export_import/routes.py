"""Export/Import routes — migrate tools, skills, and workflows between instances."""

import base64
import json
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db, list_owned
from app.rate_limit import limiter
from app.sanitize import validate_tool_source_code
from app.skills.models import Skill, SkillFile
from app.tools.helpers import register_and_store_tool
from app.tools.models import Tool
from app.tools.schemas import ToolCreate
from app.utils import read_upload_with_limit
from app.workflows.models import Workflow

from .schemas import ExportData, ExportDataValidator, ImportResult, ToolExport, WorkflowExport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export-import", tags=["export-import"])

# Maximum import file size: 10MB
MAX_IMPORT_SIZE = 10 * 1024 * 1024


async def _export_skill_files(skill_id, db: AsyncSession) -> list[dict]:
    """Export skill files as a list of dicts for JSON serialization."""
    from sqlalchemy import select

    result = await db.execute(select(SkillFile).where(SkillFile.skill_id == skill_id).order_by(SkillFile.path))
    files = result.scalars().all()

    exported = []
    for f in files:
        entry = {"path": f.path, "mime_type": f.mime_type}
        if f.content_text is not None:
            entry["content_text"] = f.content_text
        elif f.content_bytes is not None:
            entry["content_b64"] = base64.b64encode(f.content_bytes).decode("ascii")
        exported.append(entry)
    return exported


def _generate_unique_name(base_name: str, existing_names: set[str]) -> str:
    """Generate a unique name by appending suffix if needed."""
    if base_name not in existing_names:
        return base_name

    # Try _imported, _imported_2, _imported_3, etc.
    suffix = "_imported"
    counter = 2
    candidate = f"{base_name}{suffix}"
    while candidate in existing_names:
        candidate = f"{base_name}{suffix}_{counter}"
        counter += 1
    return candidate


@router.get("/export/")
@limiter.limit("10/minute")
async def export_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all tools, skills, and workflows for the current user.

    Returns a JSON file download containing all user's tools, skills, and workflows.
    Workflows reference tools and skills by name (not UUID) for portability.
    Agent IDs are excluded as they are instance-specific.
    """
    user_id = str(current_user.id)

    tools = await list_owned(db, Tool, user_id)
    skills = await list_owned(db, Skill, user_id)
    workflows = await list_owned(db, Workflow, user_id)

    tool_id_to_name = {str(t.id): t.name for t in tools}
    skill_id_to_name = {str(s.id): s.name for s in skills}

    export = ExportData(
        tools=[
            ToolExport(
                name=t.name,
                description=t.description,
                source_code=t.source_code,
                json_schema=json.loads(t.json_schema) if isinstance(t.json_schema, str) else t.json_schema,
                tags=t.tag_list,
                pip_requirements=t.pip_requirements_list,
            )
            for t in tools
        ],
        skills=[
            {
                "name": s.name,
                "description": s.description,
                "content": s.content,
                "files": await _export_skill_files(s.id, db),
            }
            for s in skills
        ],
        workflows=[
            WorkflowExport(
                name=w.name,
                description=w.description,
                prompt_template=w.prompt_template,
                tool_names=[tool_id_to_name.get(tid, "") for tid in (w.tool_ids_list or []) if tid in tool_id_to_name],
                skill_names=[
                    skill_id_to_name.get(sid, "") for sid in (w.skill_ids_list or []) if sid in skill_id_to_name
                ],
                schedule_cron=w.schedule_cron,
                default_variables=w.default_variables_dict,
                include_reasoning=w.include_reasoning,
            )
            for w in workflows
        ],
    )

    # Serialize to JSON
    export_json = export.model_dump_json(indent=2)

    return Response(
        content=export_json.encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="delta-export.json"',
        },
    )


async def _import_skills(
    skills_data: list[dict],
    user_id: str,
    existing_skill_names: set[str],
    db: AsyncSession,
    result: ImportResult,
) -> set[str]:
    """Import skills from export data. Returns set of imported skill names."""
    imported_skill_names: set[str] = set()

    for skill_data in skills_data:
        try:
            name = skill_data.get("name", "")
            if not name:
                result.skills_skipped += 1
                result.errors.append("Skill missing name field")
                continue

            unique_name = _generate_unique_name(name, existing_skill_names | imported_skill_names)
            if unique_name != name:
                logger.info("Skill name collision: %s -> %s", name, unique_name)

            skill = Skill(
                user_id=user_id,
                name=unique_name,
                description=skill_data.get("description"),
                source="import",
                content=skill_data.get("content", ""),
            )
            db.add(skill)
            await db.flush()

            for file_data in skill_data.get("files", []):
                try:
                    from app.sanitize import sanitize_file_path, validate_mime_type

                    content_text = file_data.get("content_text")
                    content_bytes = None
                    if content_text is None and file_data.get("content_b64"):
                        content_bytes = base64.b64decode(file_data["content_b64"])

                    raw_path = file_data.get("path", "unknown")
                    safe_path = sanitize_file_path(raw_path)
                    safe_mime = validate_mime_type(file_data.get("mime_type", "application/octet-stream"))

                    sf = SkillFile(
                        skill_id=skill.id,
                        path=safe_path,
                        content_text=content_text,
                        content_bytes=content_bytes,
                        mime_type=safe_mime,
                    )
                    db.add(sf)
                except Exception as file_err:
                    logger.warning("Failed to import skill file '%s': %s", file_data.get("path"), file_err)
            await db.flush()

            imported_skill_names.add(unique_name)
            result.skills_imported += 1

        except Exception as e:
            result.skills_skipped += 1
            result.errors.append(f"Skill '{skill_data.get('name', 'unknown')}': {e}")
            logger.exception("Failed to import skill")

    return imported_skill_names


async def _import_tools(
    tools_data: list[dict],
    user_id: str,
    existing_tool_names: set[str],
    db: AsyncSession,
    result: ImportResult,
) -> set[str]:
    """Import tools from export data. Returns set of imported tool names."""
    imported_tool_names: set[str] = set()

    for tool_data in tools_data:
        try:
            name = tool_data.get("name", "")
            if not name:
                result.tools_skipped += 1
                result.errors.append("Tool missing name field")
                continue

            unique_name = _generate_unique_name(name, existing_tool_names | imported_tool_names)
            if unique_name != name:
                logger.info("Tool name collision: %s -> %s", name, unique_name)

            validate_tool_source_code(tool_data.get("source_code", ""))

            tool_create = ToolCreate(
                name=unique_name,
                description=tool_data.get("description"),
                source_code=tool_data.get("source_code", ""),
                json_schema=tool_data.get("json_schema", {}),
                tags=tool_data.get("tags"),
                pip_requirements=tool_data.get("pip_requirements"),
            )

            await register_and_store_tool(
                name=unique_name,
                description=tool_create.description,
                source_code=tool_create.source_code,
                json_schema=tool_create.json_schema,
                tags=tool_create.tags,
                pip_requirements=tool_create.pip_requirements,
                user_id=user_id,
                db=db,
                source="import",
            )
            imported_tool_names.add(unique_name)
            result.tools_imported += 1

        except Exception as e:
            result.tools_skipped += 1
            result.errors.append(f"Tool '{tool_data.get('name', 'unknown')}': {e}")
            logger.exception("Failed to import tool")

    return imported_tool_names


async def _import_workflows(
    workflows_data: list[dict],
    user_id: str,
    existing_workflow_names: set[str],
    tool_name_to_id: dict[str, str],
    skill_name_to_id: dict[str, str],
    db: AsyncSession,
    result: ImportResult,
) -> None:
    """Import workflows from export data."""
    for workflow_data in workflows_data:
        try:
            name = workflow_data.get("name", "")
            if not name:
                result.workflows_skipped += 1
                result.errors.append("Workflow missing name field")
                continue

            unique_name = _generate_unique_name(name, existing_workflow_names)
            if unique_name != name:
                logger.info("Workflow name collision: %s -> %s", name, unique_name)

            tool_names = workflow_data.get("tool_names", [])
            skill_names = workflow_data.get("skill_names", [])

            tool_ids = [tool_name_to_id[n] for n in tool_names if n in tool_name_to_id]
            skill_ids = [skill_name_to_id[n] for n in skill_names if n in skill_name_to_id]

            workflow = Workflow(
                user_id=user_id,
                agent_id="",  # No agent assigned on import
                name=unique_name,
                description=workflow_data.get("description"),
                prompt_template=workflow_data.get("prompt_template", ""),
                tool_ids=json.dumps([str(tid) for tid in tool_ids]) if tool_ids else None,
                skill_ids=json.dumps([str(sid) for sid in skill_ids]) if skill_ids else None,
                schedule_cron=workflow_data.get("schedule_cron"),
                default_variables=json.dumps(workflow_data.get("default_variables"))
                if workflow_data.get("default_variables")
                else None,
                include_reasoning=workflow_data.get("include_reasoning", False),
            )
            db.add(workflow)
            await db.flush()

            result.workflows_imported += 1
            result.workflows_needing_agent += 1
            existing_workflow_names.add(unique_name)

        except Exception as e:
            result.workflows_skipped += 1
            result.errors.append(f"Workflow '{workflow_data.get('name', 'unknown')}': {e}")
            logger.exception("Failed to import workflow")


@router.post("/import/", response_model=ImportResult)
@limiter.limit("5/minute")
async def import_all(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import tools, skills, and workflows from an export file.

    Creates new entities owned by the current user. Handles name collisions
    by appending suffixes. Re-registers tools with Letta. Workflows are
    created without agent_id (user must assign agent later).
    """
    user_id = str(current_user.id)
    result = ImportResult()

    # Read and validate file
    content = await read_upload_with_limit(file, MAX_IMPORT_SIZE)

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("application/json", "text/plain", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content type: {content_type}. Expected application/json.",
        )

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e}",
        )

    try:
        validated = ExportDataValidator(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid export file format: {e}",
        )

    existing_tools = await list_owned(db, Tool, user_id)
    existing_skills = await list_owned(db, Skill, user_id)
    existing_workflows = await list_owned(db, Workflow, user_id)

    existing_tool_names = {t.name for t in existing_tools}
    existing_skill_names = {s.name for s in existing_skills}
    existing_workflow_names = {w.name for w in existing_workflows}

    # Import skills first (no dependencies)
    await _import_skills(validated.skills, user_id, existing_skill_names, db, result)

    # Import tools (register with Letta)
    await _import_tools(validated.tools, user_id, existing_tool_names, db, result)

    # Build name -> ID mappings for workflow references
    all_tools = await list_owned(db, Tool, user_id)
    all_skills = await list_owned(db, Skill, user_id)

    tool_name_to_id = {t.name: t.id for t in all_tools}
    skill_name_to_id = {s.name: s.id for s in all_skills}

    # Import workflows (reference tools/skills by name)
    await _import_workflows(
        validated.workflows,
        user_id,
        existing_workflow_names,
        tool_name_to_id,
        skill_name_to_id,
        db,
        result,
    )

    await db.commit()
    return result
