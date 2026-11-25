"""Mount-audit tests for docker-compose token topology (F2).

These parse the compose files and assert the secret-mount topology the
Phase 1 security plan requires:

- The Letta container mounts NEITHER shared_config NOR delta_secrets —
  sandboxed tools cannot read any service token from disk.
- The backend mounts delta_secrets read-write (it generates the tokens).
- pip-sidecar and eval mount delta_secrets read-only and receive their
  token kind via env var only.
- No service except the backend receives DELTA_SERVICE_TOKEN.
- F4: letta_secrets is a distinct volume mounted at /data/letta-secrets in
  letta and /letta-secrets in postgres; the letta command wrapper builds
  the scoped-role URI and exports the encryption key. There is no
  superuser fallback — Delta is fresh-install only.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    with open(REPO_ROOT / name) as f:
        return yaml.safe_load(f)


def _mounts(service):
    return service.get("volumes") or []


def _env(service):
    return service.get("environment") or []


class TestMainCompose:
    def test_letta_has_no_secret_mounts(self):
        """The Letta container must not mount shared_config or delta_secrets."""
        compose = _load("docker-compose.yml")
        mounts = _mounts(compose["services"]["letta"])
        for mount in mounts:
            assert not str(mount).startswith("shared_config:"), (
                f"letta mounts shared_config: {mount} — tools could read the tool-callback token from disk (F2 unmount)"
            )
            assert not str(mount).startswith("delta_secrets:"), (
                f"letta mounts delta_secrets: {mount} — tools could read the eval/sidecar tokens from disk"
            )

    def test_backend_mounts_delta_secrets_rw(self):
        """The backend generates the eval/sidecar tokens — it needs rw."""
        compose = _load("docker-compose.yml")
        mounts = _mounts(compose["services"]["backend"])
        assert any(str(m) == "delta_secrets:/data/secrets" for m in mounts), (
            "backend must mount delta_secrets read-write at /data/secrets"
        )

    def test_sidecar_mounts_delta_secrets_ro(self):
        compose = _load("docker-compose.yml")
        service = compose["services"]["pip-sidecar"]
        mounts = _mounts(service)
        assert any(str(m) == "delta_secrets:/data/secrets:ro" for m in mounts), (
            "pip-sidecar must mount delta_secrets read-only"
        )
        assert not any(str(m).startswith("shared_config:") for m in mounts), (
            "pip-sidecar no longer needs shared_config — its token is on delta_secrets"
        )

    def test_sidecar_env_has_no_tool_callback_token(self):
        """The sidecar must not receive DELTA_SERVICE_TOKEN (tool-callback token)."""
        compose = _load("docker-compose.yml")
        env = _env(compose["services"]["pip-sidecar"])
        for entry in env:
            assert not str(entry).startswith("DELTA_SERVICE_TOKEN="), (
                "pip-sidecar must use DELTA_SIDECAR_SERVICE_TOKEN, not the tool-callback token"
            )

    def test_delta_secrets_volume_declared(self):
        compose = _load("docker-compose.yml")
        assert "delta_secrets" in compose["volumes"]


class TestEvalCompose:
    def test_eval_mounts_delta_secrets_ro(self):
        compose = _load("docker-compose.eval.yml")
        service = compose["services"]["eval"]
        mounts = _mounts(service)
        assert any(str(m) == "delta_secrets:/data/secrets:ro" for m in mounts), (
            "eval must mount delta_secrets read-only"
        )
        assert not any(str(m).startswith("shared_config:") for m in mounts), (
            "eval no longer needs shared_config — its token is on delta_secrets"
        )

    def test_eval_env_has_no_tool_callback_token(self):
        compose = _load("docker-compose.eval.yml")
        env = _env(compose["services"]["eval"])
        for entry in env:
            assert not str(entry).startswith("DELTA_SERVICE_TOKEN="), (
                "eval must use DELTA_EVAL_SERVICE_TOKEN, not the tool-callback token"
            )


class TestF4LettaSecretsTopology:
    """F4: scoped PG role + secrets encryption key via the letta_secrets volume."""

    def test_letta_mounts_letta_secrets(self):
        compose = _load("docker-compose.yml")
        mounts = _mounts(compose["services"]["letta"])
        assert any(str(m) == "letta_secrets:/data/letta-secrets" for m in mounts), (
            "letta must mount letta_secrets at /data/letta-secrets"
        )

    def test_postgres_mounts_letta_secrets(self):
        compose = _load("docker-compose.yml")
        mounts = _mounts(compose["services"]["postgres"])
        assert any(str(m) == "letta_secrets:/letta-secrets" for m in mounts), (
            "postgres must mount letta_secrets at /letta-secrets (initdb writes there)"
        )

    def test_letta_secrets_is_distinct_from_delta_secrets(self):
        compose = _load("docker-compose.yml")
        assert "letta_secrets" in compose["volumes"]
        assert "delta_secrets" in compose["volumes"]
        # Distinct volumes, distinct mount paths in letta — a wrong-mount
        # mistake would give tools the PG password.
        mounts = _mounts(compose["services"]["letta"])
        assert not any(str(m).startswith("delta_secrets:") for m in mounts), "letta must NOT mount delta_secrets"

    def test_letta_wrapper_builds_scoped_uri_and_refuses_without_password(self):
        """The command wrapper reads the password file, builds LETTA_PG_URI
        from it, refuses to start when it is empty (fresh-install only),
        and exports the encryption key."""
        compose = _load("docker-compose.yml")
        letta = compose["services"]["letta"]
        command = letta.get("command") or ""
        command_str = str(command)
        assert "letta_pg_password" in command_str, "wrapper must read the role password"
        assert "LETTA_PG_URI" in command_str, "wrapper must override the PG URI"
        assert "fresh-install only" in command_str, "empty-password refusal must name the fresh-install policy"
        assert "down -v" in command_str, "refusal must tell the user to reinstall from scratch"
        assert "superuser" not in command_str, "no superuser fallback may exist"
        assert "LETTA_ENCRYPTION_KEY" in command_str, "wrapper must export the encryption key"
        assert "letta_encryption_key" in command_str

    def test_letta_env_has_no_pg_uri(self):
        """The letta container must never hold superuser credentials: no
        LETTA_PG_URI in the environment block. The wrapper builds the
        scoped-role URI at runtime."""
        compose = _load("docker-compose.yml")
        env = _env(compose["services"]["letta"])
        for entry in env:
            assert not str(entry).startswith("LETTA_PG_URI="), (
                "letta env must not contain LETTA_PG_URI (superuser credential leak)"
            )

    def test_letta_env_has_no_api_base_url(self):
        """G-1: DELTA_API_BASE_URL in the letta env is dead weight — sandboxed
        tools don't inherit container env (v0.16.38). The backend delivers it
        via agent secrets. Leaving it here suggests tools can read it, which
        is how the propose_tool break slipped through two live runs."""
        compose = _load("docker-compose.yml")
        env = _env(compose["services"]["letta"])
        for entry in env:
            assert not str(entry).startswith("DELTA_API_BASE_URL="), (
                "DELTA_API_BASE_URL belongs in the backend env (DELTA_BACKEND_URL), "
                "delivered to tools via agent secrets — not in the letta env"
            )

    def test_tool_templates_have_no_localhost_fallback(self):
        """G-1: the tool templates must fail loudly when the base URL is
        missing, not fall back to localhost (which turned a delivery failure
        into a confusing 'connection refused' inside the letta container)."""
        for path in (
            REPO_ROOT / "backend" / "app" / "tools" / "propose_tool.py",
            REPO_ROOT / "backend" / "app" / "docs" / "fetch_docs_tool.py",
        ):
            source = path.read_text()
            assert "localhost:8000" not in source, f"{path.name} must not default to localhost"
            assert "DELTA_API_BASE_URL not configured" in source, f"{path.name} must fail loudly on a missing base URL"

    def test_initdb_creates_role_and_key(self):
        """The initdb scripts exist and are executable (fresh installs)."""
        import stat

        for name in ("03-letta-role.sh", "04-letta-encryption-key.sh"):
            path = REPO_ROOT / "postgres" / "initdb" / name
            assert path.exists(), f"missing initdb script: {name}"
            mode = stat.S_IMODE(path.stat().st_mode)
            assert mode & stat.S_IXUSR, f"{name} must be executable"

    def test_initdb_revokes_connect_on_delta(self):
        """P-1: the scoped role must not reach Delta's own database."""
        initdb_03 = (REPO_ROOT / "postgres" / "initdb" / "03-letta-role.sh").read_text()
        assert "REVOKE CONNECT ON DATABASE delta FROM PUBLIC" in initdb_03
        assert "GRANT CONNECT ON DATABASE delta TO delta" in initdb_03
        assert "GRANT CONNECT ON DATABASE delta TO letta" not in initdb_03


class TestF5LettaPortUnpublished:
    """F5: the Letta API is not published to the host by default."""

    def test_letta_has_no_ports(self):
        compose = _load("docker-compose.yml")
        ports = compose["services"]["letta"].get("ports") or []
        assert ports == [], (
            f"letta must not publish ports by default (F5): {ports} — use docker-compose.debug.yml for debugging"
        )

    def test_debug_override_republishes_localhost_only(self):
        compose = _load("docker-compose.debug.yml")
        ports = compose["services"]["letta"].get("ports") or []
        assert any(str(p).startswith("127.0.0.1:8283") for p in ports), (
            "debug override must republish 8283 on 127.0.0.1 only"
        )


class TestInitVolumesService:
    """C-2 (release check): named-volume roots are root:root 755 by default;
    an init service must chown them to the writing users before any
    consumer starts."""

    def _service(self, name="init-volumes", file="docker-compose.yml"):
        compose = _load(file)
        return compose["services"][name]

    def test_init_volumes_exists_and_is_hardened(self):
        svc = self._service()
        assert svc["user"] == "root", "the chown requires root"
        assert set(svc.get("cap_add") or []) == {"CHOWN", "FOWNER", "DAC_OVERRIDE"}, (
            "chown capabilities + DAC_OVERRIDE (live-tested: root without "
            "DAC_OVERRIDE cannot stat a fresh VirtioFS volume dir)"
        )
        assert (svc.get("cap_drop") or []) == ["ALL"]
        assert svc.get("network_mode") == "none", "no network needed"
        assert svc.get("restart") == "no", "one-shot"

    def test_init_volumes_chowns_all_three_volumes(self):
        command = str(self._service()["command"])
        # delta_secrets → backend appuser (1000), 0700
        assert "chown 1000:1000 /data/secrets" in command
        assert "chmod 0700 /data/secrets" in command
        # letta_secrets → postgres (999), group 1000, 0770 — and the FILES
        # are pre-created (setgid doesn't survive the VirtioFS mount layer;
        # redirection into a pre-owned file preserves ownership instead)
        assert "chown 999:1000 /letta-secrets" in command
        assert "chmod 0770 /letta-secrets" in command
        assert "[ -e /letta-secrets/letta_pg_password ] || touch" in command
        assert "[ -e /letta-secrets/letta_encryption_key ] || touch" in command
        assert "chown 999:1000 /letta-secrets/letta_pg_password" in command
        assert "chmod 640 /letta-secrets/letta_pg_password" in command
        assert "letta_encryption_key" in command  # chowned/touched together with the password file
        # server_password → letta wrapper (1000), 0750
        assert "chown 1000:1000 /data/letta-secrets/server_password" in command
        assert "chmod 0750 /data/letta-secrets/server_password" in command
        # All three volumes mounted
        mounts = _mounts(self._service())
        assert any(str(m).startswith("delta_secrets:") for m in mounts)
        assert any(str(m).startswith("letta_secrets:") for m in mounts)
        assert any(str(m).startswith("letta_server_password:") for m in mounts)

    def test_init_volumes_fails_fast(self):
        """S-1.4: `set -e` and explicit { …; } grouping — a failure at any
        step stops the service instead of continuing to the chown three
        lines later."""
        command = str(self._service()["command"])
        assert "set -e" in command
        assert "{ [ -e /letta-secrets/letta_pg_password ] || touch" in command
        assert "{ [ -e /letta-secrets/letta_encryption_key ] || touch" in command

    def test_all_secret_volume_consumers_depend_on_init(self):
        compose = _load("docker-compose.yml")
        for name in ("backend", "postgres", "letta", "pip-sidecar"):
            depends = compose["services"][name].get("depends_on") or {}
            assert "init-volumes" in depends, (
                f"{name} must depend on init-volumes (condition: service_completed_successfully)"
            )
            assert depends["init-volumes"] == {"condition": "service_completed_successfully"}

    def test_eval_depends_on_init(self):
        compose = _load("docker-compose.eval.yml")
        depends = compose["services"]["eval"].get("depends_on") or {}
        assert "init-volumes" in depends, "eval reads delta_secrets — must wait for init"

    def test_init_volumes_never_deletes_secret_files(self):
        """L-1 (release check 3): init-volumes runs on EVERY compose up
        (compose restarts exited one-shots). An rm/truncate here would wipe
        the encryption key and PG password on every restart — the wrapper
        would mint a new key over existing encrypted data and silently
        fall back to the superuser. Static regression guard."""
        command = str(self._service()["command"])
        assert "rm " not in command.replace("mkdir", ""), "init-volumes must not remove anything on /letta-secrets"
        assert " > /letta-secrets" not in command, "init-volumes must not truncate secret files with redirection"

    def test_letta_wrapper_has_sentinel_guards(self):
        """L-1 defense in depth: the wrapper refuses to mint a second
        encryption key / server password once a sentinel exists. (No PG
        password sentinel: with no superuser fallback there is nothing to
        distinguish "not migrated yet" from "lost" — an empty password is
        always a hard refusal.)"""
        compose = _load("docker-compose.yml")
        command = str(compose["services"]["letta"]["command"])
        for secret in ("letta_encryption_key", "password"):
            assert f"{secret}.sentinel" in command, f"missing sentinel for {secret}"
        assert "letta_pg_password.sentinel" not in command, (
            "the PG password sentinel is upgrade-path machinery — removed"
        )
        assert command.count("exit 1") >= 3, "PG refusal + each sentinel must be able to refuse to start"

    def test_secret_files_mode_640_not_644(self):
        """With the setgid group granting read to 1000, files don't need
        world-read."""

        initdb_03 = (REPO_ROOT / "postgres" / "initdb" / "03-letta-role.sh").read_text()
        assert "chmod 640 /letta-secrets/letta_pg_password" in initdb_03
        assert "chmod 644" not in initdb_03
        initdb_04 = (REPO_ROOT / "postgres" / "initdb" / "04-letta-encryption-key.sh").read_text()
        assert "chmod 640 /letta-secrets/letta_encryption_key" in initdb_04
        assert "chmod 644" not in initdb_04
        compose = _load("docker-compose.yml")
        command = str(compose["services"]["letta"]["command"])
        assert "chmod 640 /data/letta-secrets/server_password/password" in command
        assert "chmod 644" not in command
