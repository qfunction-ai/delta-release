"""read_github_file — Letta tool that lets agents read specific files from GitHub repos.

When the agent_tool_creation setting is enabled for a user, this tool
is attached to their agents alongside propose_tool, fetch_docs, and
list_github_repo. The agent calls it with a GitHub repo URL and file
path to read the raw file content from raw.githubusercontent.com, with
optional line range support for large files.

No authentication is needed — the tool calls raw.githubusercontent.com
directly for public repositories (60 req/hr unauthenticated rate limit).
"""

_READ_GITHUB_FILE_TOOL_TEMPLATE = '''def read_github_file(repo_url: str, file_path: str, branch: str = "main", start_line: int = 0, end_line: int = 0) -> str:
    """Read a specific file from a GitHub repository. Use this after list_github_repo to read source code, READMEs, and examples.

    Only public GitHub repositories are supported. The tool returns file content
    with line numbers. For large files, use start_line and end_line to read specific
    sections. Without line ranges, the file is truncated at 50000 chars — the output
    includes the total line count so you know what range to request next.

    Args:
        repo_url: GitHub repository URL (e.g., "https://github.com/tenable/pytenable")
        file_path: Path to the file within the repo (e.g., "pytenable/nessus/scans.py")
        branch: Branch name (default: "main"). Try "master" if the repo uses that instead.
        start_line: Start line number (1-indexed). 0 means start from the beginning.
        end_line: End line number (1-indexed). 0 means read to end (max 1000 lines from start_line).
    """
    import httpx, re

    # Parse the GitHub repo URL to extract owner and repo
    match = re.match(r"https?://github\\.com/([^/]+)/([^/]+)/?", repo_url)
    if not match:
        return "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
    owner = match.group(1)
    repo = match.group(2)

    # Construct the raw.githubusercontent.com URL
    raw_url = "https://raw.githubusercontent.com/{}/{}/{}/{}".format(owner, repo, branch, file_path)

    headers = {"Accept": "text/plain", "User-Agent": "Mozilla/5.0"}
    try:
        resp = httpx.get(raw_url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return "File not found. Check the file path and branch name. If the default branch is 'master', try: read_github_file(repo_url, file_path, branch='master')"
        if resp.status_code == 403:
            return "GitHub API rate limit exceeded (60 req/hr for unauthenticated requests). Wait a minute and try again."
        if resp.status_code != 200:
            return "GitHub raw content error {}: {}".format(resp.status_code, resp.text[:200])

        content = resp.text
        lines = content.split("\\n")
        total_lines = len(lines)

        # Check for binary content (null bytes or high ratio of non-printable chars)
        if "\\x00" in content:
            return "This appears to be a binary file. read_github_file only supports text files."

        _MAX_CHARS = 50000
        _MAX_LINES_WITH_RANGE = 1000

        # Apply line range if specified
        if start_line > 0 or end_line > 0:
            s = max(1, start_line) - 1  # Convert to 0-indexed
            e = end_line if end_line > 0 else total_lines
            e = min(e, s + _MAX_LINES_WITH_RANGE)  # Max 1000 lines per range
            e = min(e, total_lines)
            selected = lines[s:e]
            header = "File: {} ({} lines total)\\nShowing lines {}-{}\\n\\n".format(file_path, total_lines, s + 1, e)
            body = "\\n".join("{:6d}  {}".format(s + 1 + i, line) for i, line in enumerate(selected))
            return header + body

        # No line range — return whole file, truncated at 50K chars
        if len(content) <= _MAX_CHARS:
            header = "File: {} ({} lines)\\n\\n".format(file_path, total_lines)
            body = "\\n".join("{:6d}  {}".format(i + 1, line) for i, line in enumerate(lines))
            return header + body

        # Truncate at 50K chars
        truncated = content[:_MAX_CHARS]
        trunc_lines = truncated.split("\\n")
        header = "File: {} ({} lines total)\\n".format(file_path, total_lines)
        header += "Showing lines 1-{} (truncated at {} chars — use start_line and end_line to read specific sections)\\n\\n".format(len(trunc_lines), _MAX_CHARS)
        body = "\\n".join("{:6d}  {}".format(i + 1, line) for i, line in enumerate(trunc_lines))
        return header + body

    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
        return "Error reading GitHub file: " + str(e)
'''


def build_read_github_file_source() -> str:
    """Generate read_github_file source code.

    Like list_github_repo, this tool does not call the Delta backend —
    it calls raw.githubusercontent.com directly. No agent_id or service
    token is needed.
    """
    return _READ_GITHUB_FILE_TOOL_TEMPLATE


READ_GITHUB_FILE_SCHEMA = {
    "title": "ReadGithubFileInput",
    "type": "object",
    "properties": {
        "repo_url": {
            "type": "string",
            "description": "GitHub repository URL (e.g., 'https://github.com/tenable/pytenable')",
        },
        "file_path": {
            "type": "string",
            "description": "Path to the file within the repo (e.g., 'pytenable/nessus/scans.py')",
        },
        "branch": {
            "type": "string",
            "description": "Branch name (default: 'main'). Try 'master' if the repo uses that instead.",
            "default": "main",
        },
        "start_line": {
            "type": "integer",
            "description": "Start line number (1-indexed). 0 means start from the beginning.",
            "default": 0,
        },
        "end_line": {
            "type": "integer",
            "description": "End line number (1-indexed). 0 means read to end (max 1000 lines from start_line).",
            "default": 0,
        },
    },
    "required": ["repo_url", "file_path"],
}

READ_GITHUB_FILE_DESCRIPTION = (
    "Read a specific file from a public GitHub repository. "
    "Returns file content with line numbers. For large files, use start_line and "
    "end_line to read specific sections. Use after list_github_repo to read source "
    "code, READMEs, and examples. Only public repositories are supported."
)
