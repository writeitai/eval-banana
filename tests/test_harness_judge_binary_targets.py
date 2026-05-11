from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
import subprocess

import pytest

from eval_banana.config import Config
from eval_banana.harness.template import AgentTemplate
from eval_banana.models import HarnessJudgeCheckDefinition
from eval_banana.runners.harness_judge import run_harness_judge_check


def _completed_process(
    *, stdout: str, stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["judge"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_binary_target_is_prompt_metadata_without_embedded_nul(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    target_bytes = b"DuckDB\x00binary\x00content"
    target_path = tmp_path / "target.duckdb"
    target_path.write_bytes(target_bytes)
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("judge",), prompt_flag="--prompt"),
    )

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["args"] = command
        return _completed_process(stdout='{"score": 1, "reason": "ok"}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    check = HarnessJudgeCheckDefinition(
        schema_version=1,
        id="judge_check",
        type="harness_judge",
        description="desc",
        target_paths=["target.duckdb"],
        instructions="Judge the binary target.",
    )

    result = run_harness_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    prompt = captured["args"][-1]
    assert result.status.value == "passed"
    assert all("\x00" not in arg for arg in captured["args"])
    assert "Binary target content omitted." in prompt
    assert "Relative path: target.duckdb" in prompt
    assert f"Resolved path: {target_path.resolve()}" in prompt
    assert f"Byte size: {len(target_bytes)}" in prompt
    assert f"SHA-256: {hashlib.sha256(target_bytes).hexdigest()}" in prompt
    assert target_bytes.decode("utf-8") not in prompt
