import logging
import os
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Shared constants (non-configurable)
SKILL_FILENAME = "SKILL.md"

# Shared volume path for persisting auto-generated secrets across restarts
_SECRETS_DIR = "/data/config"
# Backend-owned secrets (eval/sidecar tokens) — delta_secrets volume, never
# mounted in the Letta container. Backend mounts rw, eval/sidecar mount ro.
_DELTA_SECRETS_DIR = "/data/secrets"

_INSECURE_DEFAULTS = {
    "jwt_secret": "change-me-in-production",
    "credentials_encryption_key": "change-me-in-production",
}

# Patterns that indicate a weak/placeholder secret
_WEAK_SECRET_PATTERNS = [
    "change-me",
    "in-production",
    "do-not-use",
    "placeholder",
    "example",
    "ci-eval",
    "test",
    "dev",
    "debug",
    "local",
    "default",
]

# Minimum length for security-critical secrets
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://delta:delta@localhost:5432/delta"

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption
    credentials_encryption_key: str = ""

    # Letta
    letta_base_url: str = "http://localhost:8283"

    # Letta server password (v0.16.39+ API auth). Empty = no auth (fake-letta
    # CI, pre-0.16.39 pins). Read from the letta_secrets volume file when the
    # env var is unset — see _load_letta_server_password below.
    letta_server_password: str = ""

    # Backend URL as seen from the Letta container (for tool exec env vars)
    backend_url: str = "http://backend:8000"

    # Eval runner
    eval_url: str = "http://eval:8003"
    evals_dir: str = "/app/evals"  # Base directory for eval scenario YAML files (VULN-045)

    # Dev mode — allows insecure defaults and bootstrap user creation
    dev_mode: bool = False

    # Service token for internal service-to-service auth (e.g., credential execution)
    # Scoped to the tool-callback endpoints only (propose/fetch); delivered to
    # agents via the agent secrets channel. See docs/security-fixes-phase1-plan.md F2.
    service_token: str = ""

    # Eval service token — authenticates the eval container against the
    # backend (settings/chat eval endpoints) and the backend against the eval
    # runner. Distinct from the tool-callback token so a leaked eval token
    # can't propose tools or fetch docs, and vice versa.
    eval_service_token: str = ""

    # Sidecar service token — authenticates the backend against pip-sidecar
    # package install/list/uninstall calls. Held only by the backend and the
    # pip-sidecar (delta_secrets volume, never mounted in the Letta container).
    sidecar_service_token: str = ""

    # Setup token for first-user registration (optional)
    # If set, the first user must provide this token when registering.
    # If empty, registration is open (no token required) — only safe in dev mode.
    setup_token: str = ""

    # CORS
    # Comma-separated list of allowed origins for the frontend.
    # Never use "*" in production with credentials=True — it's a CSRF vector.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Rate limiting — default request limit for all endpoints.
    # Dev mode / E2E typically sets this high (e.g. "1000/minute") via
    # DELTA_RATE_LIMIT_DEFAULT to effectively disable limiting.
    rate_limit_default: str = "100/minute"

    # Trusted Host headers — DNS-rebinding defense. A rebinding page carries
    # the attacker's hostname in the Host header, so it is rejected outright.
    # Must include the Compose service name "backend": propose_tool and
    # fetch_docs call the backend by that name from inside the Letta
    # container, and those requests arrive with Host: backend[:port].
    # Hostnames from cors_origins are also trusted (added at startup).
    trusted_hosts: str = "localhost,127.0.0.1,backend"

    # Operational limits (configurable via env vars)
    max_steps: int = 50
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    max_zip_entries: int = 50
    max_file_uncompressed_size: int = 1 * 1024 * 1024  # 1MB per file
    max_zip_total_uncompressed: int = 10 * 1024 * 1024  # 10MB total
    max_lessons_per_workflow: int = 3
    max_lines_per_log_file: int = 5000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "DELTA_"

    def check_security(self) -> None:
        """Warn or fail if secrets are insecure and not in dev mode."""
        issues = []  # Blocking — prevents startup
        warnings = []  # Non-blocking — logged but doesn't prevent startup

        # Reject blank/empty secrets — always, regardless of dev mode
        for key in ("jwt_secret", "credentials_encryption_key"):
            if not getattr(self, key).strip():
                issues.append(f"{key} (must not be empty)")

        for key, insecure_val in _INSECURE_DEFAULTS.items():
            val = getattr(self, key)
            if val == insecure_val:
                issues.append(key)
            # Also check for weak patterns (e.g., "dev-jwt-secret-do-not-use")
            elif any(pat in val.lower() for pat in _WEAK_SECRET_PATTERNS):
                if not self.dev_mode:
                    issues.append(f"{key} (weak pattern detected)")
            if len(val) < _MIN_SECRET_LENGTH and not self.dev_mode:
                if f"{key} (must not be empty)" not in issues and key not in issues:
                    issues.append(f"{key} (too short — minimum {_MIN_SECRET_LENGTH} characters)")

        # Warn about missing setup token — open registration allows anyone
        # to create an admin account. For local Docker Desktop deployments
        # this is acceptable (single user). For server deployments, set
        # DELTA_SETUP_TOKEN to prevent unauthenticated admin creation.
        if not self.dev_mode and not self.setup_token:
            warnings.append(
                "setup_token (recommended in production — open registration allows anyone to create an admin account)"
            )

        # Warn about auto-generated service token — not available to
        # the agents unless delivered via the agent secrets channel
        if not self.dev_mode and not self.service_token:
            warnings.append(
                "service_token (auto-generated tool-callback token — set DELTA_SERVICE_TOKEN in .env for production deployments)"
            )

        # F6: warn on default/weak Postgres password — the backend's own
        # credential (delta DB).
        try:
            from urllib.parse import unquote, urlparse

            _pg = urlparse(self.database_url)
            _pg_password = unquote(_pg.password or "")
            if not self.dev_mode and (_pg_password == "delta" or len(_pg_password) < 16):
                warnings.append("database password (default or short (<16 chars) — set POSTGRES_PASSWORD in .env)")
        except ValueError:
            pass  # malformed URL — not this check's job to reject

        # Block wildcard CORS with credentials — it's a CSRF vector
        if "*" in self.cors_origins.split(",") and not self.dev_mode:
            issues.append("cors_origins (wildcard '*' not allowed with credentials in production)")

        # Block insecure JWT algorithms — 'none' bypasses all signature verification
        _ALLOWED_JWT_ALGORITHMS = {
            "HS256",
            "HS384",
            "HS512",
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
            "PS256",
            "PS384",
            "PS512",
        }
        if self.jwt_algorithm not in _ALLOWED_JWT_ALGORITHMS:
            issues.append(f"jwt_algorithm ('{self.jwt_algorithm}' is not allowed — use HS256 or RS256)")

        # Warn about non-localhost HTTP Letta URL — credential secrets are sent
        # to this URL and would be transmitted in cleartext over the network.
        _LOCALHOST_PATTERNS = ("localhost", "127.0.0.1", "host.docker.internal", "letta", "backend")
        if self.letta_base_url.startswith("http://") and not self.dev_mode:
            from urllib.parse import urlparse

            hostname = urlparse(self.letta_base_url).hostname or ""
            if not any(hostname == pat or hostname.endswith(f".{pat}") for pat in _LOCALHOST_PATTERNS):
                issues.append(
                    f"letta_base_url ('{self.letta_base_url}' uses HTTP to a non-localhost host — "
                    "credential secrets are sent in cleartext)"
                )

        # Log warnings
        if warnings:
            logger.warning(
                "⚠️  Security recommendations: %s",
                ", ".join(warnings),
            )

        if issues:
            if self.dev_mode:
                logger.warning(
                    "⚠️  Running in DEV MODE with insecure defaults for: %s. "
                    "Set proper values before deploying to production.",
                    ", ".join(issues),
                )
            else:
                raise RuntimeError(
                    f"Refusing to start with insecure defaults for: {', '.join(issues)}. "
                    f"Set proper environment variables or set DELTA_DEV_MODE=1 for local development."
                )


def _read_secret_from_volume(name: str, secrets_dir: str = _SECRETS_DIR) -> str | None:
    """Read a previously auto-generated secret from the shared volume."""
    try:
        path = os.path.join(secrets_dir, name)
        with open(path, "r") as f:
            value = f.read().strip()
        if value:
            logger.info("Loaded %s from %s", name, path)
            return value
    except (OSError, FileNotFoundError):
        pass
    return None


def _write_secret_to_volume(name: str, value: str, secrets_dir: str = _SECRETS_DIR) -> None:
    """Write an auto-generated secret to the shared volume.

    File permissions are set to 0600 (owner read/write only) to prevent
    other processes from reading the secret.
    """
    try:
        os.makedirs(secrets_dir, exist_ok=True)
        path = os.path.join(secrets_dir, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)
        logger.info("Wrote %s to %s", name, path)
    except OSError:
        # Shared volume may not be available in all environments (e.g., local dev)
        logger.debug("Could not write %s to shared volume", name)


def _is_weak_secret(value: str) -> bool:
    """Check if a secret value is empty, matches an insecure default, or contains a weak pattern."""
    if not value.strip():
        return True
    if value in _INSECURE_DEFAULTS.values():
        return True
    if any(pat in value.lower() for pat in _WEAK_SECRET_PATTERNS):
        return True
    if len(value) < _MIN_SECRET_LENGTH:
        return True
    return False


def _needs_auto_generation(value: str) -> bool:
    """Check if a secret needs auto-generation.

    Only returns True for empty values or insecure defaults.
    Does NOT trigger auto-generation for short keys or test patterns —
    those are deliberate choices (e.g., test suites) and should only
    produce warnings in check_security(), not be silently replaced.
    """
    if not value.strip():
        return True
    if value in _INSECURE_DEFAULTS.values():
        return True
    return False


def _auto_generate_secrets(settings: Settings) -> None:
    """Auto-generate missing secrets and persist them to the shared volume.

    On first run, JWT_SECRET, CREDENTIALS_ENCRYPTION_KEY, and SERVICE_TOKEN
    are generated and written to /data/config/ so they survive restarts.
    On subsequent starts, the persisted values are loaded from the volume.

    This makes `docker compose up -d` work out of the box — no .env
    configuration required for local Docker Desktop deployments.
    """
    # JWT secret
    if _needs_auto_generation(settings.jwt_secret):
        existing = _read_secret_from_volume("jwt_secret")
        if existing:
            settings.jwt_secret = existing
        else:
            settings.jwt_secret = secrets.token_urlsafe(48)
            logger.info(
                "🔑 Auto-generated JWT secret (DELTA_JWT_SECRET not set). "
                "Set DELTA_JWT_SECRET in .env for production deployments."
            )
            _write_secret_to_volume("jwt_secret", settings.jwt_secret)

    # Credentials encryption key (Fernet key)
    if _needs_auto_generation(settings.credentials_encryption_key):
        existing = _read_secret_from_volume("credentials_encryption_key")
        if existing:
            settings.credentials_encryption_key = existing
        else:
            from cryptography.fernet import Fernet

            settings.credentials_encryption_key = Fernet.generate_key().decode()
            logger.info(
                "🔑 Auto-generated credentials encryption key (DELTA_CREDENTIALS_ENCRYPTION_KEY not set). "
                "Set DELTA_CREDENTIALS_ENCRYPTION_KEY in .env for production deployments."
            )
            _write_secret_to_volume("credentials_encryption_key", settings.credentials_encryption_key)

    # Service token
    if not settings.service_token:
        existing = _read_secret_from_volume("service_token")
        if existing:
            settings.service_token = existing
        else:
            settings.service_token = secrets.token_urlsafe(32)
            logger.info(
                "🔑 Auto-generated service token (DELTA_SERVICE_TOKEN not set). "
                "Set DELTA_SERVICE_TOKEN in .env for production deployments."
            )
            _write_secret_to_volume("service_token", settings.service_token)
    else:
        # Service token was set via env var — still write to shared volume
        # for pip-sidecar and eval containers that read from file
        _write_secret_to_volume("service_token", settings.service_token)

    # Eval service token (backend <-> eval runner)
    if _needs_auto_generation(settings.eval_service_token):
        existing = _read_secret_from_volume("eval_service_token", _DELTA_SECRETS_DIR)
        if existing:
            settings.eval_service_token = existing
        else:
            settings.eval_service_token = secrets.token_urlsafe(32)
            logger.info("🔑 Auto-generated eval service token (DELTA_EVAL_SERVICE_TOKEN not set).")
            _write_secret_to_volume("eval_service_token", settings.eval_service_token, _DELTA_SECRETS_DIR)
    else:
        _write_secret_to_volume("eval_service_token", settings.eval_service_token, _DELTA_SECRETS_DIR)

    # Sidecar service token (backend -> pip-sidecar)
    if _needs_auto_generation(settings.sidecar_service_token):
        existing = _read_secret_from_volume("sidecar_service_token", _DELTA_SECRETS_DIR)
        if existing:
            settings.sidecar_service_token = existing
        else:
            settings.sidecar_service_token = secrets.token_urlsafe(32)
            logger.info("🔑 Auto-generated sidecar service token (DELTA_SIDECAR_SERVICE_TOKEN not set).")
            _write_secret_to_volume("sidecar_service_token", settings.sidecar_service_token, _DELTA_SECRETS_DIR)
    else:
        _write_secret_to_volume("sidecar_service_token", settings.sidecar_service_token, _DELTA_SECRETS_DIR)


_LETTA_SERVER_PASSWORD_FILE = "/data/letta-secrets/server_password/password"


def _load_letta_server_password(settings: Settings) -> None:
    """Resolve the Letta server password (v0.16.39 adoption item 1).

    Precedence: explicit env var (LETTA_SERVER_PASSWORD in .env/compose)
    wins; otherwise fall back to the file the letta command wrapper
    generates on the letta_secrets volume, in its own subdirectory
    (least privilege: the backend mounts ONLY that path, so its read of
    the password does not also expose the PG password or the encryption
    key). Empty when neither exists — fake-letta CI and pre-0.16.39 pins
    run unauthenticated, and every consumer sends the header only when
    non-empty (graceful degradation, same pattern as the abort API).
    """
    if settings.letta_server_password:
        return
    try:
        with open(_LETTA_SERVER_PASSWORD_FILE) as f:
            value = f.read().strip()
        if value:
            settings.letta_server_password = value
    except OSError:
        pass  # No password file — unauthenticated (CI / pre-0.16.39)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Auto-generate missing secrets BEFORE security check.
    # This ensures first-run works without .env configuration.
    _auto_generate_secrets(settings)

    # Letta server password: env override, else the wrapper-generated file
    _load_letta_server_password(settings)

    settings.check_security()

    return settings


def get_cors_origins() -> list[str]:
    """Parse the comma-separated cors_origins setting into a list."""
    settings = get_settings()
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
