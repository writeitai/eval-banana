from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner
import pytest

from eval_banana.cli import main
from eval_banana.config import Config
from eval_banana.models import EvalReport


def test_init_writes_config_and_example_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    assert (tmp_path / ".eval-banana" / "config.toml").is_file()
    assert (tmp_path / "eval_checks" / "example_check.yaml").is_file()


def test_run_exit_code_zero_and_prompt_overrides_reach_load_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured = {}

    def fake_load_config(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("eval_banana.cli.load_config", fake_load_config)
    monkeypatch.setattr(
        "eval_banana.cli.run_checks",
        lambda config, check_dir, check_id: EvalReport(
            run_id="run1",
            project_root="/tmp",
            output_dir="/tmp/out",
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
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
            checks=[],
        ),
    )

    result = runner.invoke(
        main,
        [
            "run",
            "--output-dir",
            "out",
            "--provider",
            "codex",
            "--model",
            "m",
            "--api-base",
            "https://example.com",
            "--api-key",
            "k",
            "--codex-auth-path",
            "/tmp/auth.json",
            "--pass-threshold",
            "0.5",
            "--harness-agent",
            "codex",
            "--harness-prompt",
            "Fix it",
            "--harness-model",
            "gpt-5.4",
            "--harness-reasoning-effort",
            "high",
            "--skip-harness",
            "--cwd",
            "/tmp/project",
        ],
    )

    assert result.exit_code == 0
    assert captured["output_dir"] == "out"
    assert captured["provider"] == "codex"
    assert captured["harness_agent"] == "codex"
    assert captured["harness_prompt"] == "Fix it"
    assert captured["harness_prompt_file"] is None
    assert captured["harness_model"] == "gpt-5.4"
    assert captured["harness_reasoning_effort"] == "high"
    assert captured["skip_harness"] is True
    assert captured["cwd"] == "/tmp/project"


def test_run_forwards_harness_prompt_file_as_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    captured = {}

    def fake_load_config(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("eval_banana.cli.load_config", fake_load_config)
    monkeypatch.setattr(
        "eval_banana.cli.run_checks",
        lambda config, check_dir, check_id: EvalReport(
            run_id="run1",
            project_root="/tmp",
            output_dir="/tmp/out",
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
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
            checks=[],
        ),
    )

    result = runner.invoke(
        main,
        ["run", "--harness-agent", "codex", "--harness-prompt-file", "prompts/task.md"],
    )

    assert result.exit_code == 0
    assert captured["harness_prompt"] is None
    assert captured["harness_prompt_file"] == "prompts/task.md"
    assert captured["skip_harness"] is None


def test_run_exit_code_one(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())
    monkeypatch.setattr(
        "eval_banana.cli.run_checks",
        lambda config, check_dir, check_id: EvalReport(
            run_id="run1",
            project_root="/tmp",
            output_dir="/tmp/out",
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
            total_checks=1,
            passed_checks=0,
            failed_checks=1,
            errored_checks=0,
            points_earned=0,
            total_points=1,
            percentage=0.0,
            pass_threshold=1.0,
            meets_threshold=False,
            run_passed=False,
            checks=[],
        ),
    )

    result = runner.invoke(main, ["run"])

    assert result.exit_code == 1


def test_list_prints_discovered_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.discover_check_files",
        lambda **kwargs: [tmp_path / "eval_checks" / "one.yaml"],
    )

    class DummyCheck:
        id = "one"
        type = "deterministic"
        description = "desc"

    monkeypatch.setattr(
        "eval_banana.cli.load_check_definitions",
        lambda paths: [(tmp_path / "eval_checks" / "one.yaml", DummyCheck())],
    )

    result = runner.invoke(main, ["list"])

    assert result.exit_code == 0
    assert "one" in result.output


def test_validate_exit_code_zero_and_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.discover_check_files",
        lambda **kwargs: [tmp_path / "eval_checks" / "one.yaml"],
    )
    monkeypatch.setattr("eval_banana.cli.load_check_definitions", lambda paths: [])

    success = runner.invoke(main, ["validate"])
    assert success.exit_code == 0

    monkeypatch.setattr(
        "eval_banana.cli.load_check_definitions",
        lambda paths: (_ for _ in ()).throw(ValueError("bad yaml")),
    )
    failure = runner.invoke(main, ["validate"])
    assert failure.exit_code == 1


def test_distribute_skills_default_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    skills_dir = tmp_path / "skills"
    (skills_dir / "gemini_media_use").mkdir(parents=True)
    captured: list[str] = []
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(
            project_root=tmp_path, skills_dir=str(skills_dir.resolve())
        ),
    )

    def fake_distribute_skills(**kwargs: object) -> list[str]:
        agent_type = kwargs["agent_type"]
        assert isinstance(agent_type, str)
        captured.append(agent_type)
        return ["gemini_media_use"]

    monkeypatch.setattr("eval_banana.cli.distribute_skills", fake_distribute_skills)

    result = runner.invoke(main, ["distribute-skills"])

    assert result.exit_code == 0
    assert captured == ["claude", "codex"]
    assert "claude: distributed 1 skill" in result.output
    assert "codex: distributed 1 skill" in result.output


def test_distribute_skills_target_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    skills_dir = tmp_path / "skills"
    (skills_dir / "gemini_media_use").mkdir(parents=True)
    captured: list[str] = []
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(
            project_root=tmp_path, skills_dir=str(skills_dir.resolve())
        ),
    )
    monkeypatch.setattr(
        "eval_banana.cli.distribute_skills",
        lambda **kwargs: (
            captured.append(str(kwargs["agent_type"])) or ["gemini_media_use"]
        ),
    )

    result = runner.invoke(main, ["distribute-skills", "--target-agents", "codex"])

    assert result.exit_code == 0
    assert captured == ["codex"]
    assert "codex: distributed 1 skill" in result.output


def test_distribute_skills_missing_skills_dir_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(
            project_root=tmp_path,
            skills_dir=str((tmp_path / "missing-skills").resolve()),
        ),
    )

    result = runner.invoke(main, ["distribute-skills"])

    assert result.exit_code == 0
    assert "No skills directory found at" in result.output


def test_distribute_skills_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    skills_dir = tmp_path / "skills"
    (skills_dir / "gemini_media_use").mkdir(parents=True)
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(
            project_root=tmp_path, skills_dir=str(skills_dir.resolve())
        ),
    )
    monkeypatch.setattr(
        "eval_banana.cli.distribute_skills",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("distribute_skills must not be called during dry-run")
        ),
    )

    result = runner.invoke(main, ["distribute-skills", "--dry-run"])

    assert result.exit_code == 0
    assert "claude: would distribute 1 skill" in result.output
    assert "codex: would distribute 1 skill" in result.output


def test_distribute_skills_invalid_target_agent(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main, ["distribute-skills", "--target-agents", "invalid-agent"]
    )

    assert result.exit_code == 2
    assert "Invalid value for '--target-agents'" in result.output
