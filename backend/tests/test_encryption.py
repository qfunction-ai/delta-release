"""Tests for credential encryption — encrypt/decrypt round-trips, migration, error handling."""

import base64
import os

import pytest
from cryptography.fernet import Fernet

# Use a short key that's NOT a valid Fernet key so v0, v1, and v2 all differ
os.environ["DELTA_DEV_MODE"] = "1"
os.environ["DELTA_CREDENTIALS_ENCRYPTION_KEY"] = "short-test-key"

from app.credentials.encryption import (
    _derive_key_v0,
    _derive_key_v1,
    _derive_key_v2,
    _derive_pbkdf2_salt_v2,
    decrypt_value,
    encrypt_value,
)


@pytest.fixture(autouse=True)
def reset_fernet_cache():
    """Reset the cached Fernet instances between tests so each test gets fresh state."""
    import app.credentials.encryption as mod

    mod._fernet_v2 = None
    mod._fernet_v1 = None
    mod._fernet_v0 = None
    yield
    mod._fernet_v2 = None
    mod._fernet_v1 = None
    mod._fernet_v0 = None


class TestEncryptDecrypt:
    def test_roundtrip(self):
        """encrypt_value → decrypt_value returns the original plaintext."""
        plaintext = "my-secret-api-key"
        encrypted = encrypt_value(plaintext)
        assert decrypt_value(encrypted) == plaintext

    def test_roundtrip_special_chars(self):
        """Handles special characters in plaintext."""
        plaintext = "key/with+special=chars&more!"
        encrypted = encrypt_value(plaintext)
        assert decrypt_value(encrypted) == plaintext

    def test_empty_string(self):
        """Empty string encrypts and decrypts to empty string."""
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_decrypt_invalid_base64(self):
        """Invalid base64 input raises ValueError."""
        with pytest.raises(ValueError, match="invalid base64"):
            decrypt_value("a")

    def test_decrypt_garbage_ciphertext(self):
        """Valid base64 but not a Fernet token raises ValueError."""
        garbage = base64.urlsafe_b64encode(b"not-a-fernet-token-at-all").decode()
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_value(garbage)


class TestKeyDerivation:
    def test_v1_differs_from_v0(self):
        """PBKDF2 and SHA-256 produce different keys from the same input."""
        key = "short-test-key"
        assert _derive_key_v1(key) != _derive_key_v0(key)

    def test_v2_differs_from_v1(self):
        """Per-deployment salt produces different keys than static salt."""
        key = "short-test-key"
        assert _derive_key_v2(key) != _derive_key_v1(key)

    def test_v1_deterministic(self):
        """Same input always produces the same v1 key."""
        key = "short-test-key"
        assert _derive_key_v1(key) == _derive_key_v1(key)

    def test_v2_deterministic(self):
        """Same input always produces the same v2 key."""
        key = "short-test-key"
        assert _derive_key_v2(key) == _derive_key_v2(key)

    def test_v2_salt_per_deployment(self):
        """Different encryption keys produce different v2 salts."""
        salt_a = _derive_pbkdf2_salt_v2("deployment-key-a")
        salt_b = _derive_pbkdf2_salt_v2("deployment-key-b")
        assert salt_a != salt_b

    def test_v2_keys_differ_across_deployments(self):
        """Different encryption keys produce different v2 Fernet keys."""
        key_a = _derive_key_v2("deployment-key-a")
        key_b = _derive_key_v2("deployment-key-b")
        assert key_a != key_b


class TestMigration:
    def test_v0_to_current_migration(self):
        """Data encrypted with v0 key can be decrypted (returns plaintext)."""
        # Encrypt with v0 key directly
        key = "short-test-key"
        fernet_v0 = Fernet(_derive_key_v0(key))
        plaintext = "legacy-secret-value"
        encrypted_bytes = fernet_v0.encrypt(plaintext.encode())
        encrypted_b64 = base64.urlsafe_b64encode(encrypted_bytes).decode()

        # decrypt_value should fall back to v0 and return the plaintext
        result = decrypt_value(encrypted_b64)
        assert result == plaintext

    def test_v1_to_current_migration(self):
        """Data encrypted with v1 key can be decrypted via fallback."""
        key = "short-test-key"
        fernet_v1 = Fernet(_derive_key_v1(key))
        plaintext = "v1-secret-value"
        encrypted_bytes = fernet_v1.encrypt(plaintext.encode())
        encrypted_b64 = base64.urlsafe_b64encode(encrypted_bytes).decode()

        # decrypt_value should try v2, fail, then fall back to v1
        result = decrypt_value(encrypted_b64)
        assert result == plaintext

    def test_current_encrypted_doesnt_need_migration(self):
        """Data encrypted with current key (v2) decrypts directly without fallback."""
        plaintext = "current-secret-value"
        encrypted = encrypt_value(plaintext)
        # This should succeed with v2 key directly
        assert decrypt_value(encrypted) == plaintext
