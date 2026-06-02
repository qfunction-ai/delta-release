import binascii
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)
import base64
import hashlib

# PBKDF2 parameters for key derivation (OWASP 2023 recommendation)
_PBKDF2_ITERATIONS = 600_000

# v1: Static salt (legacy — same across all deployments)
_PBKDF2_SALT_V1 = b"delta-credential-key-derivation"


def _derive_pbkdf2_salt_v2(key: str) -> bytes:
    """Derive a per-deployment PBKDF2 salt from the encryption key.

    v1 used a static salt, allowing precomputation attacks across
    deployments. v2 derives the salt from the key itself so each
    deployment gets a unique salt.
    """
    return hashlib.sha256(b"delta-salt-v2-" + key.encode()).digest()[:16]


def _derive_pbkdf2_key(key: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key using PBKDF2-HMAC-SHA256."""
    derived = hashlib.pbkdf2_hmac("sha256", key.encode(), salt, _PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(derived)


def _derive_key_v0(key: str) -> bytes:
    """Legacy key derivation (raw SHA-256) — used for migrating old data."""
    derived = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(derived)


def _derive_key_v1(key: str) -> bytes:
    """v1 key derivation (PBKDF2-HMAC-SHA256 with static salt)."""
    return _derive_pbkdf2_key(key, _PBKDF2_SALT_V1)


def _derive_key_v2(key: str) -> bytes:
    """v2 key derivation (PBKDF2-HMAC-SHA256 with per-deployment salt)."""
    return _derive_pbkdf2_key(key, _derive_pbkdf2_salt_v2(key))


def _get_fernet_key() -> bytes:
    """Get or generate the Fernet encryption key.

    Derives a Fernet key from the configured credentials_encryption_key
    using PBKDF2 with high iteration count and a per-deployment salt.
    Falls back to accepting a raw Fernet key if it's already a valid
    32-byte base64 key.
    """
    settings = get_settings()
    key = settings.credentials_encryption_key

    # If key is already a valid Fernet key, use it directly
    try:
        if len(base64.urlsafe_b64decode(key)) == 32:
            return key.encode() if isinstance(key, str) else key
    except (ValueError, TypeError):
        pass

    # Derive key using PBKDF2 with per-deployment salt (v2)
    return _derive_key_v2(key)


_fernet_v2: Fernet | None = None
_fernet_v1: Fernet | None = None
_fernet_v0: Fernet | None = None


def get_fernet() -> Fernet:
    """Get the current Fernet instance (v2 — per-deployment salt)."""
    global _fernet_v2
    if _fernet_v2 is None:
        _fernet_v2 = Fernet(_get_fernet_key())
    return _fernet_v2


def _get_fernet_v1() -> Fernet:
    """Get the v1 Fernet instance (PBKDF2 with static salt) for migration."""
    global _fernet_v1
    if _fernet_v1 is None:
        settings = get_settings()
        key = settings.credentials_encryption_key
        try:
            if len(base64.urlsafe_b64decode(key)) == 32:
                # Already a valid Fernet key — v1 and v2 are the same
                _fernet_v1 = get_fernet()
            else:
                _fernet_v1 = Fernet(_derive_key_v1(key))
        except (ValueError, TypeError):
            _fernet_v1 = Fernet(_derive_key_v1(key))
    return _fernet_v1


def _get_fernet_v0() -> Fernet:
    """Get the legacy Fernet instance (SHA-256-derived key) for migration."""
    global _fernet_v0
    if _fernet_v0 is None:
        settings = get_settings()
        key = settings.credentials_encryption_key
        try:
            if len(base64.urlsafe_b64decode(key)) == 32:
                # Already a valid Fernet key — v0 and v2 are the same
                _fernet_v0 = get_fernet()
            else:
                _fernet_v0 = Fernet(_derive_key_v0(key))
        except (ValueError, TypeError):
            _fernet_v0 = Fernet(_derive_key_v0(key))
    return _fernet_v0


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value using the current (v2 — per-deployment salt) key."""
    if not plaintext:
        return ""
    fernet = get_fernet()
    encrypted = fernet.encrypt(plaintext.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted).decode("utf-8")


def decrypt_value(encrypted: str) -> str:
    """Decrypt a string value, with transparent migration from v0/v1 to v2.

    Tries the current v2 key first. If that fails, falls back to v1 (static
    salt PBKDF2), then v0 (SHA-256). This transparently migrates old data
    on first access.
    """
    if not encrypted:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
    except (ValueError, binascii.Error):
        raise ValueError("Failed to decode encrypted value (invalid base64)")

    # Try current key (v2) first
    fernet_v2 = get_fernet()
    try:
        return fernet_v2.decrypt(decoded).decode("utf-8")
    except InvalidToken:
        logger.debug("v2 key failed, trying v1")

    # Fall back to v1 (static salt PBKDF2)
    fernet_v1 = _get_fernet_v1()
    try:
        plaintext = fernet_v1.decrypt(decoded).decode("utf-8")
        return plaintext
    except InvalidToken:
        logger.debug("v1 key failed, trying v0")

    # Fall back to v0 (SHA-256)
    fernet_v0 = _get_fernet_v0()
    try:
        plaintext = fernet_v0.decrypt(decoded).decode("utf-8")
        return plaintext
    except InvalidToken:
        raise ValueError("Failed to decrypt value with current and all legacy keys")


async def _migrate_credentials(db, target_fernet, version_label: str) -> None:
    """Re-encrypt all credentials that aren't already at the target version.

    Shared logic for v0→v1 and v1→v2 migrations. Iterates all credentials,
    tries to decrypt with the target version's Fernet instance. If that
    fails, decrypts with the cascade and re-encrypts with the current key.
    """
    from sqlalchemy import select

    from app.credentials.models import Credential

    result = await db.execute(select(Credential))
    credentials = result.scalars().all()

    migrated = 0
    for cred in credentials:
        try:
            # Try decrypting with target key — if it works, no migration needed
            target_fernet().decrypt(base64.urlsafe_b64decode(cred.primary_key_encrypted.encode("utf-8")))
        except InvalidToken:
            # Needs migration — decrypt with cascade, re-encrypt with current key
            try:
                primary_key = decrypt_value(cred.primary_key_encrypted)
                cred.primary_key_encrypted = encrypt_value(primary_key)

                if cred.secondary_key_encrypted:
                    secondary_key = decrypt_value(cred.secondary_key_encrypted)
                    cred.secondary_key_encrypted = encrypt_value(secondary_key)

                migrated += 1
            except (ValueError, TypeError, InvalidToken, OSError) as e:
                logger.warning("Failed to migrate credential %s to %s: %s", cred.key, version_label, e)

    if migrated > 0:
        await db.commit()
        logger.info("Migrated %d credentials to %s", migrated, version_label)


async def migrate_credentials_to_v1(db) -> None:
    """Re-encrypt all credentials from v0 (SHA-256) to v1 (PBKDF2 static salt)."""
    await _migrate_credentials(db, _get_fernet_v1, "v1 (PBKDF2)")


async def migrate_credentials_to_v2(db) -> None:
    """Re-encrypt all credentials from v0/v1 to v2 (per-deployment salt)."""
    await _migrate_credentials(db, get_fernet, "v2 (per-deployment salt)")


async def check_for_v0_credentials(db) -> int:
    """Check if any credentials are still encrypted with v0 (raw SHA-256).

    Returns the count of v0-encrypted credentials. If > 0, the deployment
    has credentials protected only by the weak v0 derivation (no salt,
    single SHA-256 pass). These should be migrated immediately.
    """
    from sqlalchemy import select

    from app.credentials.models import Credential

    result = await db.execute(select(Credential))
    credentials = result.scalars().all()

    v0_count = 0
    fernet_v2 = get_fernet()
    fernet_v1 = _get_fernet_v1()
    for cred in credentials:
        try:
            decoded = base64.urlsafe_b64decode(cred.primary_key_encrypted.encode("utf-8"))
        except (ValueError, binascii.Error):
            continue
        # If it can't be decrypted by v2 or v1, it's v0
        try:
            fernet_v2.decrypt(decoded)
            continue  # v2 — OK
        except InvalidToken:
            pass  # Not v2, try v1
        try:
            fernet_v1.decrypt(decoded)
            continue  # v1 — needs migration but not v0
        except InvalidToken:
            pass  # Not v1, must be v0
        # Must be v0
        v0_count += 1

    return v0_count
