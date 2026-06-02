"""Tests for sanitization utilities."""

import pytest
from fastapi import HTTPException

from app.sanitize import (
    sanitize_file_path,
    sanitize_filename,
    sanitize_python_code,
    sanitize_string,
    validate_cron_expression,
    validate_mime_type,
    validate_prompt_template,
    validate_tool_source_code,
)


class TestSanitizeString:
    """Tests for sanitize_string."""

    def test_removes_control_chars(self):
        result = sanitize_string("hello\x00world\x01")
        assert result == "helloworld"

    def test_truncates_long_string(self):
        result = sanitize_string("x" * 20000, max_length=100)
        assert len(result) == 100

    def test_passes_through_normal_string(self):
        result = sanitize_string("hello world")
        assert result == "hello world"

    def test_non_string_passthrough(self):
        result = sanitize_string(42)
        assert result == 42


class TestValidateCronExpression:
    """Tests for validate_cron_expression."""

    def test_empty_allowed(self):
        assert validate_cron_expression("") is True

    def test_valid_5_field(self):
        assert validate_cron_expression("0 * * * *") is True

    def test_valid_every_5_min(self):
        assert validate_cron_expression("*/5 * * * *") is True

    def test_rejects_every_minute(self):
        assert validate_cron_expression("* * * * *") is False

    def test_rejects_every_2_min(self):
        assert validate_cron_expression("*/2 * * * *") is False

    def test_rejects_4_fields(self):
        assert validate_cron_expression("0 * * *") is False

    def test_rejects_6_fields(self):
        assert validate_cron_expression("0 * * * * 0") is False

    def test_rejects_invalid_chars(self):
        assert validate_cron_expression("0 abc * * *") is False


class TestValidatePromptTemplate:
    """Tests for validate_prompt_template."""

    def test_valid_template(self):
        is_valid, error = validate_prompt_template("Search for {{query}}")
        assert is_valid is True
        assert error == ""

    def test_empty_template(self):
        is_valid, error = validate_prompt_template("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_script_tag_rejected(self):
        is_valid, error = validate_prompt_template("<script>alert('x')</script>")
        assert is_valid is False

    def test_javascript_protocol_rejected(self):
        is_valid, error = validate_prompt_template("javascript:alert(1)")
        assert is_valid is False

    def test_event_handler_rejected(self):
        is_valid, error = validate_prompt_template("onclick=alert(1)")
        assert is_valid is False

    def test_malformed_variable(self):
        is_valid, error = validate_prompt_template("{bad_var}")
        assert is_valid is False


class TestSanitizePythonCode:
    """Tests for sanitize_python_code."""

    def test_safe_code_no_warnings(self):
        code, warnings = sanitize_python_code("x = 1 + 2")
        assert warnings == []

    def test_subprocess_import_blocked(self):
        code, warnings = sanitize_python_code("import subprocess")
        assert any("subprocess" in w for w in warnings)

    def test_os_system_blocked(self):
        code, warnings = sanitize_python_code("import os\nos.system('ls')")
        assert any("os.system" in w or "Restricted os" in w for w in warnings)

    def test_eval_blocked(self):
        code, warnings = sanitize_python_code("eval('1+1')")
        assert any("eval" in w for w in warnings)

    def test_exec_blocked(self):
        code, warnings = sanitize_python_code("exec('print(1)')")
        assert any("exec" in w for w in warnings)

    def test_syntax_error_rejected(self):
        code, warnings = sanitize_python_code("def foo(")
        assert any("syntax" in w.lower() for w in warnings)

    def test_dunder_attr_blocked(self):
        code, warnings = sanitize_python_code("x.__class__")
        assert any("__class__" in w for w in warnings)

    def test_safe_os_getenv_allowed(self):
        code, warnings = sanitize_python_code("import os\nx = os.getenv('KEY')")
        assert not any("os.getenv" in w for w in warnings)

    def test_alias_tracking(self):
        """Aliases are tracked: x = os; x.system() is caught."""
        code, warnings = sanitize_python_code("import os\nx = os\nx.system('ls')")
        assert any("system" in w.lower() for w in warnings)

    def test_import_from_subprocess(self):
        """from subprocess import run is blocked."""
        code, warnings = sanitize_python_code("from subprocess import run")
        assert any("subprocess" in w for w in warnings)

    def test_import_from_os_unsafe(self):
        """from os import system is blocked."""
        code, warnings = sanitize_python_code("from os import system")
        assert any("os" in w.lower() for w in warnings)

    def test_import_from_os_safe(self):
        """from os import getenv is allowed."""
        code, warnings = sanitize_python_code("from os import getenv")
        assert not any("getenv" in w for w in warnings)

    def test_alias_via_assignment(self):
        """x = os; x.system() is caught via assignment tracking."""
        code, warnings = sanitize_python_code("import os\nx = os\nx.system('ls')")
        assert any("system" in w.lower() for w in warnings)

    def test_dangerous_alias_call(self):
        """Calling an aliased dangerous module is caught."""
        code, warnings = sanitize_python_code("import subprocess as sp\nsp.run(['ls'])")
        assert any("subprocess" in w.lower() or "sp" in w for w in warnings)

    def test_importlib_import_module_blocked(self):
        """importlib.import_module() is blocked."""
        code, warnings = sanitize_python_code("import importlib\nimportlib.import_module('os')")
        assert any("importlib" in w for w in warnings)

    def test_getattr_on_dangerous_module(self):
        """getattr(os, 'system') is blocked."""
        code, warnings = sanitize_python_code("import os\ngetattr(os, 'system')")
        assert any("getattr" in w for w in warnings)

    def test_globals_subscript_blocked(self):
        """globals()['__builtins__'] is blocked."""
        code, warnings = sanitize_python_code("globals()['__builtins__']")
        assert any("globals" in w for w in warnings)

    def test_dunder_subscript_blocked(self):
        """func.__globals__['key'] is blocked."""
        code, warnings = sanitize_python_code("func.__globals__['key']")
        assert any("__globals__" in w for w in warnings)

    def test_builtins_name_blocked(self):
        """__builtins__ reference is blocked."""
        code, warnings = sanitize_python_code("__builtins__")
        assert any("__builtins__" in w for w in warnings)

    def test_os_popen_blocked(self):
        """os.popen() is blocked."""
        code, warnings = sanitize_python_code("import os\nos.popen('ls')")
        assert any("popen" in w.lower() for w in warnings)

    def test_socket_import_blocked(self):
        """import socket is blocked."""
        code, warnings = sanitize_python_code("import socket")
        assert any("socket" in w for w in warnings)

    def test_pickle_import_blocked(self):
        """import pickle is blocked."""
        code, warnings = sanitize_python_code("import pickle")
        assert any("pickle" in w for w in warnings)

    def test_ctypes_import_blocked(self):
        """import ctypes is blocked."""
        code, warnings = sanitize_python_code("import ctypes")
        assert any("ctypes" in w for w in warnings)

    def test_null_bytes_removed(self):
        """Null bytes are removed from code."""
        code, warnings = sanitize_python_code("x = 1\x00")
        assert "\x00" not in code

    def test_alias_propagation_via_direct_name(self):
        """Direct module reference in assignment: x = subprocess; x.run() is caught."""
        code, warnings = sanitize_python_code("x = subprocess\nx.run(['ls'])")
        # subprocess is in DANGEROUS_MODULES, so x.run should be caught
        assert any("subprocess" in w.lower() or "run" in w.lower() for w in warnings)

    def test_dangerous_call_via_alias_name(self):
        """Calling an aliased dangerous module as a function is caught."""
        code, warnings = sanitize_python_code("import subprocess\nsubprocess(['ls'])")
        # subprocess is called as a function (not typical, but caught)
        assert len(warnings) > 0

    def test_subscript_on_dangerous_builtin(self):
        """globals['key'] (subscript on builtin name without call) is blocked."""
        code, warnings = sanitize_python_code("globals['key']")
        assert any("globals" in w for w in warnings)


class TestValidateToolSourceCode:
    """Tests for validate_tool_source_code."""

    def test_safe_code_passes(self):
        result = validate_tool_source_code("def run(x): return x")
        assert result is not None

    def test_dangerous_code_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_tool_source_code("import subprocess")
        assert exc_info.value.status_code == 400


class TestSanitizeFilename:
    """Tests for sanitize_filename — prevents Content-Disposition header injection."""

    def test_normal_filename(self):
        assert sanitize_filename("report.csv") == "report.csv"

    def test_strips_directory(self):
        assert sanitize_filename("scripts/exploit.py") == "exploit.py"

    def test_strips_quotes(self):
        """Double quotes break the Content-Disposition quoted-string boundary."""
        result = sanitize_filename('file"name.txt')
        assert '"' not in result
        assert result == "filename.txt"

    def test_strips_newlines(self):
        """Newlines enable HTTP header injection — must be removed."""
        result = sanitize_filename("file\r\nX-Injected: true.txt")
        assert "\r" not in result
        assert "\n" not in result
        # The newlines are gone, so no header injection is possible
        # even if the remaining text looks odd

    def test_strips_control_chars(self):
        result = sanitize_filename("file\x00\x01name.txt")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_collapse_whitespace(self):
        result = sanitize_filename("file   name.txt")
        assert result == "file name.txt"

    def test_empty_after_sanitization(self):
        """Falls back to 'download' if nothing remains."""
        result = sanitize_filename('"\r\n"')
        assert result == "download"

    def test_path_traversal_stripped(self):
        result = sanitize_filename("../../etc/passwd")
        assert result == "passwd"


class TestSanitizeFilePath:
    """Tests for sanitize_file_path — preserves directory structure, strips injection chars."""

    def test_preserves_directory_structure(self):
        assert sanitize_file_path("scripts/run.py") == "scripts/run.py"

    def test_preserves_nested_dirs(self):
        assert sanitize_file_path("references/api-docs.md") == "references/api-docs.md"

    def test_strips_quotes(self):
        result = sanitize_file_path('dir/file"name.txt')
        assert '"' not in result

    def test_strips_newlines(self):
        result = sanitize_file_path("dir/file\r\nX-Injected: true.txt")
        assert "\r" not in result
        assert "\n" not in result

    def test_rejects_path_traversal(self):
        result = sanitize_file_path("../../etc/passwd")
        assert ".." not in result
        assert result == "passwd"

    def test_rejects_absolute_path(self):
        result = sanitize_file_path("/etc/passwd")
        assert not result.startswith("/")

    def test_strips_control_chars(self):
        result = sanitize_file_path("dir/file\x00name.txt")
        assert "\x00" not in result

    def test_empty_after_sanitization(self):
        result = sanitize_file_path('"\r\n"')
        assert result == "unknown"


class TestValidateMimeType:
    """Tests for validate_mime_type — prevents stored XSS via text/html."""

    def test_safe_text_plain(self):
        assert validate_mime_type("text/plain") == "text/plain"

    def test_safe_image(self):
        assert validate_mime_type("image/png") == "image/png"

    def test_safe_json(self):
        assert validate_mime_type("application/json") == "application/json"

    def test_safe_octet_stream(self):
        assert validate_mime_type("application/octet-stream") == "application/octet-stream"

    def test_rejects_text_html(self):
        """text/html is the stored XSS vector — must be rejected."""
        assert validate_mime_type("text/html") == "application/octet-stream"

    def test_rejects_unknown_type(self):
        assert validate_mime_type("application/x-shellscript") == "application/octet-stream"

    def test_safe_yaml(self):
        assert validate_mime_type("application/yaml") == "application/yaml"

    def test_safe_markdown(self):
        assert validate_mime_type("text/markdown") == "text/markdown"
