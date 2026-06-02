"""Log line parsers for each service.

Each parser takes a raw log line and returns a dict with:
  timestamp, level, module, message

Or None if the line can't be parsed.
"""

import re
from datetime import datetime

# Standard Python logging format: 2026-04-25 14:48:10,339 INFO [app.main] Application startup complete
PYTHON_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"\[([^\]]+)\]\s+"
    r"(.*)$"
)

# PostgreSQL log format: 2026-04-25 14:48:10.339 UTC [123] LOG:  message
# Or: 2026-04-25 14:48:10.339 UTC [123] ERROR:  message
# Or: 2026-04-25 14:48:10.339 UTC [123] WARNING:  message
POSTGRES_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+\w+\s+\[(\d+)\]\s+"
    r"(LOG|ERROR|WARNING|FATAL|PANIC|DETAIL|HINT|CONTEXT|STATEMENT|INFO):\s+"
    r"(.*)$"
)

# Letta logs are varied — try Python format first, then fall back to timestamped lines
# Common Letta format: INFO:     Started server process [1]
# Or: 2026-04-25 14:48:10 - letta.server.server - INFO - message
LETTA_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*-\s*"
    r"([^-]+)\s*-\s*"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*-\s*"
    r"(.*)$"
)

# Uvicorn-style: INFO:     Uvicorn running on http://0.0.0.0:8000
UVICORN_RE = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):\s+(.*)$")


def parse_python_line(line: str) -> dict | None:
    """Parse a standard Python logging format line."""
    m = PYTHON_RE.match(line)
    if not m:
        return None
    ts_str, level, module, message = m.groups()

    # Skip verbose SQLAlchemy engine logs (query echoes)
    if module.startswith("sqlalchemy.engine") or module.startswith("sqlalchemy.pool"):
        if level in ("DEBUG", "INFO"):
            return None

    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        ts = None
    return {
        "timestamp": ts.isoformat() if ts else ts_str,
        "level": level,
        "module": module,
        "message": message,
    }


def parse_postgres_line(line: str) -> dict | None:
    """Parse a PostgreSQL log line."""
    m = POSTGRES_RE.match(line)
    if not m:
        return None
    ts_str, pid, pg_level, message = m.groups()
    # Map Postgres levels to standard levels
    level_map = {
        "LOG": "INFO",
        "ERROR": "ERROR",
        "WARNING": "WARNING",
        "FATAL": "ERROR",
        "PANIC": "CRITICAL",
        "DETAIL": "DEBUG",
        "HINT": "DEBUG",
        "CONTEXT": "DEBUG",
        "STATEMENT": "DEBUG",
        "INFO": "INFO",
    }
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        ts = None
    return {
        "timestamp": ts.isoformat() if ts else ts_str,
        "level": level_map.get(pg_level, "INFO"),
        "module": f"postgres[{pid}]",
        "message": message,
    }


def parse_letta_line(line: str) -> dict | None:
    """Parse a Letta log line. Tries multiple formats."""
    # Try Python format first (Letta uses Python logging internally)
    result = parse_python_line(line)
    if result:
        result["module"] = f"letta.{result['module']}" if result["module"] != "letta" else result["module"]
        return result

    # Try Letta-specific format
    m = LETTA_RE.match(line)
    if m:
        ts_str, module, level, message = m.groups()
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            ts = None
        return {
            "timestamp": ts.isoformat() if ts else ts_str,
            "level": level,
            "module": f"letta.{module.strip()}",
            "message": message,
        }

    # Try uvicorn-style (no timestamp)
    m = UVICORN_RE.match(line)
    if m:
        level, message = m.groups()
        return {
            "timestamp": None,
            "level": level,
            "module": "letta",
            "message": message.strip(),
        }

    # Unstructured line — keep it with INFO level
    stripped = line.strip()
    if not stripped:
        return None
    return {
        "timestamp": None,
        "level": "INFO",
        "module": "letta",
        "message": stripped,
    }


def parse_pip_sidecar_line(line: str) -> dict | None:
    """Parse a pip-sidecar log line (Python format)."""
    result = parse_python_line(line)
    if result:
        result["module"] = (
            f"pip-sidecar.{result['module']}" if not result["module"].startswith("pip") else result["module"]
        )
        return result
    # Fallback for unstructured lines
    stripped = line.strip()
    if not stripped:
        return None
    return {
        "timestamp": None,
        "level": "INFO",
        "module": "pip-sidecar",
        "message": stripped,
    }


# Service → parser mapping
PARSERS = {
    "backend": parse_python_line,
    "letta": parse_letta_line,
    "postgres": parse_postgres_line,
    "pip-sidecar": parse_pip_sidecar_line,
}
