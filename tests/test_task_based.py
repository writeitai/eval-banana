from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import subprocess
from typing import cast

import pytest

from eval_banana.config import Config
from eval_banana.config import HarnessConfig
from eval_banana.models import TaskBasedCheckDefinition
from eval_banana.runners.task_based import _reset_warn_state
from eval_banana.runners.task_based import run_task_based_check


@pytest.fixture(autouse=True)
def reset_harness_warn_state() -> None:
    _reset_warn_state()


def _make_task_check(
    *,
    check_id: str = "task_check",
    description: str = "desc",
    command: list[str] | None = None,
    harness: str | None = None,
    model: str | None = None,
    working_directory: str | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> TaskBasedCheckDefinition:
    return TaskBasedCheckDefinition(
        schema_version=1,
        id=check_id,
        type="task_based",
        description=description,
        command=command or ["pytest"],
        harness=harness,
        model=model,
        working_directory=working_directory,
        env=env or {},
        timeout_seconds=timeout_seconds,
    )


def _make_source_path(*, tmp_path: Path) -> Path:
    source_path = tmp_path / "eval_checks" / "task.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    return source_path


def test_pass_fail_and_error_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    check = _make_task_check()
    responses = [
        subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="ok", stderr=""
        ),
        subprocess.CompletedProcess(
            args=["pytest"], returncode=1, stdout="", stderr="bad"
        ),
        FileNotFoundError("missing"),
    ]

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)

    passed = run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )
    failed = run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )
    errored = run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert passed.status == "passed"
    assert failed.status == "failed"
    assert errored.status == "error"


def test_task_based_runner_preserves_legacy_command_path_without_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        captured["env"] = kwargs["env"]
        captured["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(
            args=["uv", "run", "pytest"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    check = _make_task_check(
        check_id="legacy_task",
        command=["uv", "run", "pytest", "tests", "-q"],
        env={"CUSTOM": "1"},
    )

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path, task_timeout_seconds=123),
    )

    expected_env = dict(os.environ)
    expected_env.update({"CUSTOM": "1"})
    expected_env["EVAL_BANANA_PROJECT_ROOT"] = str(tmp_path)
    expected_env["EVAL_BANANA_OUTPUT_DIR"] = str(tmp_path / "out" / "checks" / check.id)
    expected_env["EVAL_BANANA_CHECK_ID"] = check.id

    assert captured["argv"] == ["uv", "run", "pytest", "tests", "-q"]
    assert captured["env"] == expected_env
    assert captured["timeout"] == 123


def test_task_based_runner_merges_harness_command_flags_model_and_check_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "codex": HarnessConfig(
                command=["codex", "exec"],
                shared_flags=["--skip-git-repo-check"],
                default_model="gpt-5.4",
                model_flag="--model",
            )
        },
    )
    check = _make_task_check(harness="codex", command=["Write", "a", "summary"])

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["argv"] == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.4",
        "Write",
        "a",
        "summary",
    ]


def test_task_based_runner_treats_check_command_as_appended_args_not_full_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path, harnesses={"claude": HarnessConfig(command=["claude"])}
    )
    check = _make_task_check(harness="claude", command=["claude", "hello"])

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["argv"] == ["claude", "claude", "hello"]


def test_task_based_runner_omits_model_flag_when_no_model_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        return subprocess.CompletedProcess(
            args=["gemini"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "gemini": HarnessConfig(
                command=["gemini"],
                shared_flags=["--approval-mode=yolo"],
                model_flag="--model",
            )
        },
    )
    check = _make_task_check(harness="gemini", command=["prompt"])

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["argv"] == ["gemini", "--approval-mode=yolo", "prompt"]


def test_task_based_runner_sets_all_model_env_vars_only_when_model_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured_envs: list[dict[str, str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_envs.append(cast(dict[str, str], kwargs["env"]))
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "claude": HarnessConfig(
                command=["claude"],
                model_env_vars=["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"],
            )
        },
    )

    run_task_based_check(
        check=_make_task_check(
            check_id="selected_model",
            harness="claude",
            model="anthropic/claude-sonnet-4.6",
            command=["prompt"],
        ),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )
    run_task_based_check(
        check=_make_task_check(
            check_id="no_model", harness="claude", command=["prompt"]
        ),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured_envs[0]["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4.6"
    assert (
        captured_envs[0]["ANTHROPIC_DEFAULT_SONNET_MODEL"]
        == "anthropic/claude-sonnet-4.6"
    )
    assert "ANTHROPIC_MODEL" not in captured_envs[1]
    assert "ANTHROPIC_DEFAULT_SONNET_MODEL" not in captured_envs[1]


def test_task_based_runner_check_model_overrides_harness_default_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = args[0]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "codex": HarnessConfig(
                command=["codex", "exec"],
                default_model="default-model",
                model_flag="--model",
                model_env_vars=["CODEX_MODEL", "CODEX_FALLBACK_MODEL"],
            )
        },
    )

    run_task_based_check(
        check=_make_task_check(
            harness="codex", model="override-model", command=["prompt"]
        ),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["argv"] == ["codex", "exec", "--model", "override-model", "prompt"]
    assert captured["env"]["CODEX_MODEL"] == "override-model"
    assert captured["env"]["CODEX_FALLBACK_MODEL"] == "override-model"


def test_task_based_runner_resolves_provider_env_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")
    monkeypatch.setenv("API_HOST", "openrouter.ai")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "claude_openrouter": HarnessConfig(
                command=["claude"],
                provider_env={
                    "ANTHROPIC_AUTH_TOKEN": "{env:OPENROUTER_API_KEY}",
                    "ANTHROPIC_BASE_URL": "https://{env:API_HOST}/api",
                },
            )
        },
    )

    run_task_based_check(
        check=_make_task_check(harness="claude_openrouter", command=["prompt"]),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["env"]["ANTHROPIC_AUTH_TOKEN"] == "router-secret"
    assert captured["env"]["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"


def test_task_based_runner_warns_once_and_substitutes_empty_for_missing_placeholder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured_envs: list[dict[str, str]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_envs.append(cast(dict[str, str], kwargs["env"]))
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "claude": HarnessConfig(
                command=["claude"],
                provider_env={
                    "AUTH_HEADER": "Bearer {env:MISSING_TOKEN}",
                    "SECOND_HEADER": "Token {env:MISSING_TOKEN}",
                },
            )
        },
    )

    with caplog.at_level("WARNING"):
        run_task_based_check(
            check=_make_task_check(harness="claude", command=["prompt"]),
            source_path=source_path,
            project_root=tmp_path,
            output_dir=tmp_path / "out" / "checks",
            config=config,
        )
        run_task_based_check(
            check=_make_task_check(
                check_id="second_run", harness="claude", command=["prompt"]
            ),
            source_path=source_path,
            project_root=tmp_path,
            output_dir=tmp_path / "out" / "checks",
            config=config,
        )

    warnings = [
        record.message
        for record in caplog.records
        if "Harness env placeholder {env:MISSING_TOKEN} is unset" in record.message
    ]

    assert warnings == [
        "Harness env placeholder {env:MISSING_TOKEN} is unset; substituting empty string"
    ]
    assert captured_envs[0]["AUTH_HEADER"] == "Bearer "
    assert captured_envs[0]["SECOND_HEADER"] == "Token "
    assert captured_envs[1]["AUTH_HEADER"] == "Bearer "


def test_task_based_runner_omits_env_key_when_entire_value_is_single_unset_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "claude": HarnessConfig(
                command=["claude"],
                provider_env={"ANTHROPIC_AUTH_TOKEN": "{env:OPENROUTER_API_KEY}"},
            )
        },
    )

    run_task_based_check(
        check=_make_task_check(harness="claude", command=["prompt"]),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in captured["env"]


def test_task_based_runner_check_env_overrides_harness_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={
            "codex": HarnessConfig(
                command=["codex", "exec"], provider_env={"TOKEN": "from-harness"}
            )
        },
    )

    run_task_based_check(
        check=_make_task_check(
            harness="codex", command=["prompt"], env={"TOKEN": "from-check"}
        ),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["env"]["TOKEN"] == "from-check"


def test_task_based_runner_check_env_values_not_interpolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={"codex": HarnessConfig(command=["codex", "exec"])},
    )

    with caplog.at_level("WARNING"):
        run_task_based_check(
            check=_make_task_check(
                harness="codex",
                command=["prompt"],
                env={"TOKEN": "{env:SHOULD_NOT_EXPAND}"},
            ),
            source_path=source_path,
            project_root=tmp_path,
            output_dir=tmp_path / "out" / "checks",
            config=config,
        )

    assert captured["env"]["TOKEN"] == "{env:SHOULD_NOT_EXPAND}"
    assert caplog.records == []


def test_task_based_runner_eval_banana_vars_not_overridable_by_check_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={"codex": HarnessConfig(command=["codex", "exec"])},
    )
    output_dir = tmp_path / "out" / "checks"
    check = _make_task_check(
        check_id="env_guard",
        harness="codex",
        command=["prompt"],
        env={
            "EVAL_BANANA_PROJECT_ROOT": "hack",
            "EVAL_BANANA_OUTPUT_DIR": "fake-output",
            "EVAL_BANANA_CHECK_ID": "fake-id",
        },
    )

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=output_dir,
        config=config,
    )

    assert captured["env"]["EVAL_BANANA_PROJECT_ROOT"] == str(tmp_path)
    assert captured["env"]["EVAL_BANANA_OUTPUT_DIR"] == str(output_dir / check.id)
    assert captured["env"]["EVAL_BANANA_CHECK_ID"] == check.id


def test_task_based_runner_returns_error_for_unknown_harness(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    check = _make_task_check(harness="missing_harness", command=["prompt"])

    result = run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"
    assert (
        result.error_detail
        == "Unknown harness 'missing_harness'. Define it in [harnesses.missing_harness] in your config.toml."
    )


def test_working_directory_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    workdir = tmp_path / "subdir"
    workdir.mkdir()
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    check = _make_task_check(working_directory="subdir")

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert captured["cwd"] == workdir.resolve()


def test_task_based_runner_honors_working_directory_with_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = _make_source_path(tmp_path=tmp_path)
    workdir = tmp_path / "subdir"
    workdir.mkdir()
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    config = make_config(
        project_root=tmp_path,
        harnesses={"codex": HarnessConfig(command=["codex", "exec"])},
    )

    run_task_based_check(
        check=_make_task_check(
            harness="codex", command=["prompt"], working_directory="subdir"
        ),
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=config,
    )

    assert captured["cwd"] == workdir.resolve()
