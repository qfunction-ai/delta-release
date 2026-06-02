"""GitHub tool fetch logic — fetch tool.yaml manifests from GitHub repos."""

import json
import logging

import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.constants import GITHUB_FETCH_TIMEOUT
from app.github import (
    detect_default_branch,
    fetch_file_from_github,
    fetch_github_directory,
    fetch_github_subdir_contents,
)
from app.sanitize import validate_tool_source_code
from app.tools.tool_yaml import ToolYamlError, parse_tool_yaml, validate_entry_point

logger = logging.getLogger(__name__)

TOOL_YAML_FILENAME = "tool.yaml"


async def fetch_github_tool(
    owner: str,
    repo: str,
    branch: str | None,
    sub_path: str,
    gh_headers: dict,
) -> tuple[str, str | None, str, dict, list[str], list[str] | None, bool]:
    """Fetch a tool from a GitHub repo containing a tool.yaml manifest.

    Returns:
        (name, description, source_code, json_schema, tags, pip_requirements, has_skill_md)

    Raises:
        HTTPException: On validation or fetch errors
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=GITHUB_FETCH_TIMEOUT) as client_http:
        # Detect default branch if not specified
        if not branch:
            branch = await detect_default_branch(client_http, owner, repo, gh_headers)

        contents = await fetch_github_directory(client_http, owner, repo, branch, sub_path, gh_headers)
        params = {"ref": branch}

        entries_by_name = {e.get("name"): e for e in contents if isinstance(e, dict)}

        tool_yaml_entry = entries_by_name.get(TOOL_YAML_FILENAME)
        if not tool_yaml_entry or tool_yaml_entry.get("type") != "file":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub directory must contain a {TOOL_YAML_FILENAME} file",
            )

        # Download and parse tool.yaml
        tool_yaml_content = await fetch_file_from_github(
            client_http, tool_yaml_entry["download_url"], TOOL_YAML_FILENAME, settings.max_upload_size
        )
        try:
            manifest = parse_tool_yaml(tool_yaml_content)
        except ToolYamlError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {TOOL_YAML_FILENAME}: {e}")

        # Resolve the source file path
        source_path = manifest.source
        source_parts = source_path.split("/")
        source_filename = source_parts[-1]
        source_subdir = "/".join(source_parts[:-1]) if len(source_parts) > 1 else ""

        # Find the source file entry
        source_entry = None
        subdir_contents: list[dict] | None = None
        if source_subdir:
            subdir_entry = entries_by_name.get(source_subdir)
            if subdir_entry and subdir_entry.get("type") == "dir":
                subdir_contents = await fetch_github_subdir_contents(
                    client_http, subdir_entry["url"], params, gh_headers
                )
                if subdir_contents:
                    for entry in subdir_contents:
                        if entry.get("name") == source_filename and entry.get("type") == "file":
                            source_entry = entry
                            break
        else:
            source_entry = entries_by_name.get(source_filename)

        if not source_entry or not source_entry.get("download_url"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source file '{source_path}' not found in GitHub directory",
            )

        # Download source code
        source_code = await fetch_file_from_github(
            client_http, source_entry["download_url"], manifest.source, settings.max_upload_size
        )

        try:
            validate_entry_point(source_code, manifest.entry_point)
        except ToolYamlError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Sanitize source code
        validate_tool_source_code(source_code)

        # Find and download schema.json
        schema_entry = None
        schema_parts = manifest.schema.split("/")
        schema_filename = schema_parts[-1]
        schema_subdir = "/".join(schema_parts[:-1]) if len(schema_parts) > 1 else ""

        if schema_subdir:
            if schema_subdir == source_subdir and subdir_contents is not None:
                for entry in subdir_contents:
                    if entry.get("name") == schema_filename and entry.get("type") == "file":
                        schema_entry = entry
                        break
            else:
                sd_entry = entries_by_name.get(schema_subdir)
                if sd_entry and sd_entry.get("type") == "dir":
                    sd_contents = await fetch_github_subdir_contents(client_http, sd_entry["url"], params, gh_headers)
                    if sd_contents:
                        for entry in sd_contents:
                            if entry.get("name") == schema_filename and entry.get("type") == "file":
                                schema_entry = entry
                                break
        else:
            schema_entry = entries_by_name.get(schema_filename)

        if not schema_entry or not schema_entry.get("download_url"):
            # Schema file not found — auto-generate from source code instead
            from app.tools.routes import generate_schema_from_source

            try:
                json_schema = generate_schema_from_source(source_code)
                logger.info("Auto-generated schema for '%s' from source code", manifest.name)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Schema file '{manifest.schema}' not found and could not auto-generate: {e}",
                )
        else:
            schema_content = await fetch_file_from_github(
                client_http, schema_entry["download_url"], manifest.schema, settings.max_upload_size
            )
            try:
                json_schema = json.loads(schema_content)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON in {manifest.schema}: {e}"
                )

        # Find and download requirements.txt (optional)
        pip_requirements: list[str] | None = None
        reqs_entry = None
        reqs_parts = manifest.requirements.split("/")
        reqs_filename = reqs_parts[-1]
        reqs_subdir = "/".join(reqs_parts[:-1]) if len(reqs_parts) > 1 else ""

        if reqs_subdir:
            if reqs_subdir == source_subdir and subdir_contents is not None:
                for entry in subdir_contents:
                    if entry.get("name") == reqs_filename and entry.get("type") == "file":
                        reqs_entry = entry
                        break
            else:
                rd_entry = entries_by_name.get(reqs_subdir)
                if rd_entry and rd_entry.get("type") == "dir":
                    rd_contents = await fetch_github_subdir_contents(client_http, rd_entry["url"], params, gh_headers)
                    if rd_contents:
                        for entry in rd_contents:
                            if entry.get("name") == reqs_filename and entry.get("type") == "file":
                                reqs_entry = entry
                                break
        else:
            reqs_entry = entries_by_name.get(reqs_filename)

        if reqs_entry and reqs_entry.get("download_url"):
            reqs_content = await fetch_file_from_github(
                client_http, reqs_entry["download_url"], manifest.requirements, settings.max_upload_size
            )
            pip_requirements = [
                line.strip()
                for line in reqs_content.strip().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if not pip_requirements:
                pip_requirements = None

        has_skill_md = entries_by_name.get("SKILL.md") is not None

        return (
            manifest.name,
            manifest.description,
            source_code,
            json_schema,
            manifest.tags,
            pip_requirements,
            has_skill_md,
        )
