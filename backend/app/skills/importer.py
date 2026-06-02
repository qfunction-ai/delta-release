"""Skill import/zip parsing logic."""

import logging
import os
import zipfile
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SKILL_FILENAME, get_settings
from app.skills.github_fetch import extract_description_from_frontmatter, extract_name_from_frontmatter
from app.skills.models import Skill, SkillFile, SkillTool

logger = logging.getLogger(__name__)


async def persist_skill(
    user_id: str,
    name: str,
    description: str | None,
    source: str,
    content: str,
    db: AsyncSession,
    extra_files: dict[str, bytes] | None = None,
    tool_ids: list[str] | None = None,
) -> Skill:
    """Create and flush the Skill DB record, plus any extra files and tool links."""
    skill = Skill(
        user_id=user_id,
        name=name,
        description=description,
        source=source,
        content=content,
    )
    db.add(skill)
    await db.flush()

    # Persist extra files (scripts, references, assets, etc.)
    if extra_files:
        from app.sanitize import sanitize_file_path, validate_mime_type

        for rel_path, data in extra_files.items():
            content_text, content_bytes = _split_text_binary(data)
            safe_path = sanitize_file_path(rel_path)
            mime_type = validate_mime_type(_guess_mime_type(rel_path))
            sf = SkillFile(
                skill_id=skill.id,
                path=safe_path,
                content_text=content_text,
                content_bytes=content_bytes,
                mime_type=mime_type,
            )
            db.add(sf)
        await db.flush()

    # Persist skill-tool links (ownership already validated by callers)
    if tool_ids:
        for tid in tool_ids:
            db.add(SkillTool(skill_id=skill.id, tool_id=tid))
        await db.flush()

    return skill


def _split_text_binary(data: bytes) -> tuple[str | None, bytes | None]:
    """Split raw bytes into (text, None) or (None, bytes) depending on UTF-8 decodability."""
    try:
        text = data.decode("utf-8")
        if "\x00" in text:
            return None, data
        return text, None
    except UnicodeDecodeError:
        return None, data


def _guess_mime_type(path: str) -> str:
    """Guess MIME type from file path. Falls back to application/octet-stream."""
    import mimetypes

    # Register types that Python's mimetypes module doesn't know by default
    mimetypes.add_type("application/yaml", ".yaml")
    mimetypes.add_type("application/yaml", ".yml")
    mimetypes.add_type("text/markdown", ".md")
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def parse_skill_zip(zip_bytes: bytes) -> tuple[str, str, str, dict[str, bytes]]:
    """Parse a zipped skill directory.

    Returns: (name, description, skill_md_content, extra_files)
    extra_files is a dict of {relative_path: file_bytes} for non-SKILL.md files.
    """
    settings = get_settings()
    try:
        zf = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("Invalid zip file")

    # Find SKILL.md - it could be at root or one level deep
    skill_md_path = None
    all_files = {}

    total_uncompressed = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        # Reject path traversal entries
        if ".." in info.filename or info.filename.startswith("/") or "\\" in info.filename:
            continue
        # Reject macOS metadata junk
        if "__MACOSX" in info.filename or info.filename.startswith("."):
            continue
        if len(all_files) >= settings.max_zip_entries:
            raise ValueError(f"Zip contains too many files. Maximum is {settings.max_zip_entries}")
        # Reject oversized entries (decompression bomb protection)
        if info.file_size > settings.max_file_uncompressed_size:
            raise ValueError(
                f"File '{info.filename}' is too large when decompressed "
                f"({info.file_size} bytes, max {settings.max_file_uncompressed_size} bytes)"
            )
        total_uncompressed += info.file_size
        if total_uncompressed > settings.max_zip_total_uncompressed:
            raise ValueError(
                f"Total uncompressed size exceeds limit "
                f"({total_uncompressed} bytes, max {settings.max_zip_total_uncompressed} bytes)"
            )
        all_files[info.filename] = zf.read(info.filename)

    # Look for SKILL.md
    for path in all_files:
        basename = os.path.basename(path)
        if basename == SKILL_FILENAME:
            skill_md_path = path
            break

    if skill_md_path is None:
        raise ValueError("Zip must contain a SKILL.md file")

    try:
        skill_content = all_files[skill_md_path].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"SKILL.md is not valid UTF-8: {e}")
    name = extract_name_from_frontmatter(skill_content)
    description = extract_description_from_frontmatter(skill_content)

    if not name:
        # Derive name from directory structure
        parts = skill_md_path.split("/")
        if len(parts) > 1:
            name = parts[0]
        else:
            raise ValueError("SKILL.md must have a 'name' field in frontmatter")

    # Determine the base directory (if any)
    if "/" in skill_md_path:
        base_dir = skill_md_path.rsplit("/", 1)[0]
    else:
        base_dir = ""

    # Collect extra files (everything except SKILL.md)
    extra_files = {}
    for path, data in all_files.items():
        if path == skill_md_path:
            continue
        # Strip base directory prefix
        if base_dir and path.startswith(base_dir + "/"):
            rel_path = path[len(base_dir) + 1 :]
        else:
            rel_path = path

        # Sanitize path: reject traversal attempts
        if ".." in rel_path or rel_path.startswith("/") or "\\" in rel_path:
            continue
        extra_files[rel_path] = data

    return name, description or "", skill_content, extra_files
