from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess

import pytest

from eval_banana.config import Config
from eval_banana.models import TaskBasedCheckDefinition
from eval_banana.runners.task_based import run_task_based_check


def test_pass_fail_and_error_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "task.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    check = TaskBasedCheckDefinition(
        schema_version=1,
        id="task_check",
        type="task_based",
        description="desc",
        command=["pytest"],
    )
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


def test_env_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "task.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    captured = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    check = TaskBasedCheckDefinition(
        schema_version=1,
        id="task_env",
        type="task_based",
        description="desc",
        command=["pytest"],
        env={"CUSTOM": "1"},
    )

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert captured["env"]["CUSTOM"] == "1"
    assert captured["env"]["EVAL_BANANA_CHECK_ID"] == "task_env"


def test_working_directory_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "task.yaml"
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    workdir = tmp_path / "subdir"
    workdir.mkdir()
    captured = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("eval_banana.runners.task_based.subprocess.run", fake_run)
    check = TaskBasedCheckDefinition(
        schema_version=1,
        id="task_dir",
        type="task_based",
        description="desc",
        command=["pytest"],
        working_directory="subdir",
    )

    run_task_based_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert captured["cwd"] == workdir.resolve()
