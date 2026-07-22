from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

from eval_banana.cli import _classify_run_failure
from eval_banana.cli import main
from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import EvalReport
from eval_banana.result_output import observe_dirty_tree
from eval_banana.result_output import ResultStatus


def _passing_report(*, checks: list[CheckResult]) -> EvalReport:
    return EvalReport(
        run_id="run1",
        project_root="/tmp/project",
        output_dir="/tmp/project/out",
        started_at="2026-07-22T12:00:00+00:00",
        completed_at="2026-07-22T12:00:01+00:00",
        duration_ms=1000,
        total_checks=len(checks),
        passed_checks=len(checks),
        failed_checks=0,
        errored_checks=0,
        points_earned=len(checks),
        total_points=len(checks),
        percentage=100.0,
        pass_threshold=1.0,
        meets_threshold=True,
        run_passed=True,
        checks=checks,
    )


def _init_git_repo(*, path: Path) -> str:
    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=path, capture_output=True, text=True, check=True
        )

    _git("init", "-q")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    _git("config", "commit.gpgsign", "false")
    (path / "tracked.txt").write_text("hello\n", encoding="utf-8")
    _git("add", ".")
    _git("commit", "-q", "-m", "init")
    return _git("rev-parse", "HEAD").stdout.strip()


def _fenced_json(*, text: str) -> dict[str, object]:
    lines = text.splitlines()
    start = lines.index("```eval-banana-result v1")
    end = lines.index("```", start + 1)
    return json.loads("\n".join(lines[start + 1 : end]))


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
        lambda config, check_dir, check_id, tags, flat_output: EvalReport(
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
            "gpt-5.6-sol",
            "--harness-reasoning-effort",
            "high",
            "--harness-timeout-seconds",
            "10800",
            "--max-parallel-checks",
            "6",
            "--no-project-config",
            "--cwd",
            "/tmp/project",
        ],
    )

    assert result.exit_code == 0
    assert captured["output_dir"] == "out"
    assert captured["harness_agent"] == "codex"
    assert captured["harness_model"] == "gpt-5.6-sol"
    assert captured["harness_reasoning_effort"] == "high"
    assert captured["harness_timeout_seconds"] == 10800
    assert captured["max_parallel_checks"] == 6
    assert captured["use_project_config"] is False
    assert captured["cwd"] == "/tmp/project"


def test_run_rejects_non_positive_harness_timeout() -> None:
    """Validate the CLI timeout before loading config or launching an agent."""

    result = CliRunner().invoke(main, ["run", "--harness-timeout-seconds", "0"])

    assert result.exit_code == 2
    assert "not in the range x>=1" in result.output


def test_run_rejects_non_positive_max_parallel_checks() -> None:
    """Validate the CLI concurrency cap before loading config."""

    result = CliRunner().invoke(main, ["run", "--max-parallel-checks", "0"])

    assert result.exit_code == 2
    assert "not in the range x>=1" in result.output


def test_run_exit_code_one(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())
    monkeypatch.setattr(
        "eval_banana.cli.run_checks",
        lambda config, check_dir, check_id, tags, flat_output: EvalReport(
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
        flat_output: bool,
    ) -> EvalReport:
        captured["config"] = config
        captured["check_dir"] = check_dir
        captured["check_id"] = check_id
        captured["tags"] = tags
        captured["flat_output"] = flat_output
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
    assert captured["flat_output"] is False


def test_run_flat_output_requires_explicit_output_dir() -> None:
    result = CliRunner().invoke(main, ["run", "--flat-output"])

    assert result.exit_code == 2
    assert "--flat-output requires an explicit --output-dir" in result.output


def test_run_passes_flat_output_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())

    def fake_run_checks(**kwargs: object) -> EvalReport:
        captured.update(kwargs)
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

    result = runner.invoke(
        main, ["run", "--flat-output", "--output-dir", "/tmp/attempt-eval"]
    )

    assert result.exit_code == 0
    assert captured["flat_output"] is True


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


def test_validate_accepts_explicit_harness_agent_without_project_config(
    tmp_path: Path,
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
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        [
            "validate",
            "--cwd",
            str(tmp_path),
            "--check-dir",
            str(checks_dir),
            "--harness-agent",
            "codex",
            "--no-project-config",
        ],
    )

    assert result.exit_code == 0
    assert "Validated 1 checks successfully." in result.output


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


def test_run_without_result_out_writes_no_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent --result-out is pure backward-compat: no document is written."""

    runner = CliRunner()
    monkeypatch.setattr("eval_banana.cli.load_config", lambda **kwargs: object())
    monkeypatch.setattr(
        "eval_banana.cli.run_checks", lambda **kwargs: _passing_report(checks=[])
    )
    write_calls: list[object] = []
    monkeypatch.setattr(
        "eval_banana.cli.write_result_document",
        lambda **kwargs: write_calls.append(kwargs),
    )

    result = runner.invoke(main, ["run"])

    assert result.exit_code == 0
    assert write_calls == []


def test_run_result_out_completed_writes_stamped_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    commit = _init_git_repo(path=tmp_path)
    check = CheckResult(
        check_id="goal_outcome",
        check_type=CheckType.harness_judge,
        check_definition_sha256="sha256:" + "0" * 64,
        description="desc",
        source_path=str(tmp_path / "check.yaml"),
        status=CheckStatus.passed,
        score=1,
        started_at="2026-07-22T12:00:00+00:00",
        completed_at="2026-07-22T12:00:01+00:00",
        duration_ms=1000,
        reason="looks good",
        details={"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
    )
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(
            project_root=tmp_path, cwd=str(tmp_path), harness_agent="codex"
        ),
    )
    monkeypatch.setattr(
        "eval_banana.cli.run_checks", lambda **kwargs: _passing_report(checks=[check])
    )
    result_out = tmp_path / "out" / "eval_results.md"

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--result-out",
            str(result_out),
            "--provenance-attempt",
            "attempt-7",
            "--provenance-field",
            "session=s1",
            "--cwd",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert result_out.is_file()
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["run_passed"] is True
    assert payload["harness"] == {"family": "codex", "effort": "xhigh"}
    assert payload["provenance"] == {"attempt": "attempt-7", "session": "s1"}
    assert payload["observed"]["commit_before"] == commit
    assert payload["observed"]["commit_after"] == commit
    assert payload["observed"]["dirty_tree_digest"] is not None
    assert payload["observed"]["dirty_tree_algorithm"] == "eb-git-status-v2-sha256"
    assert payload["checks"] == [
        {
            "id": "goal_outcome",
            "status": "passed",
            "reason": "looks good",
            "model": "gpt-5.6-sol",
        }
    ]


def test_run_result_out_json_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )
    monkeypatch.setattr(
        "eval_banana.cli.run_checks", lambda **kwargs: _passing_report(checks=[])
    )
    result_out = tmp_path / "result.json"

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--result-out",
            str(result_out),
            "--result-format",
            "json",
            "--cwd",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["schema_version"] == 1


def test_run_result_out_no_checks_status(tmp_path: Path) -> None:
    """A real no-checks run still writes a stamped document (non-git => nulls)."""

    result_out = tmp_path / "result.md"

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--result-out",
            str(result_out),
            "--no-project-config",
            "--cwd",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert result_out.is_file()
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "no_checks"
    assert payload["run_passed"] is False
    assert payload["checks"] == []
    assert "No checks found" in str(payload["error"])
    assert payload["observed"]["commit_before"] is None
    assert payload["observed"]["dirty_tree_digest"] is None
    assert payload["observed"]["dirty_tree_algorithm"] is None


def test_run_result_out_harness_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )

    def raise_harness(**kwargs: object) -> EvalReport:
        raise SystemExit(
            "harness_judge check requires a harness but none is configured"
        )

    monkeypatch.setattr("eval_banana.cli.run_checks", raise_harness)
    result_out = tmp_path / "result.md"

    result = CliRunner().invoke(
        main, ["run", "--result-out", str(result_out), "--cwd", str(tmp_path)]
    )

    assert result.exit_code == 1
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "harness_error"
    assert payload["run_passed"] is False
    assert "requires a harness" in str(payload["error"])


def test_run_result_out_config_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )

    def raise_config(**kwargs: object) -> EvalReport:
        raise SystemExit("Config.project_root must be set")

    monkeypatch.setattr("eval_banana.cli.run_checks", raise_config)
    result_out = tmp_path / "result.md"

    result = CliRunner().invoke(
        main, ["run", "--result-out", str(result_out), "--cwd", str(tmp_path)]
    )

    assert result.exit_code == 1
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "config_error"
    assert payload["run_passed"] is False


def test_run_result_out_refuses_symlink_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )
    monkeypatch.setattr(
        "eval_banana.cli.run_checks", lambda **kwargs: _passing_report(checks=[])
    )
    real_file = tmp_path / "real.md"
    real_file.write_text("original\n", encoding="utf-8")
    link = tmp_path / "eval_results.md"
    link.symlink_to(real_file)

    result = CliRunner().invoke(
        main, ["run", "--result-out", str(link), "--cwd", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "symlink" in result.output
    assert real_file.read_text(encoding="utf-8") == "original\n"


def test_run_result_out_rejects_malformed_provenance_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )
    monkeypatch.setattr(
        "eval_banana.cli.run_checks", lambda **kwargs: _passing_report(checks=[])
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--result-out",
            str(tmp_path / "result.md"),
            "--provenance-field",
            "novalue",
            "--cwd",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "--provenance-field must be key=value" in result.output


def test_run_result_out_stamps_config_load_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A load_config failure with --result-out still writes config_error."""

    def raise_load(**kwargs: object) -> Config:
        raise SystemExit("Invalid TOML in .eval-banana/config.toml: bad")

    monkeypatch.setattr("eval_banana.cli.load_config", raise_load)
    result_out = tmp_path / "result.md"

    result = CliRunner().invoke(
        main, ["run", "--result-out", str(result_out), "--cwd", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert result_out.is_file()
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "config_error"
    assert payload["run_passed"] is False
    assert payload["checks"] == []
    assert "Invalid TOML" in str(payload["error"])


def test_run_result_out_dirty_digest_observed_at_run_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """A mid-run tree change must not alter the recorded dirty digest."""

    _init_git_repo(path=tmp_path)
    clean_digest = observe_dirty_tree(cwd=str(tmp_path)).digest
    monkeypatch.setattr(
        "eval_banana.cli.load_config",
        lambda **kwargs: make_config(project_root=tmp_path, cwd=str(tmp_path)),
    )

    def dirty_run(**kwargs: object) -> EvalReport:
        (tmp_path / "tracked.txt").write_text("mutated by run\n", encoding="utf-8")
        return _passing_report(checks=[])

    monkeypatch.setattr("eval_banana.cli.run_checks", dirty_run)
    result_out = tmp_path / "out" / "result.md"

    result = CliRunner().invoke(
        main, ["run", "--result-out", str(result_out), "--cwd", str(tmp_path)]
    )

    assert result.exit_code == 0
    payload = _fenced_json(text=result_out.read_text(encoding="utf-8"))
    # The run dirtied the tree, so a post-run observation differs; the recorded
    # digest matches the pre-run (clean) state, proving run-start observation.
    post_run_digest = observe_dirty_tree(cwd=str(tmp_path)).digest
    assert post_run_digest != clean_digest
    assert payload["observed"]["dirty_tree_digest"] == clean_digest


def test_classify_run_failure_keys_on_known_messages() -> None:
    assert _classify_run_failure(message="No checks found") == ResultStatus.no_checks
    # A bad --check-id is a usage/config error, not an empty selection.
    assert (
        _classify_run_failure(message="No check found with id 'x'")
        == ResultStatus.config_error
    )
    assert (
        _classify_run_failure(
            message="harness_judge check requires a harness but none is configured"
        )
        == ResultStatus.harness_error
    )
    assert (
        _classify_run_failure(message="Config.project_root must be set")
        == ResultStatus.config_error
    )
    assert (
        _classify_run_failure(message="Duplicate check id 'x' found in a and b")
        == ResultStatus.config_error
    )
