"""list_github_repo — Letta tool that lets agents browse GitHub repo file trees.

When the agent_tool_creation setting is enabled for a user, this tool
is attached to their agents alongside propose_tool and fetch_docs. The
agent calls it with a GitHub repo URL to get the file tree, then uses
fetch_docs to read specific files from raw.githubusercontent.com.

No authentication is needed — the tool calls the GitHub API directly
for public repositories (60 req/hr unauthenticated rate limit).
"""

_LIST_GITHUB_REPO_TOOL_TEMPLATE = '''def list_github_repo(repo_url: str, branch: str = "main") -> str:
    """List the file structure of a GitHub repository. Use this to browse a repo's files before reading specific ones with fetch_docs.

    Only public GitHub repositories are supported. The tool returns the file tree
    (paths only) filtered to relevant source files. After listing, use fetch_docs
    to read individual files from raw.githubusercontent.com.

    Args:
        repo_url: GitHub repository URL (e.g., "https://github.com/CrowdStrike/falconpy")
        branch: Branch name (default: "main"). Try "master" if the repo uses that instead.
    """
    import json, httpx, re

    # Parse the GitHub repo URL to extract owner and repo
    match = re.match(r"https?://github\\.com/([^/]+)/([^/]+)/?", repo_url)
    if not match:
        return "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
    owner = match.group(1)
    repo = match.group(2)

    # Noise directories to filter out
    _NOISE_DIRS = {".github", ".git", "node_modules", "__pycache__", ".venv",
                   "venv", "dist", "build", ".eggs", ".pytest_cache", ".mypy_cache",
                   ".tox", "htmlcov", ".idea", ".vscode"}
    _MAX_PATHS = 500

    api_url = "https://api.github.com/repos/{}/{}".format(owner, repo) + "/git/trees/{}?recursive=1".format(branch)

    headers = {{"Accept": "application/vnd.github+json", "User-Agent": "Mozilla/5.0"}}
    try:
        resp = httpx.get(api_url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return "Repository or branch not found. If the default branch is 'master', try: list_github_repo(repo_url, branch='master')"
        if resp.status_code == 403:
            return "GitHub API rate limit exceeded (60 req/hr for unauthenticated requests). Wait a minute and try again."
        if resp.status_code != 200:
            return "GitHub API error {}: {}".format(resp.status_code, resp.text[:200])

        data = resp.json()
        truncated_by_api = data.get("truncated", False)

        # Filter and collect paths
        paths = []
        for item in data.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            # Skip noise directories
            parts = path.split("/")
            if any(p in _NOISE_DIRS for p in parts):
                continue
            paths.append(path)

        if not paths:
            return "No files found in repository {}/{} on branch '{}'.".format(owner, repo, branch)

        # Sort for readability
        paths.sort()

        truncated = False
        if len(paths) > _MAX_PATHS:
            paths = paths[:_MAX_PATHS]
            truncated = True

        result = "\\n".join(paths)
        if truncated or truncated_by_api:
            result += "\\n\\n[Truncated: {} files shown of {} total. The repository is large — consider asking the operator for specific file paths.]".format(len(paths), "many" if truncated_by_api else len(paths) + 1)

        return result

    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException, json.JSONDecodeError) as e:
        return "Error listing GitHub repository: " + str(e)
'''


def build_list_github_repo_source() -> str:
    """Generate list_github_repo source code.

    Unlike propose_tool and fetch_docs, this tool does not call the Delta
    backend — it calls the GitHub API directly. No agent_id or service
    token is needed.
    """
    return _LIST_GITHUB_REPO_TOOL_TEMPLATE


LIST_GITHUB_REPO_SCHEMA = {
    "title": "ListGithubRepoInput",
    "type": "object",
    "properties": {
        "repo_url": {
            "type": "string",
            "description": "GitHub repository URL (e.g., 'https://github.com/CrowdStrike/falconpy')",
        },
        "branch": {
            "type": "string",
            "description": "Branch name (default: 'main'). Try 'master' if the repo uses that instead.",
            "default": "main",
        },
    },
    "required": ["repo_url"],
}

LIST_GITHUB_REPO_DESCRIPTION = (
    "List the file structure of a public GitHub repository. "
    "Returns file paths filtered to relevant source files. "
    "After listing, use fetch_docs to read individual files from "
    "raw.githubusercontent.com (e.g., 'https://raw.githubusercontent.com/owner/repo/main/path/to/file.py'). "
    "Only public repositories are supported."
)
