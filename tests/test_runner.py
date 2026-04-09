from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
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
