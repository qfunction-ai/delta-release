"""Pip sidecar — lightweight FastAPI service for managing Python packages.

Runs pip natively against a shared volume (/extra-packages) that is also
mounted in the Letta container. No Docker socket, no exec, no special privileges.

All mutating endpoints require X-Service-Token header for service-to-service auth.
"""

import asyncio
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, field_validator
from shared.service_token import make_verify_service_token

verify_sidecar_service_token = make_verify_service_token("sidecar")

# Configure logging
LOG_DIR = "/data/logs"
LOG_FILE = os.path.join(LOG_DIR, "pip-sidecar.log")

# Console handler — ensures `docker logs` shows output
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
console_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

app = FastAPI(title="Delta Pip Sidecar")

PIP_TARGET = "/extra-packages"

# ---------------------------------------------------------------------------
# F3 — stdlib/critical-module shadowing guard (D-2b interim)
#
# PYTHONPATH puts /extra-packages ahead of the standard library in the Letta
# server process, so a module named `json` or `httpx` in an installed package
# shadows the real one. Install into a temp target first, scan it, and only
# then move the contents in. The structural fix (per-tool venv / path
# demotion) is Phase 2; this is the Delta-side interim guard.
# ---------------------------------------------------------------------------

# sitecustomize/usercustomize are not in sys.stdlib_module_names, but Python
# imports sitecustomize automatically at every interpreter start when it is
# anywhere on sys.path — a package shipping one runs code in the Letta server
# with nothing importing it.
_AUTO_IMPORT_MODULES = {"sitecustomize", "usercustomize"}

# Modules the Letta server itself runs on — shadowing any of these hijacks
# the server process.
_CRITICAL_RUNTIME_MODULES = {
    "letta",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "httpx",
    "uvicorn",
    "starlette",
    "openai",
    "redis",
}

_GUARDED_MODULE_NAMES = (
    frozenset(sys.stdlib_module_names)
    | _AUTO_IMPORT_MODULES
    | _CRITICAL_RUNTIME_MODULES
)


def _top_level_module_names(directory: str) -> set[str]:
    """Extract importable top-level module names from a pip target directory.

    Matches package directories, .py files, and compiled extensions by stem
    (json.cpython-312-x86_64-linux-gnu.so shadows json). dist-info/bin and
    other non-importable entries are ignored.
    """
    names: set[str] = set()
    root = Path(directory)
    if not root.is_dir():
        return names
    for entry in root.iterdir():
        if entry.is_dir():
            # Package directory (has __init__.py) — its name is importable
            if (entry / "__init__.py").exists():
                names.add(entry.name)
        elif entry.is_file():
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif entry.name.endswith(".so"):
                # Strip the platform/ABI suffix: everything before the first dot
                names.add(entry.name.split(".")[0])
    return names


def _find_shadowing_modules(
    directory: str,
    existing: set[str],
    requested: set[str],
    existing_ownership: dict[str, str],
) -> list[str]:
    """Return sorted module names in `directory` that must not land in PIP_TARGET.

    A name is shadowing when it hits the stdlib/critical/auto-import guard
    list, or when it collides with an already-installed module whose owning
    package is not among the requested packages. The owner that matters is
    the EXISTING copy's owner: replacing a module owned by a requested
    package is a reinstall/upgrade; replacing anything else — whether the
    new copy came from a dependency or from the requested package itself —
    hijacks an installed module.
    """
    shadowing = []
    for name in _top_level_module_names(directory):
        if name in _GUARDED_MODULE_NAMES:
            shadowing.append(name)
        elif name in existing:
            owner = existing_ownership.get(name)
            if owner is None or owner not in requested:
                shadowing.append(name)
    return sorted(set(shadowing))


def _dist_module_ownership(directory: str) -> dict[str, str]:
    """Map top-level module name → normalized dist name, via dist-info RECORD files.

    Needed to distinguish a legitimate reinstall (the requested package's own
    modules already exist in PIP_TARGET) from a dependency shipping a module
    that shadows something already installed.
    """
    ownership: dict[str, str] = {}
    root = Path(directory)
    for dist_info in root.glob("*.dist-info"):
        m = re.match(r"^(.+?)-(\d.*)\.dist-info$", dist_info.name)
        if not m:
            continue
        dist = _normalize_pkg_name(m.group(1))
        record = dist_info / "RECORD"
        if not record.exists():
            continue
        try:
            with open(record, newline="") as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    top = row[0].split("/", 1)[0]
                    if top.endswith(".py"):
                        top = top[:-3]
                    elif top.endswith(".so"):
                        top = top.split(".")[0]
                    if top and top not in (".", ".."):
                        ownership[top] = dist
        except OSError:
            continue
    return ownership


# Package name validation — base pattern composed into install and name-only variants
# Install allows: package==version (exact version pin only, no >=, <=, ~=, etc.)
_PKG_NAME_PATTERN = r"[a-zA-Z0-9_][a-zA-Z0-9_.\-]*"
_PKG_NAME_RE = re.compile(rf"^{_PKG_NAME_PATTERN}$")
_PKG_SPEC_RE = re.compile(rf"^{_PKG_NAME_PATTERN}(==[a-zA-Z0-9_.]+)?$")


def _normalize_pkg_name(name: str) -> str:
    """Normalize a package name for comparison (lowercase, hyphens/dots → underscores)."""
    return name.lower().replace("-", "_").replace(".", "_")


class InstallRequest(BaseModel):
    packages: list[str]
    # Explicit admin override for the shadowing guard (F3). When True, the
    # install bypasses the stdlib/critical-module checks and installs directly.
    allow_shadowing: bool = False

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one package is required")
        for pkg in v:
            if not _PKG_SPEC_RE.match(pkg):
                raise ValueError(f"Invalid package specifier: {pkg}")
        return v


async def _run_pip_async(args: list[str]) -> subprocess.CompletedProcess:
    """Run a pip command asynchronously. Raises HTTPException on failure.

    Uses asyncio.create_subprocess_exec instead of subprocess.run to avoid
    blocking the event loop during pip operations (which can take minutes).
    """
    proc = await asyncio.create_subprocess_exec(
        "pip",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(
            status_code=504,
            detail=f"pip command timed out after 120s: pip {' '.join(args)}",
        )

    result = subprocess.CompletedProcess(
        args=["pip"] + args,
        returncode=proc.returncode,
        stdout=stdout.decode() if stdout else "",
        stderr=stderr.decode() if stderr else "",
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=result.stderr.strip() or "pip command failed",
        )
    return result


async def _list_installed_packages_async() -> list[dict] | None:
    """List packages installed in the shared target directory. Returns None on failure."""
    proc = await asyncio.create_subprocess_exec(
        "pip",
        "list",
        "--path",
        PIP_TARGET,
        "--format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None

    if proc.returncode != 0:
        return None
    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError:
        return None


@app.on_event("startup")
async def startup():
    """Create log directory and configure file logging at startup (not import time)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=50 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/packages")
async def list_packages(_auth=Depends(verify_sidecar_service_token)):
    """List packages installed in the shared target directory."""
    packages = await _list_installed_packages_async()
    if packages is None:
        raise HTTPException(status_code=503, detail="Failed to list packages")
    return packages


@app.post("/packages/install")
async def install_packages(
    req: InstallRequest, _auth=Depends(verify_sidecar_service_token)
):
    """Install packages into the shared target directory."""
    if req.allow_shadowing:
        # Explicit admin override — install directly, no shadowing checks
        await _run_pip_async(["install", "--target", PIP_TARGET] + req.packages)
    else:
        # F3: install into a temp target first, scan for shadowing modules,
        # and only then move the contents into PIP_TARGET. Scanning before
        # the move closes the import window a post-install scan leaves, and
        # catches shadowing modules brought in by dependencies, not just the
        # requested package.
        temp_target = tempfile.mkdtemp(prefix="pip-guard-")
        try:
            await _run_pip_async(["install", "--target", temp_target] + req.packages)

            existing = _top_level_module_names(PIP_TARGET)
            requested = {_normalize_pkg_name(p.split("==")[0]) for p in req.packages}
            existing_ownership = _dist_module_ownership(PIP_TARGET)
            shadowing = _find_shadowing_modules(
                temp_target, existing, requested, existing_ownership
            )
            if shadowing:
                root_logger.warning(
                    "Rejected install of %s — would shadow: %s",
                    req.packages,
                    ", ".join(shadowing),
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Install rejected: package(s) would shadow existing or "
                        f"protected modules: {', '.join(shadowing)}. Retry with "
                        f"allow_shadowing=true only if you have verified the source."
                    ),
                )

            # Clean — move the contents into PIP_TARGET. Remove an existing
            # entry of the same name first: shutil.move into an existing
            # directory nests instead of replacing (breaks reinstalls).
            for entry in Path(temp_target).iterdir():
                dst = Path(PIP_TARGET) / entry.name
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                elif dst.exists():
                    dst.unlink()
                shutil.move(str(entry), str(dst))
        finally:
            shutil.rmtree(temp_target, ignore_errors=True)

    # Return the newly installed packages
    all_packages = await _list_installed_packages_async()
    if not all_packages:
        return []

    installed_names = {_normalize_pkg_name(p.split("==")[0]) for p in req.packages}
    return [
        p for p in all_packages if _normalize_pkg_name(p["name"]) in installed_names
    ]


@app.delete("/packages/{package_name}")
async def uninstall_package(
    package_name: str, _auth=Depends(verify_sidecar_service_token)
):
    """Uninstall a package by removing its files from the target directory.

    pip uninstall doesn't support --path/--target, so we remove files manually.
    """
    if not _PKG_NAME_RE.match(package_name):
        raise HTTPException(status_code=400, detail="Invalid package name")

    target = Path(PIP_TARGET)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Package {package_name} not found")

    normalized = _normalize_pkg_name(package_name)
    removed = False
    target_resolved = target.resolve()

    for item in list(target.iterdir()):
        # Path boundary check — ensure the resolved path is within PIP_TARGET
        # to prevent path traversal attacks
        resolved = item.resolve()
        if (
            not str(resolved).startswith(str(target_resolved) + os.sep)
            and resolved != target_resolved
        ):
            logging.getLogger(__name__).warning(
                "Path traversal attempt: %s is outside %s", resolved, target_resolved
            )
            continue

        # Match package directory, .dist-info, or .egg-info
        # e.g., "requests" matches "requests", "requests-2.31.0.dist-info"
        # Split on "-" FIRST (before replacing), then normalize for comparison
        item_name_parts = item.name.lower().split("-")
        item_stem = item_name_parts[0].replace(".", "_")
        if item_stem == normalized:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed = True

    if not removed:
        raise HTTPException(status_code=404, detail=f"Package {package_name} not found")

    return {"status": "uninstalled"}
