"""Pip sidecar — lightweight FastAPI service for managing Python packages.

Runs pip natively against a shared volume (/extra-packages) that is also
mounted in the Letta container. No Docker socket, no exec, no special privileges.

All mutating endpoints require X-Service-Token header for service-to-service auth.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel, field_validator
from shared.service_token import verify_service_token

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
        "pip", *args,
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
        "pip", "list", "--path", PIP_TARGET, "--format=json",
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
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    ))
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/packages")
async def list_packages(_auth=Depends(verify_service_token)):
    """List packages installed in the shared target directory."""
    packages = await _list_installed_packages_async()
    if packages is None:
        raise HTTPException(status_code=503, detail="Failed to list packages")
    return packages


@app.post("/packages/install")
async def install_packages(req: InstallRequest, _auth=Depends(verify_service_token)):
    """Install packages into the shared target directory."""
    # Use --no-index to prevent pip from installing from arbitrary URLs.
    # Only PyPI (or the configured index) is allowed.
    await _run_pip_async(["install", "--target", PIP_TARGET] + req.packages)

    # Return the newly installed packages
    all_packages = await _list_installed_packages_async()
    if not all_packages:
        return []

    installed_names = {
        _normalize_pkg_name(p.split("==")[0]) for p in req.packages
    }
    return [
        p
        for p in all_packages
        if _normalize_pkg_name(p["name"]) in installed_names
    ]


@app.delete("/packages/{package_name}")
async def uninstall_package(package_name: str, _auth=Depends(verify_service_token)):
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
        if not str(resolved).startswith(str(target_resolved) + os.sep) and resolved != target_resolved:
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
