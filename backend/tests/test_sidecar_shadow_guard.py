"""Tests for the pip-sidecar stdlib/critical-module shadowing guard (F3).

The sidecar lives at <repo>/pip-sidecar/app.py — a hyphenated directory,
not importable as a package — so the module is loaded by file path. The
install endpoint is exercised against a temp PIP_TARGET with pip mocked:
the mock "installs" fake module files into whatever --target it is given.
"""

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import shared.service_token as st

_SIDECAR_APP = Path(__file__).resolve().parents[2] / "pip-sidecar" / "app.py"


@pytest.fixture(scope="module")
def sidecar():
    """Load the pip-sidecar app module by file path."""
    spec = importlib.util.spec_from_file_location("delta_pip_sidecar_app", _SIDECAR_APP)
    module = importlib.util.module_from_spec(spec)
    sys.modules["delta_pip_sidecar_app"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pip_target(tmp_path, sidecar, monkeypatch):
    """Redirect the sidecar's PIP_TARGET to a temp dir."""
    target = tmp_path / "extra-packages"
    target.mkdir()
    monkeypatch.setattr(sidecar, "PIP_TARGET", str(target))
    return target


@pytest.fixture(autouse=True)
def _sidecar_token():
    """Pin the sidecar token in the shared loader cache for auth."""
    st._SERVICE_TOKENS["sidecar"] = "test-sidecar-token"
    st._SERVICE_TOKENS_LOADED_AT["sidecar"] = time.monotonic()
    yield
    st._SERVICE_TOKENS.pop("sidecar", None)
    st._SERVICE_TOKENS_LOADED_AT.pop("sidecar", None)


def _client(sidecar):
    return AsyncClient(
        transport=ASGITransport(app=sidecar.app),
        base_url="http://test",
        headers={"X-Service-Token": "test-sidecar-token"},
    )


def _fake_pip_that_installs(files_by_package):
    """Mock _run_pip_async: for each requested package, write its fake module
    files into the --target directory pip was given."""

    async def _run(args):
        # args: ["install", "--target", <dir>, pkg1, pkg2, ...]
        target = Path(args[2])
        for pkg in args[3:]:
            written = []
            for rel, content in files_by_package.get(pkg.split("==")[0], []):
                p = target / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
                written.append(rel)
            # Write the dist-info RECORD so ownership attribution works
            name, _, version = pkg.partition("==")
            dist_info = target / f"{name}-{version or '1.0'}.dist-info"
            dist_info.mkdir(exist_ok=True)
            record_lines = [f"{rel},," for rel in written] + [f"{dist_info.name}/METADATA,,"]
            (dist_info / "RECORD").write_text("\n".join(record_lines) + "\n")

    return AsyncMock(side_effect=_run)


def _write_record(pip_target, dist_name, version, files):
    """Write a dist-info RECORD into a PIP_TARGET fixture so existing-module
    ownership attribution works (the guard reads RECORDs, not directory names)."""
    dist_info = pip_target / f"{dist_name}-{version}.dist-info"
    dist_info.mkdir(exist_ok=True)
    lines = [f"{f},," for f in files] + [f"{dist_info.name}/METADATA,,"]
    (dist_info / "RECORD").write_text("\n".join(lines) + "\n")


class TestTopLevelModuleNames:
    def test_names(self, sidecar, tmp_path):
        (tmp_path / "requests").mkdir()
        (tmp_path / "requests" / "__init__.py").write_text("")
        (tmp_path / "json.py").write_text("")
        (tmp_path / "json.cpython-312-x86_64-linux-gnu.so").write_text("")
        (tmp_path / "plain.so").write_text("")
        (tmp_path / "some_pkg-1.0.dist-info").mkdir()  # ignored
        (tmp_path / "bin").mkdir()  # no __init__.py — ignored

        names = sidecar._top_level_module_names(str(tmp_path))
        assert names == {"requests", "json", "plain"}


class TestFindShadowingModules:
    def test_stdlib_shadow_detected(self, sidecar, tmp_path):
        (tmp_path / "json.py").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), set(), set(), {}) == ["json"]

    def test_compiled_extension_shadow_detected(self, sidecar, tmp_path):
        (tmp_path / "httpx.cpython-312-x86_64-linux-gnu.so").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), set(), set(), {}) == ["httpx"]

    def test_sitecustomize_detected(self, sidecar, tmp_path):
        (tmp_path / "sitecustomize.py").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), set(), set(), {}) == ["sitecustomize"]

    def test_critical_runtime_module_detected(self, sidecar, tmp_path):
        (tmp_path / "letta").mkdir()
        (tmp_path / "letta" / "__init__.py").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), set(), set(), {}) == ["letta"]

    def test_existing_pip_target_module_detected(self, sidecar, tmp_path):
        (tmp_path / "mymodule.py").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), {"mymodule"}, set(), {}) == ["mymodule"]

    def test_normal_package_not_flagged(self, sidecar, tmp_path):
        (tmp_path / "requests").mkdir()
        (tmp_path / "requests" / "__init__.py").write_text("")
        assert sidecar._find_shadowing_modules(str(tmp_path), set(), set(), {}) == []

    def test_requested_package_reinstall_allowed(self, sidecar, tmp_path):
        """A requested package's own module may replace its installed copy."""
        (tmp_path / "requests").mkdir()
        (tmp_path / "requests" / "__init__.py").write_text("")
        result = sidecar._find_shadowing_modules(str(tmp_path), {"requests"}, {"requests"}, {"requests": "requests"})
        assert result == []

    def test_hijacking_installed_module_flagged(self, sidecar, tmp_path):
        """Replacing a module owned by a non-requested package is flagged —
        whether the new copy comes from a dependency or the requested package."""
        (tmp_path / "goodpkg").mkdir()
        (tmp_path / "goodpkg" / "__init__.py").write_text("")
        result = sidecar._find_shadowing_modules(str(tmp_path), {"goodpkg"}, {"otherpkg"}, {"goodpkg": "goodpkg"})
        assert result == ["goodpkg"]


class TestInstallEndpointGuard:
    async def test_stdlib_shadow_rejected_nothing_landed(self, sidecar, pip_target, monkeypatch):
        """A package shipping a top-level json.py → 400, PIP_TARGET untouched."""
        monkeypatch.setattr(
            sidecar,
            "_run_pip_async",
            _fake_pip_that_installs({"evilpkg": [("json.py", "# shadow"), ("evilpkg/__init__.py", "")]}),
        )
        async with _client(sidecar) as client:
            resp = await client.post("/packages/install", json={"packages": ["evilpkg==1.0"]})
        assert resp.status_code == 400
        assert "json" in resp.json()["detail"]
        assert list(pip_target.iterdir()) == []  # nothing landed

    async def test_other_package_shadowing_existing_module_rejected(self, sidecar, pip_target, monkeypatch):
        """A package shipping a module that already exists in PIP_TARGET → 400,
        and the existing module is not clobbered."""
        (pip_target / "goodpkg").mkdir()
        (pip_target / "goodpkg" / "__init__.py").write_text("old")

        monkeypatch.setattr(
            sidecar,
            "_run_pip_async",
            _fake_pip_that_installs({"otherpkg": [("goodpkg/__init__.py", "hijack"), ("otherpkg/__init__.py", "")]}),
        )
        async with _client(sidecar) as client:
            resp = await client.post("/packages/install", json={"packages": ["otherpkg==1.0"]})
        assert resp.status_code == 400
        assert "goodpkg" in resp.json()["detail"]
        assert (pip_target / "goodpkg" / "__init__.py").read_text() == "old"

    async def test_allow_shadowing_override_permits(self, sidecar, pip_target, monkeypatch):
        monkeypatch.setattr(
            sidecar,
            "_run_pip_async",
            _fake_pip_that_installs({"evilpkg": [("json.py", "# shadow")]}),
        )
        async with _client(sidecar) as client:
            resp = await client.post(
                "/packages/install",
                json={"packages": ["evilpkg==1.0"], "allow_shadowing": True},
            )
        assert resp.status_code == 200
        assert (pip_target / "json.py").exists()

    async def test_normal_package_installs(self, sidecar, pip_target, monkeypatch):
        monkeypatch.setattr(
            sidecar,
            "_run_pip_async",
            _fake_pip_that_installs({"requests": [("requests/__init__.py", "")]}),
        )
        async with _client(sidecar) as client:
            resp = await client.post("/packages/install", json={"packages": ["requests==2.32.0"]})
        assert resp.status_code == 200
        assert (pip_target / "requests" / "__init__.py").exists()

    async def test_reinstall_replaces_not_nests(self, sidecar, pip_target, monkeypatch):
        """Reinstalling an existing package replaces it — no shutil.move nesting."""
        (pip_target / "requests").mkdir()
        (pip_target / "requests" / "__init__.py").write_text("v1")
        _write_record(pip_target, "requests", "2.32.0", ["requests/__init__.py"])

        monkeypatch.setattr(
            sidecar,
            "_run_pip_async",
            _fake_pip_that_installs({"requests": [("requests/__init__.py", "v2")]}),
        )
        async with _client(sidecar) as client:
            resp = await client.post("/packages/install", json={"packages": ["requests==2.32.4"]})
        assert resp.status_code == 200
        assert (pip_target / "requests" / "__init__.py").read_text() == "v2"
        # Not nested: requests/requests/__init__.py must not exist
        assert not (pip_target / "requests" / "requests").exists()
