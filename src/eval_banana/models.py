from __future__ import annotations

from enum import StrEnum
import logging
import re
from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

logger = logging.getLogger(__name__)

_CHECK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class CheckStatus(StrEnum):
    passed = "passed"
    failed = "failed"
    error = "error"


class CheckType(StrEnum):
    deterministic = "deterministic"
    llm_judge = "llm_judge"


class HarnessStatus(StrEnum):
    succeeded = "succeeded"
    failed = "failed"
    error = "error"


class BaseCheckDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    id: str
    type: CheckType
    description: str
    target_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "id must be non-empty"
            raise ValueError(msg)
        if not _CHECK_ID_PATTERN.match(stripped):
            msg = "id must match ^[a-zA-Z0-9_-]+$"
            raise ValueError(msg)
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "description must be non-empty"
            raise ValueError(msg)
        return stripped

    @field_validator("target_paths")
    @classmethod
    def validate_target_paths(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                msg = "target_paths entries must be non-empty strings"
                raise ValueError(msg)
        return value


class DeterministicCheckDefinition(BaseCheckDefinition):
    type: Literal["deterministic"]
    script: str | None = None
    script_path: str | None = None

    @model_validator(mode="after")
    def validate_script_source(self) -> DeterministicCheckDefinition:
        has_script = bool(self.script)
        has_script_path = bool(self.script_path)
        if has_script == has_script_path:
            msg = "exactly one of script or script_path must be set"
            raise ValueError(msg)
        return self


class LlmJudgeCheckDefinition(BaseCheckDefinition):
    type: Literal["llm_judge"]
    instructions: str
    model: str | None = None

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "instructions must be non-empty"
            raise ValueError(msg)
        return stripped

    @model_validator(mode="after")
    def validate_targets(self) -> LlmJudgeCheckDefinition:
        if not self.target_paths:
            msg = "target_paths must be non-empty for llm_judge checks"
            raise ValueError(msg)
        return self


CheckDefinition = Annotated[
    DeterministicCheckDefinition | LlmJudgeCheckDefinition, Field(discriminator="type")
]


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    check_type: CheckType
    description: str
    source_path: str
    tags: list[str] = Field(default_factory=list)
    status: CheckStatus
    score: int
    started_at: str
    completed_at: str
    duration_ms: int
    reason: str | None = None
    error_detail: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: int) -> int:
        if value not in {0, 1}:
            msg = "score must be 0 or 1"
            raise ValueError(msg)
        return value


class HarnessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_type: str
    command: list[str] = Field(default_factory=list)
    working_directory: str
    status: HarnessStatus
    started_at: str
    completed_at: str
    duration_ms: int
    model: str | None = None
    reasoning_effort: str | None = None
    prompt_source: Literal["inline", "file"] | None = None
    prompt_file: str | None = None
    exit_code: int | None = None
    error_detail: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    prompt_artifact_path: str | None = None
    result_path: str | None = None
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    project_root: str
    output_dir: str
    started_at: str
    completed_at: str
    duration_ms: int
    total_checks: int
    passed_checks: int
    failed_checks: int
    errored_checks: int
    points_earned: int
    total_points: int
    percentage: float
    pass_threshold: float
    meets_threshold: bool
    run_passed: bool
    checks: list[CheckResult]
    harness: HarnessResult | None = None
