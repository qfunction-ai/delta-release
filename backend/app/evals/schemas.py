"""Pydantic schemas for eval API."""

import ast
import json
import re
from datetime import datetime

from pydantic import BaseModel, field_validator


class InteractionDef(BaseModel):
    """A single interaction turn in a scenario."""

    input: str


class CheckDef(BaseModel):
    """A check to apply to a scenario's results."""

    type: str  # StringMatching, RegexMatching, Equals, NotEquals, FnCheck, Conformity, LLMJudge
    name: str
    keyword: str | None = None
    pattern: str | None = None
    expected: str | None = None
    key: str | None = None  # JSONPath for Equals/NotEquals (default: trace.last.outputs)
    fn: str | None = None
    rule: str | None = None  # Conformity
    prompt: str | None = None  # LLMJudge

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"StringMatching", "RegexMatching", "Equals", "NotEquals", "FnCheck", "Conformity", "LLMJudge"}
        if v not in allowed:
            raise ValueError(f"Check type must be one of {allowed}, got '{v}'")
        return v

    @field_validator("fn")
    @classmethod
    def validate_fn(cls, v: str | None) -> str | None:
        """Defense-in-depth validation for FnCheck expressions.

        The eval container has its own validation, but we reject dangerous
        patterns at the API layer too so they never reach the container.
        """
        if v is None:
            return v
        # Must be a lambda expression
        stripped = v.strip()
        if not stripped.startswith("lambda"):
            raise ValueError("FnCheck expression must be a lambda expression")
        # Block dangerous patterns — regex catches what the AST can't
        # (string-based attacks, dunder fragments, structural patterns).
        # Module access patterns (os., subprocess., etc.) are NOT checked
        # here because regex can't distinguish string literals from code.
        # Those are checked via AST attribute access below.
        _DANGEROUS_PATTERNS = [
            re.compile(r"__\w+__"),  # dunder attributes
            re.compile(r"import\s"),  # imports
            re.compile(r"exec\s*\("),  # exec calls
            re.compile(r"eval\s*\("),  # eval calls
            re.compile(r"compile\s*\("),  # compile calls
            re.compile(r"open\s*\("),  # file access
        ]
        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(v):
                raise ValueError(f"FnCheck expression contains forbidden pattern: {pattern.pattern}")
        # AST-level checks
        try:
            tree = ast.parse(v, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"FnCheck expression has invalid syntax: {e}") from e

        # Modules whose attribute access is forbidden in FnCheck expressions
        _FORBIDDEN_MODULES = {
            "os",
            "subprocess",
            "shutil",
            "ctypes",
            "pickle",
            "marshal",
            "socket",
            "http",
            "urllib",
            "requests",
            "httpx",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("FnCheck expression must not contain imports")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in (
                    "exec",
                    "eval",
                    "compile",
                    "open",
                    "__import__",
                    "getattr",
                    "type",
                    "hasattr",  # sandbox escape enablers
                ):
                    raise ValueError(f"FnCheck expression must not call {func.id}")
            # Block attribute access on forbidden modules
            # Catches os.system(), subprocess.call(), etc.
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in _FORBIDDEN_MODULES:
                    raise ValueError(f"FnCheck expression must not access {node.value.id}.{node.attr}")
            # Block string constants with dunder fragments
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value
                if re.search(r"^__\w+$", val) or re.search(r"^\w+__$", val):
                    raise ValueError(f"FnCheck string constant contains dunder fragment: {val!r}")
        return v


class ScenarioDefinition(BaseModel):
    """The full scenario definition (interactions + checks)."""

    interactions: list[InteractionDef]
    checks: list[CheckDef]
    route_through_backend: bool = False  # When True, eval routes through Delta backend
    settings: dict[str, bool | str | int] | None = None  # Settings to apply before running


class EvalScenarioCreate(BaseModel):
    """Create a new eval scenario."""

    agent_id: str
    name: str
    description: str | None = None
    definition: ScenarioDefinition


class EvalScenarioUpdate(BaseModel):
    """Update an eval scenario."""

    name: str | None = None
    description: str | None = None
    agent_id: str | None = None
    definition: ScenarioDefinition | None = None


class EvalRunFromFile(BaseModel):
    """Run an eval from a YAML file path."""

    file_path: str
    agent_id: str | None = None  # Override agent_id from file


class EvalResultItem(BaseModel):
    """Result of a single check."""

    name: str
    check_type: str
    passed: bool
    detail: str | None = None


class EvalScenarioResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    description: str | None
    definition: ScenarioDefinition
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, scenario) -> "EvalScenarioResponse":
        defn = json.loads(scenario.definition) if isinstance(scenario.definition, str) else scenario.definition
        return cls(
            id=str(scenario.id),
            agent_id=scenario.agent_id,
            name=scenario.name,
            description=scenario.description,
            definition=defn,
            created_at=scenario.created_at,
            updated_at=scenario.updated_at,
        )


class EvalScenarioListResponse(BaseModel):
    scenarios: list[EvalScenarioResponse]
    total: int


class EvalRunResponse(BaseModel):
    id: str
    scenario_id: str
    status: str
    result: list[EvalResultItem] | None = None
    agent_output: str | None = None
    passed: bool | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_orm(cls, run) -> "EvalRunResponse":
        result_items = None
        passed = None
        agent_output = None
        error = None

        if run.result:
            try:
                data = json.loads(run.result) if isinstance(run.result, str) else run.result
                result_items = [EvalResultItem(**r) for r in data.get("results", [])]
                passed = data.get("passed")
                agent_output = data.get("agent_output")
                error = data.get("error")
            except (json.JSONDecodeError, TypeError):
                pass

        return cls(
            id=str(run.id),
            scenario_id=str(run.scenario_id),
            status=run.status,
            result=result_items,
            agent_output=agent_output,
            passed=passed,
            error=error,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunResponse]
    total: int
