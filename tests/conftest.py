from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType


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
