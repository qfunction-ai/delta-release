"""Compose topology tests for the Letta server-password plumbing.

Split from test_letta_server_password.py: these read docker-compose.yml via
the repo root (Path(__file__).resolve().parents[2]), so they run on the CI
runner, not inside the backend container (where parents[2] is / and the
compose files don't exist). The unit tests in the parent file import app.*
and stay in the container suite.
"""

from pathlib import Path

import yaml

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _compose():
    with open(_COMPOSE) as f:
        return yaml.safe_load(f)


class TestComposePasswordTopology:
    """Adoption item 1: wrapper generates the password; backend mounts only
    the dedicated password volume."""

    def test_wrapper_generates_server_password(self):
        compose = _compose()
        command = str(compose["services"]["letta"]["command"])
        assert "server_password/password" in command, "wrapper must generate the password"
        assert "LETTA_SERVER_PASSWORD" in command, "wrapper must export it"

    def test_backend_mounts_password_volume_ro(self):
        compose = _compose()
        mounts = compose["services"]["backend"].get("volumes") or []
        assert any(str(m) == "letta_server_password:/data/letta-secrets/server_password:ro" for m in mounts), (
            "backend must mount ONLY the password volume, read-only"
        )
        assert not any(str(m).startswith("letta_secrets:") for m in mounts), (
            "backend must NOT mount the full letta_secrets volume (PG password + encryption key)"
        )

    def test_letta_mounts_password_volume_rw(self):
        compose = _compose()
        mounts = compose["services"]["letta"].get("volumes") or []
        assert any(str(m) == "letta_server_password:/data/letta-secrets/server_password" for m in mounts), (
            "letta must mount the password volume read-write (it generates the password)"
        )
        assert "letta_server_password" in compose["volumes"]
