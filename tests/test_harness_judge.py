from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess

import pytest

from eval_banana.config import Config
from eval_banana.harness.template import AgentTemplate
from eval_banana.models import HarnessJudgeCheckDefinition
from eval_banana.runners.harness_judge import _extract_last_verdict
from eval_banana.runners.harness_judge import run_harness_judge_check


def _make_check(*, model: str | None = None) -> HarnessJudgeCheckDefinition:
    return HarnessJudgeCheckDefinition(
        schema_version=1,
        id="judge_check",
        type="harness_judge",
        description="Judge the README.",
        target_paths=["README.md"],
        instructions="Return score 1 when install steps are clear.",
        model=model,
    )


def _completed_process(
    *, stdout: str, stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["codex", "exec"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_extract_last_verdict_prefers_last_valid_json() -> None:
    score, reason = _extract_last_verdict(
        text=(
            '{"type":"progress","msg":"reading"}\n'
            '{"score": 0, "reason": "old"}\n'
            '{"score": 1, "reason": "new"}'
        )
    )

    assert score == 1
    assert reason == "new"


def test_harness_judge_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install with uv sync", encoding="utf-8")
    captured: dict[str, object] = {}
    template = AgentTemplate(
        command=("codex", "exec"), model_flag="--model", default_model="gpt-5.4"
    )

    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template", lambda **kwargs: template
    )

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return _completed_process(stdout='{"score": 1, "reason": "Looks good."}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"
    assert result.reason == "Looks good."
    assert result.check_type.value == "harness_judge"
    assert result.details["model"] == "gpt-5.4"
    assert captured["timeout"] == 300
    assert captured["cwd"] == tmp_path
    assert captured["capture_output"] is True
    assert captured["text"] is True


def test_missing_target_file_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "FileNotFoundError" in (result.error_detail or "")


def test_malformed_json_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: _completed_process(stdout="not json"),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "valid JSON verdict" in (result.error_detail or "")


def test_invalid_score_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            stdout='{"score": 2, "reason": "invalid"}'
        ),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "valid JSON verdict" in (result.error_detail or "")


def test_missing_binary_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            FileNotFoundError("missing codex")
        ),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "FileNotFoundError" in (result.error_detail or "")


def test_non_zero_exit_with_valid_json_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            stdout='{"score": 1, "reason": "ok"}', returncode=1
        ),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"
    assert result.exit_code == 1


def test_non_zero_exit_without_json_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: _completed_process(stdout="failure", returncode=1),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "Agent exited with code 1" in (result.error_detail or "")


def test_per_check_model_override_reaches_subprocess_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec"), model_flag="--model"),
    )

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["args"] = command
        return _completed_process(stdout='{"score": 1, "reason": "ok"}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(model="gpt-5.4"),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"
    assert "--model" in captured["args"]
    assert "gpt-5.4" in captured["args"]


def test_prompt_includes_all_target_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Readme text", encoding="utf-8")
    (tmp_path / "docs.md").write_text("Docs text", encoding="utf-8")
    captured: dict[str, object] = {}
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
        target_paths=["README.md", "docs.md"],
        instructions="Judge both files.",
    )

    run_harness_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    prompt = captured["args"][-1]
    assert "Readme text" in prompt
    assert "Docs text" in prompt
    assert "--- BEGIN FILE: README.md" in prompt
    assert "--- BEGIN FILE: docs.md" in prompt


def test_prompt_truncates_target_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("abcdefghij", encoding="utf-8")
    captured: dict[str, object] = {}
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

    run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(
            project_root=tmp_path, harness_agent="codex", llm_max_input_chars=5
        ),
    )

    prompt = captured["args"][-1]
    assert "abcde" in prompt
    assert "[TRUNCATED]" in prompt


def test_pretty_printed_multiline_json_is_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            stdout='{\n  "score": 1,\n  "reason": "ok"\n}'
        ),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"


def test_timeout_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(
                cmd=["codex", "exec"],
                timeout=300,
                output="partial stdout",
                stderr="partial stderr",
            )
        ),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "timed out" in (result.error_detail or "")
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"
