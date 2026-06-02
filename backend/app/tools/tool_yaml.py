"""Parser for tool.yaml manifests from GitHub tool repos.

A tool.yaml manifest defines the entry point and metadata for a tool
stored in a GitHub repository. This follows the Agent Skills convention
where executable code lives in a scripts/ directory.

Minimal tool.yaml:
    name: query_splunk
    entry_point: query_splunk

Full tool.yaml:
    name: query_splunk
    description: "Search Splunk for security events"
    entry_point: query_splunk
    source: scripts/query_splunk.py
    schema: schema.json
    tags: [splunk, siem]
    requirements: requirements.txt

Defaults:
    source → scripts/{entry_point}.py
    schema → schema.json
    requirements → requirements.txt (only if the file exists)
"""

import re
from dataclasses import dataclass, field

import yaml

# Tool names must be valid Python identifiers (lowercase, underscores)
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class ToolManifest:
    """Parsed tool.yaml manifest."""

    name: str
    entry_point: str
    description: str | None = None
    source: str = ""  # Defaults to scripts/{entry_point}.py
    schema: str = "schema.json"
    tags: list[str] = field(default_factory=list)
    requirements: str = "requirements.txt"


class ToolYamlError(ValueError):
    """Raised when a tool.yaml is invalid."""


def parse_tool_yaml(content: str) -> ToolManifest:
    """Parse a tool.yaml manifest string into a ToolManifest.

    Args:
        content: Raw YAML content of tool.yaml

    Returns:
        ToolManifest with defaults applied

    Raises:
        ToolYamlError: If the manifest is invalid
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ToolYamlError(f"Invalid YAML: {e}")

    if not isinstance(data, dict):
        raise ToolYamlError("tool.yaml must be a YAML mapping")

    # Required fields
    name = data.get("name")
    if not name:
        raise ToolYamlError("tool.yaml missing required field: name")
    if not isinstance(name, str):
        raise ToolYamlError("tool.yaml 'name' must be a string")
    if not _TOOL_NAME_RE.match(name):
        raise ToolYamlError(
            f"tool.yaml 'name' must be a valid Python identifier "
            f"(lowercase, start with letter, underscores allowed): {name}"
        )

    entry_point = data.get("entry_point")
    if not entry_point:
        raise ToolYamlError("tool.yaml missing required field: entry_point")
    if not isinstance(entry_point, str):
        raise ToolYamlError("tool.yaml 'entry_point' must be a string")
    if not _TOOL_NAME_RE.match(entry_point):
        raise ToolYamlError(f"tool.yaml 'entry_point' must be a valid Python identifier: {entry_point}")

    # Optional fields with validation
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise ToolYamlError("tool.yaml 'description' must be a string or null")

    source = data.get("source", f"scripts/{entry_point}.py")
    if not isinstance(source, str):
        raise ToolYamlError("tool.yaml 'source' must be a string")

    schema = data.get("schema", "schema.json")
    if not isinstance(schema, str):
        raise ToolYamlError("tool.yaml 'schema' must be a string")

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not isinstance(tags, list):
        raise ToolYamlError("tool.yaml 'tags' must be a list")
    for tag in tags:
        if not isinstance(tag, str):
            raise ToolYamlError("tool.yaml 'tags' must contain only strings")

    requirements = data.get("requirements", "requirements.txt")
    if not isinstance(requirements, str):
        raise ToolYamlError("tool.yaml 'requirements' must be a string")

    return ToolManifest(
        name=name,
        entry_point=entry_point,
        description=description,
        source=source,
        schema=schema,
        tags=tags,
        requirements=requirements,
    )


def validate_entry_point(source_code: str, entry_point: str) -> None:
    """Verify that the entry point exists as a function definition in the source.

    Args:
        source_code: Python source code
        entry_point: Function name to look for

    Raises:
        ToolYamlError: If the function is not found
    """
    # Simple check: look for `def {entry_point}` in the source
    # This is intentionally loose — we don't parse the AST for speed
    pattern = re.compile(rf"^def\s+{re.escape(entry_point)}\s*\(", re.MULTILINE)
    if not pattern.search(source_code):
        raise ToolYamlError(f"Entry point '{entry_point}' not found as a function definition in source code")
