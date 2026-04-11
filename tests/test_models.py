from __future__ import annotations

from pydantic import TypeAdapter
from pydantic import ValidationError
import pytest

from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType

_ADAPTER = TypeAdapter(CheckDefinition)


def test_valid_definitions_parse() -> None:
    deterministic = _ADAPTER.validate_python(
        {
            "schema_version": 1,
            "id": "check_1",
            "type": "deterministic",
            "description": "desc",
            "script": "print('ok')",
        }
    )
    llm = _ADAPTER.validate_python(
        {
            "schema_version": 1,
            "id": "check-2",
            "type": "llm_judge",
            "description": "desc",
            "target_paths": ["README.md"],
            "instructions": "judge it",
        }
    )
    task = _ADAPTER.validate_python(
        {
            "schema_version": 1,
            "id": "check3",
            "type": "task_based",
            "description": "desc",
            "command": ["pytest"],
        }
    )

    assert deterministic.id == "check_1"
    assert llm.id == "check-2"
    assert task.id == "check3"


def test_invalid_union_fails() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "schema_version": 1,
                "id": "oops",
                "type": "missing",
                "description": "desc",
            }
        )


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "schema_version": 1,
                "id": "check_1",
                "type": "deterministic",
                "description": "desc",
                "script": "print('ok')",
                "unknown": True,
            }
        )


def test_schema_version_is_required() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "id": "check_1",
                "type": "deterministic",
                "description": "desc",
                "script": "print('ok')",
            }
        )


def test_id_format_validation() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "schema_version": 1,
                "id": "bad id",
                "type": "deterministic",
                "description": "desc",
                "script": "print('ok')",
            }
        )


def test_score_validator_enforces_zero_or_one() -> None:
    with pytest.raises(ValidationError):
        CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path="/tmp/check.yaml",
            status=CheckStatus.passed,
            score=2,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )


def test_task_based_definition_accepts_optional_harness_and_model() -> None:
    task = _ADAPTER.validate_python(
        {
            "schema_version": 1,
            "id": "task_with_harness",
            "type": "task_based",
            "description": "desc",
            "command": ["prompt", "--json"],
            "harness": "codex",
            "model": "gpt-5.4",
        }
    )

    assert task.harness == "codex"
    assert task.model == "gpt-5.4"


def test_task_based_definition_still_requires_command() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "schema_version": 1,
                "id": "task_missing_command",
                "type": "task_based",
                "description": "desc",
            }
        )


def test_task_based_definition_rejects_model_without_harness() -> None:
    with pytest.raises(
        ValidationError,
        match="task_based.model requires task_based.harness to also be set",
    ):
        _ADAPTER.validate_python(
            {
                "schema_version": 1,
                "id": "task_bad_model",
                "type": "task_based",
                "description": "desc",
                "command": ["pytest"],
                "model": "gpt-5.4",
            }
        )
