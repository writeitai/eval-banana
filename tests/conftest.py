from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., Config]:
    def _make_config(**overrides: object) -> Config:
        defaults = {
            "output_dir": str((tmp_path / ".eval-banana" / "results").resolve()),
            "project_root": tmp_path.resolve(),
            "cwd": str(tmp_path.resolve()),
        }
        defaults.update(overrides)
        return Config(**defaults)

    return _make_config


@pytest.fixture
def make_check_result() -> Callable[..., CheckResult]:
    def _make_check_result(**overrides: object) -> CheckResult:
        defaults = {
            "check_id": "check_one",
            "check_type": CheckType.deterministic,
            "description": "Example check",
            "source_path": "/tmp/check.yaml",
            "status": CheckStatus.passed,
            "score": 1,
            "started_at": "2026-04-09T12:00:00+00:00",
            "completed_at": "2026-04-09T12:00:01+00:00",
            "duration_ms": 1000,
        }
        defaults.update(overrides)
        return CheckResult(**defaults)

    return _make_check_result


@pytest.fixture
def make_harness_result() -> Callable[..., HarnessResult]:
    def _make_harness_result(**overrides: object) -> HarnessResult:
        defaults = {
            "agent_type": "codex",
            "command": ["codex", "exec", "prompt"],
            "working_directory": "/tmp/project",
            "status": HarnessStatus.succeeded,
            "started_at": "2026-04-09T12:00:00+00:00",
            "completed_at": "2026-04-09T12:00:05+00:00",
            "duration_ms": 5000,
            "model": "gpt-5.4",
            "reasoning_effort": "high",
            "prompt_source": "inline",
            "prompt_artifact_path": "harness/prompt.txt",
            "stdout_path": "harness/stdout.txt",
            "stderr_path": "harness/stderr.txt",
            "result_path": "harness/result.json",
            "stdout_bytes": 12,
            "stderr_bytes": 0,
        }
        defaults.update(overrides)
        return HarnessResult(**defaults)

    return _make_harness_result
