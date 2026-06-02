"""Tests for evals schemas — CheckDef validation and response serialization."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.evals.schemas import (
    CheckDef,
    EvalRunResponse,
    EvalScenarioResponse,
    InteractionDef,
    ScenarioDefinition,
)


class TestCheckDefValidation:
    """Tests for CheckDef field validators."""

    def test_valid_string_matching(self):
        check = CheckDef(type="StringMatching", name="test", keyword="hello")
        assert check.type == "StringMatching"

    def test_valid_regex_matching(self):
        check = CheckDef(type="RegexMatching", name="test", pattern="^hello")
        assert check.type == "RegexMatching"

    def test_valid_equals(self):
        check = CheckDef(type="Equals", name="test", expected="value")
        assert check.type == "Equals"

    def test_valid_fn_check(self):
        check = CheckDef(type="FnCheck", name="test", fn="lambda x: x > 0")
        assert check.type == "FnCheck"

    def test_valid_llm_judge(self):
        check = CheckDef(type="LLMJudge", name="test", prompt="Is this correct?")
        assert check.type == "LLMJudge"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="Check type must be one of"):
            CheckDef(type="InvalidType", name="test")

    def test_fn_check_must_be_lambda(self):
        with pytest.raises(ValidationError, match="must be a lambda expression"):
            CheckDef(type="FnCheck", name="test", fn="def foo(): pass")

    def test_fn_check_rejects_dunder(self):
        with pytest.raises(ValidationError, match="forbidden pattern"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: x.__class__")

    def test_fn_check_rejects_import(self):
        with pytest.raises(ValidationError, match="forbidden pattern"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: import os")

    def test_fn_check_rejects_exec(self):
        with pytest.raises(ValidationError, match="forbidden pattern"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: exec('code')")

    def test_fn_check_rejects_os_access(self):
        with pytest.raises(ValidationError, match="must not access"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: os.system('ls')")

    def test_fn_check_rejects_subprocess_access(self):
        with pytest.raises(ValidationError, match="must not access"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: subprocess.call(['ls'])")

    def test_fn_check_rejects_open_call(self):
        with pytest.raises(ValidationError, match="forbidden pattern"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: open('/etc/passwd')")

    def test_fn_check_rejects_eval_call(self):
        with pytest.raises(ValidationError, match="forbidden pattern"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: eval('1+1')")

    def test_fn_check_rejects_getattr(self):
        with pytest.raises(ValidationError, match="must not call"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: getattr(x, 'secret')")

    def test_fn_check_rejects_invalid_syntax(self):
        with pytest.raises(ValidationError, match="invalid syntax"):
            CheckDef(type="FnCheck", name="test", fn="lambda x: x +++")

    def test_fn_check_none_allowed(self):
        """fn=None is allowed."""
        check = CheckDef(type="FnCheck", name="test", fn=None)
        assert check.fn is None

    def test_fn_check_valid_lambda(self):
        """A safe lambda expression is allowed."""
        check = CheckDef(type="FnCheck", name="test", fn="lambda x: len(x) > 0")
        assert check.fn == "lambda x: len(x) > 0"


class TestScenarioDefinition:
    """Tests for ScenarioDefinition."""

    def test_minimal_scenario(self):
        scenario = ScenarioDefinition(
            interactions=[InteractionDef(input="hello")],
            checks=[CheckDef(type="StringMatching", name="test", keyword="hello")],
        )
        assert len(scenario.interactions) == 1
        assert len(scenario.checks) == 1

    def test_default_route_through_backend(self):
        scenario = ScenarioDefinition(
            interactions=[InteractionDef(input="test")],
            checks=[],
        )
        assert scenario.route_through_backend is False

    def test_with_settings(self):
        scenario = ScenarioDefinition(
            interactions=[InteractionDef(input="test")],
            checks=[],
            settings={"eval_enabled": True},
        )
        assert scenario.settings == {"eval_enabled": True}


class TestEvalRunResponse:
    """Tests for EvalRunResponse.from_orm."""

    def test_from_orm_with_result(self):
        run = MagicMock()
        run.id = "run-1"
        run.scenario_id = "scenario-1"
        run.status = "completed"
        run.result = json.dumps(
            {
                "results": [{"name": "check1", "check_type": "StringMatching", "passed": True}],
                "passed": True,
                "agent_output": "hello",
            }
        )
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.created_at = datetime.now(timezone.utc)

        resp = EvalRunResponse.from_orm(run)
        assert resp.status == "completed"
        assert resp.passed is True
        assert resp.agent_output == "hello"
        assert len(resp.result) == 1

    def test_from_orm_with_error(self):
        run = MagicMock()
        run.id = "run-2"
        run.scenario_id = "scenario-1"
        run.status = "error"
        run.result = json.dumps({"error": "Something went wrong"})
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.created_at = datetime.now(timezone.utc)

        resp = EvalRunResponse.from_orm(run)
        assert resp.status == "error"
        assert resp.error == "Something went wrong"

    def test_from_orm_no_result(self):
        run = MagicMock()
        run.id = "run-3"
        run.scenario_id = "scenario-1"
        run.status = "running"
        run.result = None
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        run.created_at = datetime.now(timezone.utc)

        resp = EvalRunResponse.from_orm(run)
        assert resp.status == "running"
        assert resp.result is None
        assert resp.passed is None

    def test_from_orm_invalid_json_result(self):
        run = MagicMock()
        run.id = "run-4"
        run.scenario_id = "scenario-1"
        run.status = "completed"
        run.result = "not valid json{{"
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.created_at = datetime.now(timezone.utc)

        resp = EvalRunResponse.from_orm(run)
        assert resp.result is None


class TestEvalScenarioResponse:
    """Tests for EvalScenarioResponse.from_orm."""

    def test_from_orm_with_string_definition(self):
        scenario = MagicMock()
        scenario.id = "sc-1"
        scenario.agent_id = "agent-1"
        scenario.name = "test"
        scenario.description = "desc"
        scenario.definition = json.dumps(
            {
                "interactions": [{"input": "hello"}],
                "checks": [{"type": "StringMatching", "name": "test", "keyword": "hello"}],
            }
        )
        scenario.created_at = datetime.now(timezone.utc)
        scenario.updated_at = datetime.now(timezone.utc)

        resp = EvalScenarioResponse.from_orm(scenario)
        assert resp.name == "test"
        assert len(resp.definition.interactions) == 1
