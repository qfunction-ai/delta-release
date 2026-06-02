"""GitHub skill fetch logic — fetch SKILL.md and extra files from GitHub repos."""

import logging
import re

import httpx
from fastapi import HTTPException, status

from app.config import SKILL_FILENAME, get_settings
from app.github import (
    detect_default_branch,
    fetch_file_bytes_from_github,
    fetch_file_from_github,
    fetch_github_directory,
    fetch_github_subdir_contents,
)

logger = logging.getLogger(__name__)


async def fetch_github_skill(
    owner: str,
    repo: str,
    branch: str | None,
    sub_path: str,
    gh_headers: dict,
) -> tuple[str, str, str, dict[str, bytes], bool]:
    """Fetch SKILL.md and all extra files from GitHub API.

    Collects files from any subdirectory and loose files at the root level,
    not just scripts/, references/, and assets/. Per the Agent Skills spec,
    skill directories can contain arbitrary files and folders.

    Returns: (name, description, skill_content, extra_files, has_tool_yaml)
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client_http:
        # If no branch specified, detect default branch
        if not branch:
            branch = await detect_default_branch(client_http, owner, repo, gh_headers)

        contents = await fetch_github_directory(client_http, owner, repo, branch, sub_path, gh_headers)
        params = {"ref": branch}

        # Find SKILL.md in the directory
        skill_md_entry = None
        for entry in contents:
            if entry.get("name") == SKILL_FILENAME and entry.get("type") == "file":
                skill_md_entry = entry
                break

        if not skill_md_entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub directory must contain a SKILL.md file"
            )

        # Download SKILL.md content using the shared SSRF-safe helper
        download_url = skill_md_entry.get("download_url")
        if not download_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Could not get download URL for SKILL.md"
            )
        skill_content = await fetch_file_from_github(client_http, download_url, "SKILL.md", settings.max_upload_size)

        name = extract_name_from_frontmatter(skill_content)
        description = extract_description_from_frontmatter(skill_content)

        if not name:
            # Derive from directory name
            name = sub_path.split("/")[-1] if sub_path else repo
            name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)

        # Download ALL extra files — any subdirectory, any loose file.
        # Skip SKILL.md (already downloaded) and tool.yaml (metadata, not content).
        extra_files: dict[str, bytes] = {}

        for entry in contents:
            entry_name = entry.get("name", "")
            entry_type = entry.get("type", "")

            # Skip SKILL.md and tool.yaml
            if entry_name in (SKILL_FILENAME, "tool.yaml"):
                continue

            if entry_type == "file" and entry.get("download_url"):
                # Loose file at the root level of the skill directory
                try:
                    file_bytes = await fetch_file_bytes_from_github(
                        client_http, entry["download_url"], entry_name, settings.max_upload_size
                    )
                    extra_files[entry_name] = file_bytes
                except HTTPException as e:
                    if "SSRF" in str(e.detail) or "Invalid download URL" in str(e.detail):
                        logger.warning("Skipping file from GitHub repo (SSRF): %s", entry_name)
                        continue
                    raise

            elif entry_type == "dir" and entry.get("url"):
                # Any subdirectory — fetch all files within it
                subdir_contents = await fetch_github_subdir_contents(client_http, entry["url"], params, gh_headers)
                if not subdir_contents:
                    continue

                for sub_entry in subdir_contents:
                    if sub_entry.get("type") == "file" and sub_entry.get("download_url"):
                        sub_name = sub_entry["name"]
                        try:
                            file_bytes = await fetch_file_bytes_from_github(
                                client_http, sub_entry["download_url"], sub_name, settings.max_upload_size
                            )
                            rel_path = f"{entry_name}/{sub_name}"
                            extra_files[rel_path] = file_bytes
                        except HTTPException as e:
                            if "SSRF" in str(e.detail) or "Invalid download URL" in str(e.detail):
                                logger.warning("Skipping file from GitHub repo (SSRF): %s", sub_name)
                                continue
                            raise

        has_tool_yaml = any(e.get("name") == "tool.yaml" and e.get("type") == "file" for e in contents)

        return name, description or "", skill_content, extra_files, has_tool_yaml


def _extract_frontmatter_field(content: str, field: str) -> str | None:
    """Extract a named field from YAML frontmatter using yaml.safe_load."""
    if not content.strip().startswith("---"):
        return None
    parts = content.strip().split("---", 2)
    if len(parts) < 3:
        return None
    try:
        import yaml

        frontmatter = yaml.safe_load(parts[1].strip())
        if isinstance(frontmatter, dict):
            return str(frontmatter.get(field, "")) if frontmatter.get(field) is not None else None
    except Exception:
        # Fall back to line-by-line parsing if YAML parsing fails
        for line in parts[1].strip().split("\n"):
            if line.startswith(f"{field}:"):
                return line.split(":", 1)[1].strip().strip("\"'")
    return None


def extract_description_from_frontmatter(content: str) -> str | None:
    """Extract description from YAML frontmatter."""
    return _extract_frontmatter_field(content, "description")


def extract_name_from_frontmatter(content: str) -> str | None:
    """Extract name from YAML frontmatter."""
    return _extract_frontmatter_field(content, "name")
