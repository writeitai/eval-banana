from __future__ import annotations

from collections.abc import Callable

from pydantic import TypeAdapter
from pydantic import ValidationError
import pytest

from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import EvalReport
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus

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

    assert deterministic.id == "check_1"
    assert llm.id == "check-2"


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


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": 1,
            "id": "foo",
            "type": "deterministic",
            "description": "d",
            "script": "pass",
            "timeout_seconds": 30,
        },
        {
            "schema_version": 1,
            "id": "foo",
            "type": "llm_judge",
            "description": "d",
            "target_paths": ["README.md"],
            "instructions": "grade",
            "timeout_seconds": 30,
        },
    ],
    ids=["deterministic", "llm_judge"],
)
def test_stale_timeout_seconds_yaml_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(payload)


def test_harness_result_validates_and_serializes_cleanly() -> None:
    result = HarnessResult(
        agent_type="codex",
        command=["codex", "exec", "Prompt"],
        working_directory="/tmp/project",
        status=HarnessStatus.succeeded,
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:05+00:00",
        duration_ms=5000,
        stdout_bytes=10,
        stderr_bytes=0,
    )

    payload = result.model_dump()

    assert payload["status"] == HarnessStatus.succeeded
    assert payload["stdout_bytes"] == 10


def test_eval_report_accepts_nested_harness_data(
    make_check_result: Callable[..., CheckResult],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    report = EvalReport(
        run_id="run1",
        project_root="/tmp/project",
        output_dir="/tmp/out",
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:10+00:00",
        duration_ms=10000,
        total_checks=1,
        passed_checks=1,
        failed_checks=0,
        errored_checks=0,
        points_earned=1,
        total_points=1,
        percentage=100.0,
        pass_threshold=1.0,
        meets_threshold=True,
        run_passed=True,
        checks=[make_check_result()],
        harness=make_harness_result(),
    )

    dumped = report.model_dump_json()

    assert report.harness is not None
    assert '"harness"' in dumped


def test_eval_report_serializes_harness_as_null_when_absent() -> None:
    report = EvalReport(
        run_id="run1",
        project_root="/tmp/project",
        output_dir="/tmp/out",
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:10+00:00",
        duration_ms=10000,
        total_checks=0,
        passed_checks=0,
        failed_checks=0,
        errored_checks=0,
        points_earned=0,
        total_points=0,
        percentage=0.0,
        pass_threshold=1.0,
        meets_threshold=False,
        run_passed=False,
        checks=[],
    )

    assert '"harness":null' in report.model_dump_json()
