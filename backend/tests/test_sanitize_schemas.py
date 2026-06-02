"""Tests for Pydantic schema validation — UserRegister, etc."""

import pytest

from app.auth.schemas import UserRegister


class TestUserRegister:
    def test_valid_input(self):
        """Valid username and password are accepted."""
        user = UserRegister(username="testuser", password="SecurePass123!")
        assert user.username == "testuser"

    def test_short_username(self):
        """Username shorter than 3 chars is rejected."""
        with pytest.raises(ValueError, match="3-50"):
            UserRegister(username="ab", password="SecurePass123!")

    def test_long_username(self):
        """Username longer than 50 chars is rejected."""
        with pytest.raises(ValueError, match="3-50"):
            UserRegister(username="a" * 51, password="SecurePass123!")

    def test_special_chars_in_username(self):
        """Username with special characters is rejected."""
        with pytest.raises(ValueError, match="letters, numbers"):
            UserRegister(username="user@name", password="SecurePass123!")

    def test_spaces_in_username(self):
        """Username with spaces is rejected."""
        with pytest.raises(ValueError, match="letters, numbers"):
            UserRegister(username="user name", password="SecurePass123!")

    def test_short_password(self):
        """Password shorter than 8 chars is rejected."""
        with pytest.raises(ValueError, match="8 characters"):
            UserRegister(username="testuser", password="Short1!")

    def test_underscore_in_username(self):
        """Underscore in username is accepted."""
        user = UserRegister(username="test_user", password="SecurePass123!")
        assert user.username == "test_user"

    def test_setup_token_optional(self):
        """Setup token is optional and defaults to None."""
        user = UserRegister(username="testuser", password="SecurePass123!")
        assert user.setup_token is None

    def test_setup_token_provided(self):
        """Setup token can be provided."""
        user = UserRegister(username="testuser", password="SecurePass123!", setup_token="my-token")
        assert user.setup_token == "my-token"
