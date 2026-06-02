"""propose_tool — Letta tool that lets agents propose new tools.

When the agent_tool_creation setting is enabled for a user, this tool
is attached to their agents. The agent can call it to draft a new tool,
which enters a pending state requiring human review with dry-run results.
"""

_PROPOSE_TOOL_TEMPLATE = '''def propose_tool(name: str, source_code: str, json_schema: str, description: str = "", pip_requirements: str = "") -> str:
    """Propose a new tool for human review. The tool will be tested and shown to the operator for approval before it can be used.

    Args:
        name: Tool name in snake_case (e.g., query_sentinelone)
        source_code: Complete Python source code with a function matching the name
        json_schema: JSON schema for the function's parameters (as a JSON string)
        description: What the tool does (optional)
        pip_requirements: Comma-separated pip packages needed (e.g., "httpx,splunk-sdk")
    """
    import json, httpx, os

    # Read the API base URL and service token from environment (set at container level)
    api_base = os.getenv("DELTA_API_BASE_URL", "http://localhost:8000")
    service_token = os.getenv("DELTA_SERVICE_TOKEN", "")
    agent_id = {agent_id!r}

    # Parse the JSON schema — try JSON first, then Python literal eval as fallback
    # (the Letta sandbox may serialize the schema with single quotes)
    schema = None
    try:
        schema = json.loads(json_schema)
    except json.JSONDecodeError:
        try:
            import ast
            schema = ast.literal_eval(json_schema)
            if not isinstance(schema, dict):
                return "Invalid JSON schema: expected a dict, got " + type(schema).__name__
        except (ValueError, SyntaxError) as e:
            return "Invalid JSON schema: " + str(e)

    pip_reqs = [r.strip() for r in pip_requirements.split(",") if r.strip()] if pip_requirements else None

    # Call the Delta API to propose the tool via service-to-service endpoint
    headers = {{"Content-Type": "application/json"}}
    if service_token:
        headers["X-Service-Token"] = service_token

    payload = {{
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "source_code": source_code,
        "json_schema": schema,
        "pip_requirements": pip_reqs,
    }}

    try:
        resp = httpx.post(api_base + "/api/tools/propose/agent", json=payload, headers=headers, timeout=30)
        data = resp.json()
        if resp.status_code == 201:
            dry_run = "PASSED" if not data.get("dry_run_error") else "FAILED: " + data["dry_run_error"]
            return "Tool '" + name + "' proposed successfully. Dry run: " + dry_run + ". The operator will review and approve or reject it."
        else:
            return "Failed to propose tool: " + data.get("detail", resp.text)
    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException, json.JSONDecodeError) as e:
        return "Error proposing tool: " + str(e)
'''


def build_propose_tool_source(agent_id: str) -> str:
    """Generate propose_tool source code with agent ID baked in.

    The service token is read from the DELTA_SERVICE_TOKEN environment
    variable at runtime instead of being baked into the source code.
    This prevents the token from being exposed in the Letta sandbox
    where user-provided tools execute.
    """
    return _PROPOSE_TOOL_TEMPLATE.format(
        agent_id=agent_id,
    )


PROPOSE_TOOL_SCHEMA = {
    "title": "ProposeToolInput",
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Tool name in snake_case (e.g., query_sentinelone)"},
        "source_code": {
            "type": "string",
            "description": "Complete Python source code with a function matching the name",
        },
        "json_schema": {
            "type": "string",
            "description": "JSON schema for the function's parameters (as a JSON string)",
        },
        "description": {
            "type": "string",
            "description": "What the tool does",
            "default": "",
        },
        "pip_requirements": {
            "type": "string",
            "description": "Comma-separated pip packages needed (e.g., 'httpx,splunk-sdk')",
            "default": "",
        },
    },
    "required": ["name", "source_code", "json_schema"],
}

PROPOSE_TOOL_DESCRIPTION = "Propose a new tool for human review. The tool will be tested with safe inputs and shown to the operator for approval before it can be used. Use this when you need a capability that doesn't exist yet."
