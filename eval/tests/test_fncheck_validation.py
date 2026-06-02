"""Unit tests for eval container FnCheck validation.

Tests the _validate_fncheck_expr function and CheckDef.fn validator
to ensure sandbox escape vectors are blocked.
"""

import pytest
import sys
import os

# Add parent dir to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _validate_fncheck_expr, CheckDef


class TestValidateFnCheckExpr:
    """Tests for _validate_fncheck_expr sandbox validation."""

    def test_valid_lambda_passes(self):
        """Simple safe lambda should pass validation."""
        result = _validate_fncheck_expr("lambda trace: len(trace.last.outputs) > 0")
        assert result == "lambda trace: len(trace.last.outputs) > 0"

    def test_non_lambda_rejected(self):
        """Non-lambda expressions must be rejected."""
        with pytest.raises(ValueError, match="lambda"):
            _validate_fncheck_expr("print('hello')")

    def test_import_rejected(self):
        """Import statements must be rejected."""
        with pytest.raises(ValueError):
            _validate_fncheck_expr("lambda trace: __import__('os')")

    def test_exec_rejected(self):
        """exec() calls must be rejected."""
        with pytest.raises(ValueError, match="exec"):
            _validate_fncheck_expr("lambda trace: exec('pass')")

    def test_eval_rejected(self):
        """eval() calls must be rejected."""
        with pytest.raises(ValueError, match="eval"):
            _validate_fncheck_expr("lambda trace: eval('1+1')")

    def test_open_rejected(self):
        """open() calls must be rejected."""
        with pytest.raises(ValueError, match="open"):
            _validate_fncheck_expr("lambda trace: open('/etc/passwd')")

    def test_getattr_rejected(self):
        """VULN-043: getattr() must be rejected — enables sandbox escape."""
        with pytest.raises(ValueError):
            _validate_fncheck_expr("lambda trace: getattr(trace, '__class__')")

    def test_getattr_without_dunder_rejected(self):
        """VULN-043: getattr() without dunder arg is also rejected by AST walker."""
        with pytest.raises(ValueError, match="getattr"):
            _validate_fncheck_expr("lambda trace: getattr(trace, 'name')")

    def test_type_rejected(self):
        """VULN-043: type() without dunder access is rejected by AST walker."""
        with pytest.raises(ValueError, match="type"):
            _validate_fncheck_expr("lambda trace: type(trace)")

    def test_type_with_dunder_rejected(self):
        """VULN-043: type() with dunder access is rejected (regex catches dunder first)."""
        with pytest.raises(ValueError):
            _validate_fncheck_expr("lambda trace: type(trace).__bases__")

    def test_hasattr_rejected(self):
        """VULN-043: hasattr() without dunder is rejected by AST walker."""
        with pytest.raises(ValueError, match="hasattr"):
            _validate_fncheck_expr("lambda trace: hasattr(trace, 'name')")

    def test_direct_dunder_access_rejected(self):
        """Direct dunder attribute access must be caught by regex."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: trace.__class__")

    def test_dunder_bases_rejected(self):
        """__bases__ access must be caught."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: trace.__class__.__bases__")

    def test_dunder_subclasses_rejected(self):
        """__subclasses__ access must be caught."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: trace.__class__.__subclasses__()")

    def test_dunder_dict_rejected(self):
        """__dict__ access must be caught."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: trace.__dict__")

    def test_dunder_string_constant_rejected(self):
        """VULN-043: String constants containing dunder fragments are caught by regex."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: '__class__'")

    def test_dunder_string_prefix_rejected(self):
        """VULN-043: String constants with dunder prefix are caught by regex."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            _validate_fncheck_expr("lambda trace: '__subclasses__'")

    def test_os_module_rejected(self):
        """os module access must be rejected."""
        with pytest.raises(ValueError, match="os"):
            _validate_fncheck_expr("lambda trace: os.system('id')")

    def test_subprocess_rejected(self):
        """subprocess access must be rejected."""
        with pytest.raises(ValueError, match="subprocess"):
            _validate_fncheck_expr("lambda trace: subprocess.run(['ls'])")

    def test_socket_rejected(self):
        """socket access must be rejected."""
        with pytest.raises(ValueError, match="socket"):
            _validate_fncheck_expr("lambda trace: socket.socket()")

    def test_invalid_syntax_rejected(self):
        """Invalid Python syntax must be rejected."""
        with pytest.raises(ValueError, match="syntax"):
            _validate_fncheck_expr("lambda trace: !invalid")

    def test_safe_string_operations_pass(self):
        """String methods that are in safe builtins should pass."""
        result = _validate_fncheck_expr(
            "lambda trace: 'keyword' in str(trace.last.outputs).lower()"
        )
        assert "lambda" in result

    def test_safe_any_all_pass(self):
        """any() and all() should pass — they're in safe builtins."""
        result = _validate_fncheck_expr(
            "lambda trace: any(kw in str(trace.last.outputs) for kw in ['a', 'b'])"
        )
        assert "lambda" in result

    def test_safe_isinstance_passes(self):
        """isinstance() should pass — it's in safe builtins."""
        result = _validate_fncheck_expr(
            "lambda trace: isinstance(trace.last.outputs, str)"
        )
        assert "lambda" in result

    def test_string_concat_dunder_without_getattr_passes_regex_but_safe(self):
        """VULN-043: String concatenation bypasses regex but can't be used
        without getattr. This test verifies the defense-in-depth:
        the expression passes regex but getattr is blocked at eval time."""
        # This expression passes regex (no __\w+__ pattern) but would
        # fail at eval time because getattr is not in safe builtins.
        # We validate it passes the regex check (it's syntactically valid)
        # but the real protection is the missing getattr in the namespace.
        result = _validate_fncheck_expr("lambda trace: '_'+'_class_'+'_'")
        assert "lambda" in result


class TestCheckDefFnValidator:
    """Tests for CheckDef.fn field validator (defense-in-depth at container layer)."""

    def test_valid_fn_passes(self):
        """Valid FnCheck expression should pass schema validation."""
        check = CheckDef(
            type="FnCheck",
            name="test",
            fn="lambda trace: len(trace.last.outputs) > 0",
        )
        assert check.fn == "lambda trace: len(trace.last.outputs) > 0"

    def test_non_lambda_fn_rejected(self):
        """Non-lambda fn must be rejected at schema level."""
        with pytest.raises(ValueError, match="lambda"):
            CheckDef(type="FnCheck", name="test", fn="print('hello')")

    def test_dunder_fn_rejected(self):
        """Dunder patterns in fn must be rejected at schema level."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            CheckDef(
                type="FnCheck",
                name="test",
                fn="lambda trace: trace.__class__",
            )

    def test_getattr_fn_rejected(self):
        """VULN-043: getattr in fn must be rejected at schema level (regex catches dunder first)."""
        with pytest.raises(ValueError):
            CheckDef(
                type="FnCheck",
                name="test",
                fn="lambda trace: getattr(trace, '__class__')",
            )

    def test_getattr_fn_without_dunder_rejected(self):
        """VULN-043: getattr without dunder is now rejected at schema level.

        The CheckDef.fn validator calls _validate_fncheck_expr, which
        includes the full AST walk that blocks getattr. Previously the
        schema validator only did regex checks, so getattr without dunder
        slipped through — now the full validation runs at schema time.
        """
        with pytest.raises(ValueError, match="getattr"):
            CheckDef(
                type="FnCheck",
                name="test",
                fn="lambda trace: getattr(trace, 'name')",
            )

    def test_none_fn_passes(self):
        """None fn should pass (fn is optional for non-FnCheck types)."""
        check = CheckDef(type="StringMatching", name="test", keyword="hello")
        assert check.fn is None
