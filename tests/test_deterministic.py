from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import subprocess

import pytest

from eval_banana.config import Config
from eval_banana.models import DeterministicCheckDefinition
from eval_banana.runners.deterministic import run_deterministic_check


def test_inline_script_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    project_root = tmp_path
    source_path = tmp_path / "eval_checks" / "one.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        context_path = Path(args[2])
        captured["context"] = json.loads(context_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ok", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.deterministic.subprocess.run", fake_run)
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="inline_pass",
        type="deterministic",
        description="desc",
        target_paths=["README.md"],
        script="print('ok')",
    )

    result = run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=project_root,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=project_root),
    )

    assert result.status == "passed"
    assert result.score == 1
    assert result.stdout == "ok"
    assert captured["cwd"] == project_root
    assert captured["context"]["targets"][0]["resolved_path"] == str(
        (tmp_path / "README.md").resolve()
    )


def test_inline_script_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "one.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=2, stdout="", stderr="bad"
        )

    monkeypatch.setattr("eval_banana.runners.deterministic.subprocess.run", fake_run)
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="inline_fail",
        type="deterministic",
        description="desc",
        script="print('bad')",
    )

    result = run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "failed"
    assert result.exit_code == 2


def test_script_path_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "one.yaml"
    script_path = tmp_path / "eval_checks" / "scripts" / "check.py"
    script_path.parent.mkdir(parents=True)
    source_path.write_text("", encoding="utf-8")
    script_path.write_text("print('ok')", encoding="utf-8")
    captured = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["script_path"] = args[1]
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.deterministic.subprocess.run", fake_run)
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="path_check",
        type="deterministic",
        description="desc",
        script_path="scripts/check.py",
    )

    run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert captured["script_path"] == str(script_path.resolve())


def test_timeout_handling_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "one.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            cmd=args, timeout=30, output="out", stderr="err"
        )

    monkeypatch.setattr("eval_banana.runners.deterministic.subprocess.run", fake_run)
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="timeout_check",
        type="deterministic",
        description="desc",
        script="print('ok')",
    )

    result = run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"
    assert result.stderr == "err"


def test_missing_script_returns_error(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "one.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="missing_script",
        type="deterministic",
        description="desc",
        script_path="missing.py",
    )

    result = run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"
    assert "missing.py" in (result.error_detail or "")


def test_subprocess_cwd_is_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "one.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    captured = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.deterministic.subprocess.run", fake_run)
    check = DeterministicCheckDefinition(
        schema_version=1,
        id="cwd_check",
        type="deterministic",
        description="desc",
        script="print('ok')",
    )

    run_deterministic_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert captured["cwd"] == tmp_path
