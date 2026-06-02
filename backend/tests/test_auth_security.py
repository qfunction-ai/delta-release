"""Tests for auth security helpers — password hashing, JWT creation/verification."""

import os

os.environ["DELTA_DEV_MODE"] = "1"
os.environ["DELTA_JWT_SECRET"] = "test-jwt-secret-for-unit-tests"

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_roundtrip(self):
        """Hashed password verifies against the original."""
        password = "SecurePass123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password(self):
        """Wrong password does not verify."""
        hashed = hash_password("CorrectPass123!")
        assert verify_password("WrongPass456!", hashed) is False

    def test_hash_is_different_from_plaintext(self):
        """Hashed password is not the same as the plaintext."""
        password = "MyPassword789!"
        hashed = hash_password(password)
        assert hashed != password

    def test_different_hashes_for_same_password(self):
        """Same password produces different hashes (salt randomization)."""
        password = "SamePassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        # But both verify
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    def test_roundtrip(self):
        """Created token decodes back to the original data."""
        data = {"sub": "user-123", "username": "testuser"}
        token = create_access_token(data)
        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user-123"
        assert decoded["username"] == "testuser"

    def test_invalid_token(self):
        """Invalid token returns None."""
        result = decode_access_token("not-a-valid-token")
        assert result is None

    def test_tampered_token(self):
        """Token with modified payload returns None."""
        token = create_access_token({"sub": "user-123"})
        # Tamper with the token
        tampered = token + "x"
        assert decode_access_token(tampered) is None

    def test_includes_iat(self):
        """Token includes 'iat' (issued at) claim."""
        token = create_access_token({"sub": "user-123"})
        decoded = decode_access_token(token)
        assert "iat" in decoded

    def test_includes_exp(self):
        """Token includes 'exp' (expiration) claim."""
        token = create_access_token({"sub": "user-123"})
        decoded = decode_access_token(token)
        assert "exp" in decoded

    def test_default_role(self):
        """Token defaults to 'user' role when not specified."""
        token = create_access_token({"sub": "user-123"})
        decoded = decode_access_token(token)
        assert decoded["role"] == "user"

    def test_explicit_role(self):
        """Token includes explicit role when provided."""
        token = create_access_token({"sub": "user-123", "role": "admin"})
        decoded = decode_access_token(token)
        assert decoded["role"] == "admin"

    def test_default_token_version(self):
        """Token defaults to ver=1 when not specified."""
        token = create_access_token({"sub": "user-123"})
        decoded = decode_access_token(token)
        assert decoded["ver"] == 1

    def test_explicit_token_version(self):
        """Token includes explicit ver when provided."""
        token = create_access_token({"sub": "user-123", "ver": 3})
        decoded = decode_access_token(token)
        assert decoded["ver"] == 3
