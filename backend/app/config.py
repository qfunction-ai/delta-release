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

    # Backend URL as seen from the Letta container (for tool exec env vars)
    backend_url: str = "http://backend:8000"

    # Eval runner
    eval_url: str = "http://eval:8003"
    evals_dir: str = "/app/evals"  # Base directory for eval scenario YAML files (VULN-045)

    # Dev mode — allows insecure defaults and bootstrap user creation
    dev_mode: bool = False

    # Service token for internal service-to-service auth (e.g., credential execution)
    service_token: str = ""

    # Setup token for first-user registration (optional)
    # If set, the first user must provide this token when registering.
    # If empty, registration is open (no token required) — only safe in dev mode.
    setup_token: str = ""

    # CORS
    # Comma-separated list of allowed origins for the frontend.
    # Never use "*" in production with credentials=True — it's a CSRF vector.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

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
        # the Letta container if not set via env var
        if not self.dev_mode and not self.service_token:
            warnings.append(
                "service_token (auto-generated — set DELTA_SERVICE_TOKEN in .env for production deployments)"
            )

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


def _read_secret_from_volume(name: str) -> str | None:
    """Read a previously auto-generated secret from the shared volume."""
    try:
        path = os.path.join(_SECRETS_DIR, name)
        with open(path, "r") as f:
            value = f.read().strip()
        if value:
            logger.info("Loaded %s from %s", name, path)
            return value
    except (OSError, FileNotFoundError):
        pass
    return None


def _write_secret_to_volume(name: str, value: str) -> None:
    """Write an auto-generated secret to the shared volume.

    File permissions are set to 0600 (owner read/write only) to prevent
    other processes from reading the secret.
    """
    try:
        os.makedirs(_SECRETS_DIR, exist_ok=True)
        path = os.path.join(_SECRETS_DIR, name)
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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Auto-generate missing secrets BEFORE security check.
    # This ensures first-run works without .env configuration.
    _auto_generate_secrets(settings)

    settings.check_security()

    return settings


def get_cors_origins() -> list[str]:
    """Parse the comma-separated cors_origins setting into a list."""
    settings = get_settings()
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
