from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from eval_banana.harness.runner import run_harness
from eval_banana.harness.template import AgentTemplate
from eval_banana.models import HarnessStatus


def test_run_harness_success_writes_all_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        check: bool,
        cwd: Path,
        env: dict[str, str],
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured.update(
            {
                "command": list(command),
                "capture_output": capture_output,
                "check": check,
                "cwd": cwd,
                "env": dict(env),
                "text": text,
            }
        )
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="ok\n", stderr=""
        )

    monkeypatch.setattr("eval_banana.harness.runner.subprocess.run", fake_run)
    result = run_harness(
        agent_type="codex",
        template=AgentTemplate(
            command=("codex", "exec"), default_model="gpt-5.4", reasoning_effort="high"
        ),
        prompt="Fix the repo",
        prompt_source="inline",
        prompt_file=None,
        project_root=tmp_path,
        run_id="run1",
        run_output_dir=tmp_path / "out",
        harness_env={"CI": "1"},
    )
    result_payload = json.loads(
        (tmp_path / "out" / "harness" / "result.json").read_text()
    )

    assert result.status == HarnessStatus.succeeded
    assert result.command == ["codex", "exec", "--model", "gpt-5.4", "Fix the repo"]
    assert result.model == "gpt-5.4"
    assert result.reasoning_effort == "high"
    assert result.prompt_source == "inline"
    assert result.stdout_bytes == 3
    assert result.stderr_bytes == 0
    assert (tmp_path / "out" / "harness" / "prompt.txt").read_text() == "Fix the repo"
    assert (tmp_path / "out" / "harness" / "stdout.txt").read_text() == "ok\n"
    assert (tmp_path / "out" / "harness" / "stderr.txt").read_text() == ""
    assert captured["capture_output"] is True
    assert captured["check"] is False
    assert captured["cwd"] == tmp_path
    assert captured["text"] is True
    assert captured["env"]["CI"] == "1"
    assert captured["env"]["EVAL_BANANA_PROJECT_ROOT"] == str(tmp_path)
    assert captured["env"]["EVAL_BANANA_RUN_ID"] == "run1"
    assert captured["env"]["EVAL_BANANA_RUN_OUTPUT_DIR"] == str(tmp_path / "out")
    assert captured["env"]["EVAL_BANANA_OUTPUT_DIR"] == str(
        tmp_path / "out" / "harness"
    )
    assert captured["env"]["EVAL_BANANA_HARNESS_AGENT"] == "codex"
    assert result_payload["status"] == HarnessStatus.succeeded
    assert result_payload["stdout_bytes"] == 3
    assert result_payload["prompt_artifact_path"] == "harness/prompt.txt"


def test_run_harness_nonzero_exit_maps_to_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "eval_banana.harness.runner.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            args=command, returncode=2, stdout="", stderr="bad"
        ),
    )

    result = run_harness(
        agent_type="codex",
        template=AgentTemplate(command=("codex", "exec")),
        prompt="Fix the repo",
        prompt_source="inline",
        prompt_file=None,
        project_root=tmp_path,
        run_id="run1",
        run_output_dir=tmp_path / "out",
    )

    assert result.status == HarnessStatus.failed
    assert result.exit_code == 2


def test_run_harness_missing_binary_maps_to_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        check: bool,
        cwd: Path,
        env: dict[str, str],
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("No such file or directory: 'codex'")

    monkeypatch.setattr("eval_banana.harness.runner.subprocess.run", fake_run)

    result = run_harness(
        agent_type="codex",
        template=AgentTemplate(command=("codex", "exec")),
        prompt="Fix the repo",
        prompt_source="inline",
        prompt_file=None,
        project_root=tmp_path,
        run_id="run1",
        run_output_dir=tmp_path / "out",
    )

    assert result.status == HarnessStatus.error
    assert result.exit_code is None
    assert "No such file or directory" in (result.error_detail or "")
    assert (tmp_path / "out" / "harness" / "stdout.txt").read_text() == ""
    assert (tmp_path / "out" / "harness" / "stderr.txt").read_text() == ""


def test_run_harness_env_merge_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setenv("SHARED", "os")
    monkeypatch.setenv("MODEL_ENV", "os-model")

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        check: bool,
        cwd: Path,
        env: dict[str, str],
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal captured
        captured = dict(env)
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.harness.runner.subprocess.run", fake_run)

    run_harness(
        agent_type="claude",
        template=AgentTemplate(
            command=("claude",),
            provider_env=(("SHARED", "provider"), ("MODEL_ENV", "provider-model")),
            model_env_vars=("MODEL_ENV",),
            default_model="template-model",
        ),
        prompt="Prompt",
        prompt_source="inline",
        prompt_file=None,
        project_root=tmp_path,
        run_id="run1",
        run_output_dir=tmp_path / "out",
        harness_env={"SHARED": "harness", "MODEL_ENV": "harness-model"},
    )

    assert captured["SHARED"] == "harness"
    assert captured["MODEL_ENV"] == "template-model"
    assert captured["EVAL_BANANA_HARNESS_AGENT"] == "claude"


def test_run_harness_applies_harness_reasoning_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_args: list[str] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        check: bool,
        cwd: Path,
        env: dict[str, str],
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal captured_args
        captured_args = list(command)
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.harness.runner.subprocess.run", fake_run)

    run_harness(
        agent_type="codex",
        template=AgentTemplate(
            command=("codex", "exec"),
            reasoning_effort="high",
            reasoning_effort_flag=("-c", "model_reasoning_effort={effort}"),
        ),
        prompt="Prompt",
        prompt_source="inline",
        prompt_file=None,
        project_root=tmp_path,
        run_id="run1",
        run_output_dir=tmp_path / "out",
    )

    assert "model_reasoning_effort=high" in captured_args
