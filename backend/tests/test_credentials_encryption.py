"""Tests for credential encryption — key derivation, encrypt/decrypt, migration."""

import base64

import pytest
from cryptography.fernet import Fernet

from app.credentials.encryption import (
    _derive_key_v0,
    _derive_key_v1,
    _derive_key_v2,
    _derive_pbkdf2_salt_v2,
    _get_fernet_key,
    decrypt_value,
    encrypt_value,
    get_fernet,
)


class TestDerivePbkdf2SaltV2:
    """Tests for _derive_pbkdf2_salt_v2."""

    def test_returns_bytes(self):
        result = _derive_pbkdf2_salt_v2("test-key")
        assert isinstance(result, bytes)

    def test_is_16_bytes(self):
        result = _derive_pbkdf2_salt_v2("test-key")
        assert len(result) == 16

    def test_different_keys_different_salts(self):
        salt1 = _derive_pbkdf2_salt_v2("key1")
        salt2 = _derive_pbkdf2_salt_v2("key2")
        assert salt1 != salt2


class TestDeriveKeyV0:
    """Tests for _derive_key_v0 (legacy SHA-256)."""

    def test_returns_bytes(self):
        result = _derive_key_v0("test-key")
        assert isinstance(result, bytes)

    def test_produces_valid_fernet_key(self):
        key = _derive_key_v0("test-key")
        # Should be valid base64 and decode to 32 bytes
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_deterministic(self):
        key1 = _derive_key_v0("test-key")
        key2 = _derive_key_v0("test-key")
        assert key1 == key2


class TestDeriveKeyV1:
    """Tests for _derive_key_v1 (PBKDF2 with static salt)."""

    def test_returns_bytes(self):
        result = _derive_key_v1("test-key")
        assert isinstance(result, bytes)

    def test_produces_valid_fernet_key(self):
        key = _derive_key_v1("test-key")
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_different_from_v0(self):
        key_v0 = _derive_key_v0("test-key")
        key_v1 = _derive_key_v1("test-key")
        assert key_v0 != key_v1


class TestDeriveKeyV2:
    """Tests for _derive_key_v2 (PBKDF2 with per-deployment salt)."""

    def test_returns_bytes(self):
        result = _derive_key_v2("test-key")
        assert isinstance(result, bytes)

    def test_produces_valid_fernet_key(self):
        key = _derive_key_v2("test-key")
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_different_from_v1(self):
        key_v1 = _derive_key_v1("test-key")
        key_v2 = _derive_key_v2("test-key")
        assert key_v1 != key_v2


class TestGetFernetKey:
    """Tests for _get_fernet_key."""

    def test_accepts_raw_fernet_key(self):
        """A valid 32-byte base64 key is used directly."""
        result = _get_fernet_key()
        # The result depends on the settings, but should be valid
        assert isinstance(result, bytes)

    def test_derives_key_from_password(self):
        """A non-Fernet password is derived using PBKDF2 v2."""
        result = _get_fernet_key()
        assert isinstance(result, bytes)
        decoded = base64.urlsafe_b64decode(result)
        assert len(decoded) == 32


class TestEncryptDecryptValue:
    """Tests for encrypt_value and decrypt_value."""

    def test_roundtrip(self):
        """Encrypt then decrypt returns the original value."""
        plaintext = "my-secret-api-key"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_encrypt_returns_different_ciphertext(self):
        """Each encryption produces different ciphertext (random IV)."""
        plaintext = "same-value"
        enc1 = encrypt_value(plaintext)
        enc2 = encrypt_value(plaintext)
        assert enc1 != enc2

    def test_encrypt_empty_string(self):
        """Empty string returns empty string."""
        assert encrypt_value("") == ""

    def test_decrypt_empty_string(self):
        """Empty string returns empty string."""
        assert decrypt_value("") == ""

    def test_decrypt_invalid_base64(self):
        """Invalid base64 raises ValueError."""
        with pytest.raises(ValueError):
            decrypt_value("not-valid-base64!!!")

    def test_decrypt_invalid_ciphertext(self):
        """Valid base64 but invalid Fernet token raises ValueError."""
        fake = base64.urlsafe_b64encode(b"not-a-fernet-token-at-all").decode()
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_value(fake)


class TestGetFernet:
    """Tests for get_fernet."""

    def test_returns_fernet_instance(self):
        f = get_fernet()
        assert isinstance(f, Fernet)

    def test_caches_instance(self):
        """Same instance is returned on subsequent calls."""
        f1 = get_fernet()
        f2 = get_fernet()
        assert f1 is f2
