"""Tests for Letta proxy path validation."""

import pytest
from fastapi import HTTPException

from app.agents.letta_proxy import _validate_proxy_path


class TestValidateProxyPath:
    """Path validation for the Letta file proxy endpoint."""

    def test_valid_simple_filename(self):
        assert _validate_proxy_path("data.txt") == "data.txt"

    def test_valid_nested_path(self):
        assert _validate_proxy_path("subdir/data.txt") == "subdir/data.txt"

    def test_valid_with_hyphens_and_underscores(self):
        assert _validate_proxy_path("my-file_v2.json") == "my-file_v2.json"

    def test_valid_with_dots(self):
        assert _validate_proxy_path("archive.tar.gz") == "archive.tar.gz"

    def test_reject_path_traversal_dotdot(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("../../etc/passwd")
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_reject_path_traversal_mid_path(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("foo/../bar")
        assert exc_info.value.status_code == 400

    def test_reject_null_byte(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("file.txt\x00.jpg")
        assert exc_info.value.status_code == 400
        assert "null" in exc_info.value.detail.lower()

    def test_reject_empty_path(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("")
        assert exc_info.value.status_code == 400

    def test_reject_spaces(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("my file.txt")
        assert exc_info.value.status_code == 400
        assert "invalid" in exc_info.value.detail.lower()

    def test_reject_special_characters(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("file;rm -rf /")
        assert exc_info.value.status_code == 400

    def test_reject_backslash(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("dir\\file.txt")
        assert exc_info.value.status_code == 400

    def test_reject_leading_dotdot_component(self):
        """A path component that is exactly '..' should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_proxy_path("..")
        assert exc_info.value.status_code == 400

    def test_allow_dot_component(self):
        """A single '.' component is valid (current directory reference)."""
        assert _validate_proxy_path("./data.txt") == "./data.txt"

    def test_allow_dotdot_in_filename(self):
        """'..' embedded in a filename (not a path component) is allowed."""
        assert _validate_proxy_path("file..backup.txt") == "file..backup.txt"
