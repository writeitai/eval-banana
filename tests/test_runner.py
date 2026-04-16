from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from eval_banana.config import Config
from eval_banana.harness.template import AgentTemplate
from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus
from eval_banana.runner import run_checks


def test_full_orchestration_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)
    monkeypatch.setattr("eval_banana.runner.resolve_template", lambda **kwargs: None)
    monkeypatch.setattr("eval_banana.runner.run_harness", lambda **kwargs: None)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.total_checks == 1
    assert (Path(report.output_dir) / "report.json").is_file()


def test_no_checks_found(tmp_path: Path, make_config: Callable[..., Config]) -> None:
    with pytest.raises(SystemExit, match="No checks found"):
        run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))


def test_check_id_filtering_with_relaxed_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    good = checks_dir / "good.yaml"
    bad = checks_dir / "bad.yaml"
    good.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: good",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    bad.write_text(":\n-", encoding="utf-8")
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="good",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(good),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)
    monkeypatch.setattr("eval_banana.runner.resolve_template", lambda **kwargs: None)
    monkeypatch.setattr("eval_banana.runner.run_harness", lambda **kwargs: None)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="good"
    )

    assert report.total_checks == 1
    assert report.checks[0].check_id == "good"


def test_check_id_succeeds_with_broken_yaml_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "target.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: target",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "broken.yaml").write_text("not: [valid", encoding="utf-8")
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="target",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(checks_dir / "target.yaml"),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)
    monkeypatch.setattr("eval_banana.runner.resolve_template", lambda **kwargs: None)
    monkeypatch.setattr("eval_banana.runner.run_harness", lambda **kwargs: None)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="target"
    )

    assert report.run_passed is True


def test_check_id_detects_duplicates(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for name in ("a.yaml", "b.yaml"):
        (checks_dir / name).write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    "id: dup",
                    "type: deterministic",
                    "description: desc",
                    "script: print('ok')",
                ]
            ),
            encoding="utf-8",
        )

    with pytest.raises(SystemExit, match="Duplicate check id"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="dup"
        )


def test_tag_filter_runs_only_matching_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    alpha = checks_dir / "alpha.yaml"
    beta = checks_dir / "beta.yaml"
    alpha.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: alpha",
                "type: deterministic",
                "description: alpha",
                "tags: [migration, smoke]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    beta.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: beta",
                "type: deterministic",
                "description: beta",
                "tags: [docs]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        check = cast(CheckDefinition, kwargs["check"])
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            description=check.description,
            source_path=str(kwargs["source_path"]),
            tags=list(check.tags),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)
    monkeypatch.setattr("eval_banana.runner.resolve_template", lambda **kwargs: None)
    monkeypatch.setattr("eval_banana.runner.run_harness", lambda **kwargs: None)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), tags=["migration"]
    )

    assert report.total_checks == 1
    assert [check.check_id for check in report.checks] == ["alpha"]
    assert report.checks[0].tags == ["migration", "smoke"]


def test_tag_filter_with_no_matches_fails(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "tags: [migration]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="No checks found"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)),
            tags=["nonexistent"],
        )


def test_no_tag_filter_runs_all_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for check_id, tag in (("alpha", "migration"), ("beta", "docs")):
        (checks_dir / f"{check_id}.yaml").write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    f"id: {check_id}",
                    "type: deterministic",
                    f"description: {check_id}",
                    f"tags: [{tag}]",
                    "script: print('ok')",
                ]
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        check = cast(CheckDefinition, kwargs["check"])
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            description=check.description,
            source_path=str(kwargs["source_path"]),
            tags=list(check.tags),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)
    monkeypatch.setattr("eval_banana.runner.resolve_template", lambda **kwargs: None)
    monkeypatch.setattr("eval_banana.runner.run_harness", lambda **kwargs: None)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.total_checks == 2
    assert [check.check_id for check in report.checks] == ["alpha", "beta"]


def test_harness_prompt_file_is_resolved_and_forwarded_to_run_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompts" / "task.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Review the project", encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr("eval_banana.runner.write_report_files", lambda **kwargs: None)

    def fake_resolve_template(**kwargs: object) -> AgentTemplate:
        captured["resolved_agent_type"] = kwargs["agent_type"]
        return AgentTemplate(
            command=("codex", "exec"),
            default_model="built-in-model",
            reasoning_effort="medium",
        )

    def fake_run_harness(**kwargs: object) -> HarnessResult:
        captured["harness_kwargs"] = kwargs
        template = kwargs["template"]
        assert isinstance(template, AgentTemplate)
        return make_harness_result(
            status="succeeded",
            prompt_source=kwargs["prompt_source"],
            prompt_file=kwargs["prompt_file"],
            model=kwargs["model"],
            reasoning_effort=template.reasoning_effort,
        )

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner.resolve_template", fake_resolve_template)
    monkeypatch.setattr("eval_banana.runner.run_harness", fake_run_harness)
    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            harness_agent="codex",
            harness_prompt_file="prompts/task.md",
            harness_model="gpt-5.4",
            harness_reasoning_effort="high",
            harness_env={"CI": "1"},
        )
    )

    harness_kwargs = captured["harness_kwargs"]
    assert report.harness is not None
    assert captured["resolved_agent_type"] == "codex"
    assert harness_kwargs["prompt"] == "Review the project"
    assert harness_kwargs["prompt_source"] == "file"
    assert harness_kwargs["prompt_file"] == str(prompt_path.resolve())
    assert harness_kwargs["model"] == "gpt-5.4"
    assert harness_kwargs["harness_env"] == {"CI": "1"}
    assert harness_kwargs["template"].command == ("codex", "exec")
    assert harness_kwargs["template"].reasoning_effort == "high"
    assert report.harness.prompt_source == "file"
    assert report.harness.prompt_file == str(prompt_path.resolve())
    assert report.harness.reasoning_effort == "high"


def test_run_checks_no_longer_passes_skills_dir_to_run_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr("eval_banana.runner.write_report_files", lambda **kwargs: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template",
        lambda **kwargs: AgentTemplate(command=("codex", "exec")),
    )

    def fake_run_harness(**kwargs: object) -> HarnessResult:
        captured.update(kwargs)
        return make_harness_result(status="succeeded")

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner.run_harness", fake_run_harness)
    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    config = make_config(
        project_root=tmp_path,
        cwd=str(tmp_path),
        harness_agent="codex",
        harness_prompt="Fix it",
    )
    run_checks(config=config)

    assert "skills_dir" not in captured


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"harness_agent": "codex"}, "Harness requires either prompt or prompt_file"),
        (
            {
                "harness_agent": "codex",
                "harness_prompt": "Fix it",
                "harness_prompt_file": "prompts/task.md",
            },
            "Harness prompt and prompt_file are mutually exclusive",
        ),
    ],
)
def test_invalid_harness_prompt_configuration_aborts_before_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    overrides: dict[str, object],
    message: str,
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )
    monkeypatch.setattr(
        "eval_banana.runner.run_harness",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not run harness")),
    )

    with pytest.raises(SystemExit, match=message):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path), **overrides)
        )


def test_missing_harness_prompt_file_aborts_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )
    monkeypatch.setattr(
        "eval_banana.runner.run_harness",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not run harness")),
    )

    with pytest.raises(SystemExit, match="Harness prompt file not found:"):
        run_checks(
            config=make_config(
                project_root=tmp_path,
                cwd=str(tmp_path),
                harness_agent="codex",
                harness_prompt_file="prompts/missing.md",
            )
        )


def test_harness_runs_before_first_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    events: list[str] = []
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr("eval_banana.runner.write_report_files", lambda **kwargs: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template", lambda **kwargs: object()
    )

    def fake_run_harness(**kwargs: object):
        events.append("harness")
        return make_harness_result(status="succeeded")

    def fake_runner(**kwargs: object) -> CheckResult:
        events.append("check")
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner.run_harness", fake_run_harness)
    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            harness_agent="codex",
            harness_prompt="Fix it",
        )
    )

    assert report.harness is not None
    assert events == ["harness", "check"]


def test_failed_harness_aborts_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        "eval_banana.runner.run_harness",
        lambda **kwargs: make_harness_result(status="failed", exit_code=2),
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner",
        lambda check: (_ for _ in ()).throw(AssertionError("checks should not run")),
    )

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            harness_agent="codex",
            harness_prompt="Fix it",
        )
    )

    assert report.harness is not None
    assert report.harness.status == HarnessStatus.failed
    assert report.checks == []


def test_skipped_harness_still_runs_checks_and_does_not_resolve_or_spawn_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )
    monkeypatch.setattr(
        "eval_banana.runner.run_harness",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            harness_agent="missing-binary",
            skip_harness=True,
        )
    )

    assert report.harness is not None
    assert report.harness.status == HarnessStatus.skipped
    assert report.total_checks == 1


def test_no_harness_run_does_not_touch_agent_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )
    monkeypatch.setattr(
        "eval_banana.runner.run_harness",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.run_passed is True


def test_check_id_targeted_runs_still_perform_harness_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Config],
    make_harness_result: Callable[..., HarnessResult],
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    target = checks_dir / "target.yaml"
    target.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: target",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    events: list[str] = []
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.resolve_template", lambda **kwargs: object()
    )

    def fake_harness(**kwargs: object):
        events.append("harness")
        return make_harness_result(status="succeeded")

    def fake_runner(**kwargs: object) -> CheckResult:
        events.append("check")
        return CheckResult(
            check_id="target",
            check_type=CheckType.deterministic,
            description="desc",
            source_path=str(target),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner.run_harness", fake_harness)
    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            harness_agent="codex",
            harness_prompt="Fix it",
        ),
        check_id="target",
    )

    assert report.run_passed is True
    assert events == ["harness", "check"]
