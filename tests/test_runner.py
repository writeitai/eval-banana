from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
from typing import cast

import pytest

from eval_banana.config import Config
from eval_banana.config import load_config
from eval_banana.loader import load_check_definition
from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.runner import _snapshot_check_definition
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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
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

    assert report.total_checks == 1
    assert (Path(report.output_dir) / "report.json").is_file()
    assert report.checks[0].check_definition_sha256 == (
        "sha256:" + hashlib.sha256(check_path.read_bytes()).hexdigest()
    )


def test_flat_output_writes_directly_into_exact_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_bytes(
        b"schema_version: 1\r\nid: one\r\ntype: deterministic\r\n"
        b"description: desc\r\nscript: print('ok')\r\n"
    )
    output_dir = tmp_path / "attempt-eval"
    output_dir.mkdir()
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(
        config=make_config(project_root=tmp_path, output_dir=str(output_dir)),
        flat_output=True,
    )

    assert Path(report.output_dir) == output_dir.resolve()
    assert (output_dir / "report.json").is_file()
    assert not (output_dir / report.run_id).exists()
    assert report.checks[0].check_definition_sha256 == (
        "sha256:" + hashlib.sha256(check_path.read_bytes()).hexdigest()
    )


def test_flat_output_rejects_nonempty_directory_before_execution(
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
    output_dir = tmp_path / "attempt-eval"
    output_dir.mkdir()
    (output_dir / "foreign.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit, match="output directory is not empty"):
        run_checks(
            config=make_config(project_root=tmp_path, output_dir=str(output_dir)),
            flat_output=True,
        )

    assert (output_dir / "foreign.txt").read_text(encoding="utf-8") == "keep"


def test_flat_output_rejects_symlink_directory(
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
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    actual_output = tmp_path / "actual-output"
    actual_output.mkdir()
    output_link = tmp_path / "attempt-eval"
    output_link.symlink_to(actual_output, target_is_directory=True)

    with pytest.raises(SystemExit, match="exact output path is a symlink"):
        run_checks(
            config=make_config(project_root=tmp_path, output_dir=str(output_link)),
            flat_output=True,
        )


def test_flat_output_rejects_relative_output_dir_symlink(tmp_path: Path) -> None:
    """Reject a relative CLI output path whose exact target is a symlink."""
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
    actual_output = tmp_path / "actual-output"
    actual_output.mkdir()
    output_link = tmp_path / "attempt-eval"
    output_link.symlink_to(actual_output, target_is_directory=True)
    config = load_config(
        cwd=str(tmp_path), output_dir="attempt-eval", use_project_config=False
    )

    with pytest.raises(SystemExit, match="exact output path is a symlink"):
        run_checks(config=config, flat_output=True)


def test_definition_snapshot_rejects_semantic_change_after_discovery(
    tmp_path: Path,
) -> None:
    check_path = tmp_path / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: first",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    discovered_definition = load_check_definition(path=check_path)
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: changed",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="changed after discovery"):
        _snapshot_check_definition(
            source_path=check_path, expected_definition=discovered_definition
        )


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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(good),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(checks_dir / "target.yaml"),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
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

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.total_checks == 2
    assert [check.check_id for check in report.checks] == ["alpha", "beta"]


def test_harness_judge_without_harness_aborts_before_runner_is_invoked(
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
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    message = str(excinfo.value)
    assert "harness_judge check requires a harness" in message
    assert str(judge_path) in message
    assert "[harness] agent" in message
    assert "--harness-agent" in message


def test_harness_judge_with_harness_configured_proceeds(
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
    called = {"runner": False}
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.write_report_files", lambda report, output_dir: None
    )

    def fake_runner(**kwargs: object) -> CheckResult:
        called["runner"] = True
        return CheckResult(
            check_id="judge_check",
            check_type=CheckType.harness_judge,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(judge_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path, cwd=str(tmp_path), harness_agent="codex"
        )
    )

    assert called["runner"] is True
    assert report.run_passed is True


def test_deterministic_run_with_no_harness_agent_succeeds(
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
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
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


def test_check_id_targeting_deterministic_ignores_unrelated_harness_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    deterministic_path = checks_dir / "a.yaml"
    deterministic_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="a",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(deterministic_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="a"
    )

    assert report.run_passed is True
    assert report.checks[0].check_id == "a"


def test_check_id_targeting_harness_judge_without_harness_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "a.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit, match="harness_judge check requires a harness"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="b"
        )


def test_mixed_checks_without_harness_aborts_on_harness_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "a_deterministic.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a_det",
                "type: deterministic",
                "description: desc",
                "script: print(ok)",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b_judge.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b_judge",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    assert "harness_judge check requires a harness" in str(excinfo.value)
    assert str(checks_dir / "b_judge.yaml") in str(excinfo.value)


def test_multiple_harness_judge_without_harness_reports_sorted_first(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for name, check_id in (("z_last.yaml", "z_last"), ("a_first.yaml", "a_first")):
        (checks_dir / name).write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    f"id: {check_id}",
                    "type: harness_judge",
                    "description: desc",
                    "instructions: Judge the output.",
                ]
            ),
            encoding="utf-8",
        )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    message = str(excinfo.value)
    assert "harness_judge check requires a harness" in message
    assert str(checks_dir / "a_first.yaml") in message
    assert str(checks_dir / "z_last.yaml") not in message
