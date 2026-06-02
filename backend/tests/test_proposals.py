"""Tests for tool proposal helpers — identifier validation."""

import pytest

from app.tools.proposals import execute_dry_run


class TestExecuteDryRunIdentifierValidation:
    """VULN-001: entry_point_name and schema property names must be valid identifiers."""

    @pytest.mark.asyncio
    async def test_rejects_injection_in_entry_point_name(self):
        """A crafted name with code injection characters must be rejected."""
        output, error = await execute_dry_run(
            source_code="def x(): pass",
            entry_point_name='x); import os; os.system("id"); #',
            json_schema={"properties": {}, "required": []},
            pip_requirements=None,
        )
        assert output is None
        assert "Invalid entry point name" in error

    @pytest.mark.asyncio
    async def test_rejects_name_with_spaces(self):
        """Spaces in the entry point name are not valid Python identifiers."""
        output, error = await execute_dry_run(
            source_code="def my_func(): pass",
            entry_point_name="my func",
            json_schema={"properties": {}, "required": []},
            pip_requirements=None,
        )
        assert output is None
        assert "Invalid entry point name" in error

    @pytest.mark.asyncio
    async def test_rejects_name_starting_with_digit(self):
        """Python identifiers cannot start with a digit."""
        output, error = await execute_dry_run(
            source_code="def _1func(): pass",
            entry_point_name="1func",
            json_schema={"properties": {}, "required": []},
            pip_requirements=None,
        )
        assert output is None
        assert "Invalid entry point name" in error

    @pytest.mark.asyncio
    async def test_rejects_injection_in_schema_property_name(self):
        """A crafted schema property name with injection characters must be rejected."""
        output, error = await execute_dry_run(
            source_code="def my_func(evil=None): pass",
            entry_point_name="my_func",
            json_schema={
                "properties": {"evil=1; import os#": {"type": "string"}},
                "required": [],
            },
            pip_requirements=None,
        )
        assert output is None
        assert "Invalid schema property name" in error

    @pytest.mark.asyncio
    async def test_accepts_valid_identifier(self):
        """A valid identifier with underscores should pass validation.
        (The dry run itself will fail since we can't connect to Letta,
        but the validation should not reject it.)"""
        output, error = await execute_dry_run(
            source_code="def my_func(): pass",
            entry_point_name="my_func",
            json_schema={"properties": {}, "required": []},
            pip_requirements=None,
        )
        # Should not be a validation error — the error (if any) would be
        # a connection failure to Letta, not "Invalid entry point name"
        if error is not None:
            assert "Invalid entry point name" not in error
            assert "Invalid schema property name" not in error
