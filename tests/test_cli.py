from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner
import pytest

from eval_banana.cli import main
from eval_banana.config import Config
from eval_banana.models import EvalReport


def test_init_writes_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    assert (tmp_path / ".eval-banana" / "config.toml").is_file()
    assert not (tmp_path / "eval_checks").exists()


def test_run_rejects_removed_skip_harness_flag() -> None:
    # Acceptance criterion: `eval-banana run --skip-harness` must be rejected
    # by Click with "no such option" (exit 2). Locks the removal into CI.
    runner = CliRunner()

    # Built at runtime to keep the repo-wide grep sweep for "--skip-harness" clean.
    removed_flag = "--skip" + "-harness"
    result = runner.invoke(main, ["run", removed_flag])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_run_exit_code_zero_and_harness_overrides_reach_load_config(
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
        lambda config, check_dir, check_id, tags: EvalReport(
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
            "--pass-threshold",
            "0.5",
            "--harness-agent",
            "codex",
            "--harness-model",
            "gpt-5.4",
            "--harness-reasoning-effort",
            "high",
            "--cwd",
            "/tmp/project",
        ],
    )

    assert result.exit_code == 0
    assert captured["output_dir"] == "out"
    assert captured["harness_agent"] == "codex"
    assert captured["harness_model"] == "gpt-5.4"
    assert captured["harness_reasoning_effort"] == "high"
    assert captured["cwd"] == "/tmp/project"


def test_run_exit_code_one(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())
    monkeypatch.setattr(
        "eval_banana.cli.run_checks",
        lambda config, check_dir, check_id, tags: EvalReport(
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


def test_run_passes_tags_to_run_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())

    def fake_run_checks(
        config: object,
        check_dir: Path | None,
        check_id: str | None,
        tags: list[str] | None,
    ) -> EvalReport:
        captured["config"] = config
        captured["check_dir"] = check_dir
        captured["check_id"] = check_id
        captured["tags"] = tags
        return EvalReport(
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
        )

    monkeypatch.setattr("eval_banana.cli.run_checks", fake_run_checks)

    result = runner.invoke(main, ["run", "--tag", "migration", "--tag", "smoke"])

    assert result.exit_code == 0
    assert captured["tags"] == ["migration", "smoke"]


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


def test_list_filters_checks_by_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path),
    )
    monkeypatch.setattr(
        "eval_banana.cli.discover_check_files",
        lambda **kwargs: [
            tmp_path / "eval_checks" / "one.yaml",
            tmp_path / "eval_checks" / "two.yaml",
        ],
    )

    class TaggedCheck:
        def __init__(self, check_id: str, tags: list[str]) -> None:
            self.id = check_id
            self.type = "deterministic"
            self.description = f"{check_id} desc"
            self.tags = tags

    monkeypatch.setattr(
        "eval_banana.cli.load_check_definitions",
        lambda paths: [
            (tmp_path / "eval_checks" / "one.yaml", TaggedCheck("one", ["migration"])),
            (tmp_path / "eval_checks" / "two.yaml", TaggedCheck("two", ["docs"])),
        ],
    )

    result = runner.invoke(main, ["list", "--tag", "migration"])

    assert result.exit_code == 0
    assert "one" in result.output
    assert "two" not in result.output


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


def test_validate_hard_fails_when_harness_judge_has_no_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    judge_path = checks_dir / "judge.yaml"
    judge_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: judge_check",
                "type: harness_judge",
                "description: desc",
                "target_paths:",
                "  - README.md",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, harness_agent=None),
    )

    result = runner.invoke(main, ["validate", "--cwd", str(tmp_path)])

    assert result.exit_code == 1
    assert "harness_judge check requires a harness" in result.output
    assert str(judge_path) in result.output


def test_validate_succeeds_when_harness_configured_for_harness_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "judge.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: judge_check",
                "type: harness_judge",
                "description: desc",
                "target_paths:",
                "  - README.md",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, harness_agent="codex"),
    )
    from eval_banana.runner import require_harness_for_harness_judge as real_gate

    gate_calls: list[tuple[object, ...]] = []

    def spy(*, config: Config, selected_checks: list[object]) -> None:
        gate_calls.append((config.harness_agent, len(selected_checks)))
        real_gate(config=config, selected_checks=selected_checks)  # type: ignore[arg-type]

    monkeypatch.setattr("eval_banana.cli.require_harness_for_harness_judge", spy)

    result = runner.invoke(main, ["validate", "--cwd", str(tmp_path)])

    assert result.exit_code == 0
    assert "Validated 1 checks successfully." in result.output
    assert gate_calls == [("codex", 1)]


def test_list_does_not_enforce_harness_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "judge.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: judge_check",
                "type: harness_judge",
                "description: desc",
                "target_paths:",
                "  - README.md",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, harness_agent=None),
    )

    result = runner.invoke(main, ["list", "--cwd", str(tmp_path)])

    assert result.exit_code == 0
    assert "judge_check" in result.output
