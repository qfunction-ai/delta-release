"""Release-only compose regression tests (delta-release repo).

These assertions are deliberately NOT in test_compose_security.py: that
file syncs from the delta repo, which keeps the initdb bind mount. The
release bakes initdb into the postgres image instead (postgres/Dockerfile:
COPY initdb/ + dos2unix for Windows CRLF checkouts) — release main commit
37a5403 removed the bind mount, and a sync must not silently re-add it.

Runs on the CI runner (reads docker-compose.yml via the repo root), not
inside the backend container.
"""

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
_COMPOSE = _REPO / "docker-compose.yml"
_PG_DOCKERFILE = _REPO / "postgres" / "Dockerfile"


def _compose():
    with open(_COMPOSE) as f:
        return yaml.safe_load(f)


class TestInitdbBaked:
    """The postgres image is the only initdb path — no bind mount."""

    def test_postgres_has_no_initdb_bind_mount(self):
        compose = _compose()
        mounts = compose["services"]["postgres"].get("volumes") or []
        offenders = [m for m in mounts if "/docker-entrypoint-initdb.d" in str(m).split(":")]
        assert not offenders, (
            "postgres must not bind-mount ./postgres/initdb — it is baked "
            f"into the image (postgres/Dockerfile). Found: {offenders}"
        )

    def test_postgres_image_bakes_initdb(self):
        text = _PG_DOCKERFILE.read_text()
        assert "COPY initdb/" in text, "postgres/Dockerfile must bake the initdb scripts"
        assert "dos2unix" in text, "postgres/Dockerfile must normalize Windows CRLF line endings"
