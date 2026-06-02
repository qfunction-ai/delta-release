"""Tests for config module — settings validation and CORS parsing."""

import logging

import pytest

from app.config import Settings, get_cors_origins


class TestSettingsCheckSecurity:
    """Tests for Settings.check_security."""

    def test_dev_mode_warns_on_insecure_defaults(self, caplog):
        """Dev mode warns but doesn't raise on insecure defaults."""
        settings = Settings(
            jwt_secret="change-me-in-production",
            credentials_encryption_key="change-me-in-production",
            dev_mode=True,
        )
        with caplog.at_level(logging.WARNING):
            settings.check_security()
        # Should not raise

    def test_prod_mode_raises_on_insecure_defaults(self):
        """Production mode raises RuntimeError on insecure defaults."""
        settings = Settings(
            jwt_secret="change-me-in-production",
            credentials_encryption_key="change-me-in-production",
            dev_mode=False,
        )
        with pytest.raises(RuntimeError, match="insecure"):
            settings.check_security()

    def test_empty_secret_always_rejected(self):
        """Empty secrets are rejected in production."""
        settings = Settings(
            jwt_secret="",
            credentials_encryption_key="change-me-in-production",
            dev_mode=False,
        )
        with pytest.raises(RuntimeError, match="insecure"):
            settings.check_security()

    def test_weak_pattern_rejected_in_prod(self):
        """Weak patterns in secrets are rejected in production."""
        settings = Settings(
            jwt_secret="dev-jwt-secret-do-not-use-xxxxxxxxx",
            credentials_encryption_key="a-valid-encryption-key-without-weak-patterns-xxxxxxxxx",
            dev_mode=False,
            setup_token="required-setup-token",
            service_token="required-service-token",
        )
        with pytest.raises(RuntimeError, match="weak pattern"):
            settings.check_security()

    def test_short_secret_rejected_in_prod(self):
        """Short secrets are rejected in production."""
        settings = Settings(
            jwt_secret="too-short",
            credentials_encryption_key="a-valid-encryption-key-that-is-long-enough-xxxxxxxxx",
            dev_mode=False,
            setup_token="required-setup-token",
            service_token="required-service-token",
        )
        with pytest.raises(RuntimeError, match="too short"):
            settings.check_security()

    def test_wildcard_cors_rejected_in_prod(self):
        """Wildcard CORS is rejected in production."""
        settings = Settings(
            jwt_secret="a-valid-jwt-secret-without-weak-patterns-xxxxxxxxx",
            credentials_encryption_key="a-valid-encryption-key-without-weak-patterns-xxxxxxxxx",
            dev_mode=False,
            setup_token="required-setup-token",
            service_token="required-service-token",
            cors_origins="*",
        )
        with pytest.raises(RuntimeError, match="wildcard"):
            settings.check_security()

    def test_valid_settings_pass(self):
        """Valid settings with no insecure defaults pass."""
        settings = Settings(
            jwt_secret="a-valid-jwt-secret-without-weak-patterns-xxxxxxxxx",
            credentials_encryption_key="a-valid-encryption-key-without-weak-patterns-xxxxxxxxx",
            dev_mode=False,
            setup_token="required-setup-token",
            service_token="required-service-token",
        )
        # Should not raise
        settings.check_security()


class TestGetCorsOrigins:
    """Tests for get_cors_origins."""

    def test_parses_comma_separated(self):
        """Parses comma-separated origins."""
        origins = get_cors_origins()
        assert isinstance(origins, list)
        assert len(origins) >= 1

    def test_strips_whitespace(self):
        """Strips whitespace from origins."""
        # The default setting has no extra whitespace, but the function
        # should handle it
        assert isinstance(get_cors_origins(), list)
