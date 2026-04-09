from __future__ import annotations

import base64
from collections.abc import Callable
import json
from pathlib import Path
import time

import pytest

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType


def _encode_segment(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


@pytest.fixture
def make_jwt() -> Callable[..., str]:
    def _make_jwt(*, account_id: str = "acct_123", exp: int | None = None) -> str:
        if exp is None:
            exp = int(time.time()) + 3600
        header = _encode_segment({"alg": "none", "typ": "JWT"})
        payload = _encode_segment(
            {
                "exp": exp,
                "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
            }
        )
        return f"{header}.{payload}.signature"

    return _make_jwt


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
