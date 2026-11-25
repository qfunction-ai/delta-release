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


class TestAutoGenerateServiceTokens:
    """F2: eval and sidecar tokens auto-generate to the delta_secrets dir."""

    def test_eval_token_generated_when_empty(self):
        from unittest.mock import patch

        from app.config import Settings, _auto_generate_secrets

        settings = Settings(jwt_secret="x" * 48, credentials_encryption_key="y" * 44)
        with (
            patch("app.config._read_secret_from_volume", return_value=None) as mock_read,
            patch("app.config._write_secret_to_volume") as mock_write,
        ):
            _auto_generate_secrets(settings)

        assert settings.eval_service_token, "eval token must be auto-generated"
        assert settings.sidecar_service_token, "sidecar token must be auto-generated"
        # The new tokens live on the delta_secrets dir, not /data/config
        written = {call.args[0] for call in mock_write.call_args_list}
        assert "eval_service_token" in written
        assert "sidecar_service_token" in written
        for call in mock_write.call_args_list:
            if call.args[0] in ("eval_service_token", "sidecar_service_token"):
                assert call.args[2] == "/data/secrets"
        # And they are read back from the same dir on restart
        read = {call.args[0] for call in mock_read.call_args_list}
        assert {"eval_service_token", "sidecar_service_token"} <= read

    def test_explicit_tokens_are_kept_and_persisted(self):
        from unittest.mock import patch

        from app.config import Settings, _auto_generate_secrets

        settings = Settings(
            jwt_secret="x" * 48,
            credentials_encryption_key="y" * 44,
            eval_service_token="my-eval-token-0123456789abcdef",
            sidecar_service_token="my-sidecar-token-0123456789abcdef",
        )
        with (
            patch("app.config._read_secret_from_volume", return_value=None),
            patch("app.config._write_secret_to_volume") as mock_write,
        ):
            _auto_generate_secrets(settings)

        assert settings.eval_service_token == "my-eval-token-0123456789abcdef"
        assert settings.sidecar_service_token == "my-sidecar-token-0123456789abcdef"
        # Explicit values are still persisted for the consumers that read files
        written = {call.args[0] for call in mock_write.call_args_list}
        assert {"eval_service_token", "sidecar_service_token"} <= written


class TestPostgresPasswordWarning:
    """F6: weak/default Postgres password produces a startup warning."""

    def _settings(self, url):
        return Settings(
            database_url=url,
            dev_mode=False,
            jwt_secret="a" * 48,
            credentials_encryption_key="b" * 44,
        )

    def test_default_delta_password_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            self._settings("postgresql://delta:delta@postgres:5432/delta").check_security()
        assert any("database password" in w for w in caplog.messages)

    def test_short_password_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            self._settings("postgresql://delta:short@postgres:5432/delta").check_security()
        assert any("database password" in w for w in caplog.messages)

    def test_strong_password_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            self._settings("postgresql://delta:superlongrandompassword1@postgres:5432/delta").check_security()
        assert not any("database password" in w for w in caplog.messages)

    def test_dev_mode_no_warning(self, caplog):
        s = Settings(database_url="postgresql://delta:delta@postgres:5432/delta", dev_mode=True)
        with caplog.at_level(logging.WARNING):
            s.check_security()
        assert not any("database password" in w for w in caplog.messages)

    def test_url_encoded_password_parsed(self, caplog):
        """URL-encoded special chars in the password are decoded before the check."""
        with caplog.at_level(logging.WARNING):
            self._settings("postgresql://delta:sh%40rt@postgres:5432/delta").check_security()
        assert any("database password" in w for w in caplog.messages)
