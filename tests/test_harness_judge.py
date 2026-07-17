from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import subprocess

import pytest

from eval_banana.config import Config
from eval_banana.harness.template import AgentTemplate
from eval_banana.models import HarnessJudgeCheckDefinition
from eval_banana.reporter import safe_file_stem
from eval_banana.runners.harness_judge import _extract_last_verdict
from eval_banana.runners.harness_judge import run_harness_judge_check

_CHECK_DEFINITION_SHA256 = "sha256:" + "0" * 64


def _make_check(*, model: str | None = None) -> HarnessJudgeCheckDefinition:
    return HarnessJudgeCheckDefinition(
        schema_version=1,
        id="judge_check",
        type="harness_judge",
        description="Judge the README.",
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
    """Use the final verdict when a plain response contains several objects."""

    score, reason = _extract_last_verdict(
        text=(
            '{"type":"progress","msg":"reading"}\n'
            '{"score": 0, "reason": "old"}\n'
            '{"score": 1, "reason": "new"}'
        )
    )

    assert score == 1
    assert reason == "new"


def test_extract_last_verdict_unwraps_successful_stream_result() -> None:
    """Prefer Claude's terminal stream result over an earlier score example."""

    stdout = "\n".join(
        [
            '{"score": 1, "reason": "earlier example"}',
            json.dumps(
                obj={
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": (
                        "Final judgment:\n```json\n"
                        '{"score": 0, "reason": "work is incomplete"}'
                        "\n```"
                    ),
                }
            ),
        ]
    )

    score, reason = _extract_last_verdict(text=stdout)

    assert score == 0
    assert reason == "work is incomplete"


def test_extract_last_verdict_rejects_tool_result_decoy() -> None:
    """Do not accept a tool payload when the terminal result has no verdict."""

    stdout = "\n".join(
        [
            json.dumps(
                obj={
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "content": '{"score": 1, "reason": "decoy"}',
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                obj={
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "No verdict was produced.",
                }
            ),
        ]
    )

    with pytest.raises(ValueError, match="valid JSON verdict"):
        _extract_last_verdict(text=stdout)


def test_extract_last_verdict_rejects_failed_result_decoy() -> None:
    """Do not accept a verdict carried by an unsuccessful terminal event."""

    stdout = json.dumps(
        obj={
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": '{"score": 1, "reason": "decoy"}',
        }
    )

    with pytest.raises(ValueError, match="valid JSON verdict"):
        _extract_last_verdict(text=stdout)


def test_harness_judge_stream_result_score_zero_is_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Classify a valid score-zero Claude stream result as failed, not error."""

    stdout = json.dumps(
        obj={
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": '{"score": 0, "reason": "program is incomplete"}',
        }
    )

    def fake_run(
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Return a successful process containing a Claude-style result event."""

        return _completed_process(stdout=stdout)

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="claude"),
    )

    assert result.status.value == "failed"
    assert result.score == 0
    assert result.reason == "program is incomplete"
    assert result.error_detail is None


def test_harness_judge_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install with uv sync", encoding="utf-8")
    captured: dict[str, object] = {}
    template = AgentTemplate(
        command=("codex", "exec"),
        model_flag="--model",
        default_model="gpt-5.6-sol",
        reasoning_effort="medium",
        reasoning_effort_flag=("-c", "model_reasoning_effort={effort}"),
    )

    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template", lambda **kwargs: template
    )

    def fake_run(
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Capture the keyword-only subprocess contract used by the runner."""

        captured["command"] = args
        captured.update(kwargs)
        return _completed_process(stdout='{"score": 1, "reason": "Looks good."}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(
            project_root=tmp_path,
            harness_agent="codex",
            harness_reasoning_effort="xhigh",
        ),
    )

    assert result.status.value == "passed"
    assert result.reason == "Looks good."
    assert result.check_type.value == "harness_judge"
    assert result.check_definition_sha256 == _CHECK_DEFINITION_SHA256
    assert result.details["agent_type"] == "codex"
    assert result.details["model"] == "gpt-5.6-sol"
    assert result.details["reasoning_effort"] == "xhigh"
    assert result.details["timeout_seconds"] == 300
    captured_command = captured["command"]
    assert isinstance(captured_command, list)
    assert "model_reasoning_effort=xhigh" in captured_command
    assert captured["timeout"] == 300
    assert captured["cwd"] == tmp_path
    assert captured["capture_output"] is True
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["text"] is True
    stem = safe_file_stem(text="judge_check")
    prompt_path = tmp_path / "out" / "checks" / f"{stem}.prompt.txt"
    assert prompt_path.read_text(encoding="utf-8") == captured_command[-1]


def test_configured_harness_timeout_reaches_process_and_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Bind a long-running judge's configured timeout into report provenance."""

    captured: dict[str, object] = {}

    def fake_run(
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Capture the effective subprocess timeout without launching an agent."""

        captured["args"] = args
        captured.update(kwargs)
        return _completed_process(stdout='{"score": 1, "reason": "complete"}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(
            project_root=tmp_path, harness_agent="codex", harness_timeout_seconds=10800
        ),
    )

    assert result.status.value == "passed"
    assert captured["timeout"] == 10800
    assert result.details["timeout_seconds"] == 10800


def test_model_without_template_injection_surface_errors_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(command=("model-blind-agent",), model_flag=None),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: pytest.fail("unsupported model must not launch"),
    )

    result = run_harness_judge_check(
        check=_make_check(model="requested-model"),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="custom"),
    )

    assert result.status.value == "error"
    assert result.score == 0
    assert "cannot inject" in (result.error_detail or "")
    assert "requested-model" in (result.error_detail or "")
    assert result.details["model"] is None
    assert result.details["reasoning_effort"] is None


def test_reasoning_effort_without_placeholder_errors_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.resolve_template",
        lambda **kwargs: AgentTemplate(
            command=("effort-blind-agent",),
            model_flag=None,
            reasoning_effort_flag=("--effort",),
        ),
    )
    monkeypatch.setattr(
        "eval_banana.runners.harness_judge.subprocess.run",
        lambda *args, **kwargs: pytest.fail("unsupported effort must not launch"),
    )

    result = run_harness_judge_check(
        check=_make_check(),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(
            project_root=tmp_path,
            harness_agent="custom",
            harness_reasoning_effort="xhigh",
        ),
    )

    assert result.status.value == "error"
    assert result.score == 0
    assert "cannot inject" in (result.error_detail or "")
    assert "reasoning effort 'xhigh'" in (result.error_detail or "")
    assert "{effort} placeholder" in (result.error_detail or "")
    assert result.details["model"] is None
    assert result.details["reasoning_effort"] is None


def test_stock_codex_model_and_effort_remain_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Capture the stock command assembled for the subprocess."""

        captured["command"] = args
        return _completed_process(stdout='{"score": 1, "reason": "ok"}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"
    assert result.details["model"] == "gpt-5.6-sol"
    assert result.details["reasoning_effort"] == "high"
    assert "--model" in captured["command"]
    assert "gpt-5.6-sol" in captured["command"]
    assert "model_reasoning_effort=high" in captured["command"]


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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "FileNotFoundError" in (result.error_detail or "")


def test_non_zero_exit_with_valid_json_is_an_error(
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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert result.score == 0
    assert result.exit_code == 1
    assert "exited with code 1" in (result.error_detail or "")


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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
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
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Capture the per-check model command assembled by the runner."""

        captured["args"] = args
        return _completed_process(stdout='{"score": 1, "reason": "ok"}')

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    result = run_harness_judge_check(
        check=_make_check(model="gpt-5.6-sol"),
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "passed"
    assert "--model" in captured["args"]
    assert "gpt-5.6-sol" in captured["args"]


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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
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
        check_definition_sha256=_CHECK_DEFINITION_SHA256,
        source_path=tmp_path / "eval_checks" / "judge.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, harness_agent="codex"),
    )

    assert result.status.value == "error"
    assert "timed out" in (result.error_detail or "")
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"
    stem = safe_file_stem(text="judge_check")
    prompt_path = tmp_path / "out" / "checks" / f"{stem}.prompt.txt"
    assert "Check Description:\nJudge the README." in prompt_path.read_text(
        encoding="utf-8"
    )
