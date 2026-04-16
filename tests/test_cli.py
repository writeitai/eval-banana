from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner
import pytest

from eval_banana.cli import _BUNDLED_SKILL_CHOICES
from eval_banana.cli import main
from eval_banana.config import Config
from eval_banana.harness.skills import AGENT_SKILL_TARGETS
from eval_banana.harness.skills import InstallReport
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


def test_install_default_agents_and_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )

    def fake_install_bundled_skills(**kwargs: object) -> InstallReport:
        captured.update(kwargs)
        return InstallReport(installed=["one"], skipped=[], failed=[])

    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills", fake_install_bundled_skills
    )

    result = runner.invoke(main, ["install"])

    assert result.exit_code == 0
    assert captured["project_root"] == tmp_path
    assert captured["agent_types"] == sorted(AGENT_SKILL_TARGETS)
    assert captured["skill_names"] == _BUNDLED_SKILL_CHOICES
    assert captured["force"] is False
    assert captured["dry_run"] is False
    assert "Summary: installed=1 skipped=0 failed=0" in result.output


def test_install_target_agents_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )

    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills",
        lambda **kwargs: captured.update(kwargs) or InstallReport(),
    )

    result = runner.invoke(main, ["install", "--target-agents", "codex"])

    assert result.exit_code == 0
    assert captured["agent_types"] == ["codex"]


def test_install_skills_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills",
        lambda **kwargs: captured.update(kwargs) or InstallReport(),
    )

    result = runner.invoke(main, ["install", "--skills", "gemini_media_use"])

    assert result.exit_code == 0
    assert captured["skill_names"] == ["gemini_media_use"]


def test_install_dry_run_is_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills",
        lambda **kwargs: captured.update(kwargs) or InstallReport(skipped=["one"]),
    )

    result = runner.invoke(main, ["install", "--dry-run"])

    assert result.exit_code == 0
    assert captured["dry_run"] is True
    assert "Summary: installed=0 skipped=1 failed=0" in result.output


def test_install_force_is_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills",
        lambda **kwargs: captured.update(kwargs) or InstallReport(installed=["one"]),
    )

    result = runner.invoke(main, ["install", "--force"])

    assert result.exit_code == 0
    assert captured["force"] is True


def test_distribute_skills_alias_emits_warning_and_delegates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.install_bundled_skills",
        lambda **kwargs: captured.update(kwargs) or InstallReport(installed=["one"]),
    )

    result = runner.invoke(main, ["distribute-skills", "--target-agents", "codex"])

    assert result.exit_code == 0
    assert captured["agent_types"] == ["codex"]
    assert (
        "DeprecationWarning: 'distribute-skills' is deprecated; use 'eb install'"
        in result.output
    )


def test_install_help_includes_command_and_option_descriptions() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["install", "--help"])
    normalized_output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert (
        "Install bundled eval-banana agent skills into a project's native agent "
        "skill directories."
    ) in normalized_output
    assert "Repeatable. Limit installation to specific agent targets." in normalized_output
    assert (
        "Repeatable. Limit installation to specific bundled skills." in normalized_output
    )
    assert "Target project directory." in normalized_output
    assert "Print the planned installs without writing files." in normalized_output
    assert (
        "Overwrite existing unmarked target directories. Does not replace files or symlinks."
        in normalized_output
    )
    assert "Enable debug logging." in normalized_output


def test_distribute_skills_help_includes_deprecated_alias_text() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["distribute-skills", "--help"])

    assert result.exit_code == 0
    assert "Deprecated alias for 'install'." in result.output


def test_install_failures_are_reported_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("bad config")),
    )

    result = runner.invoke(main, ["install"])

    assert result.exit_code == 1
    assert "bad config" in result.stderr


def test_install_invalid_target_agent(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["install", "--target-agents", "invalid-agent"])

    assert result.exit_code == 2
    assert "Invalid value for '--target-agents'" in result.output
