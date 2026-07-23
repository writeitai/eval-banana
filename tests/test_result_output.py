from __future__ import annotations

from collections.abc import Callable
import importlib.metadata
import json
from pathlib import Path
import subprocess

import pytest

from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import EvalReport
from eval_banana.result_output import build_result_document
from eval_banana.result_output import DIRTY_TREE_ALGORITHM
from eval_banana.result_output import observe_dirty_tree
from eval_banana.result_output import ObservedGit
from eval_banana.result_output import read_head_commit
from eval_banana.result_output import render_result_document
from eval_banana.result_output import ResultStatus
from eval_banana.result_output import write_result_document


def _init_git_repo(*, path: Path) -> str:
    """Create a one-commit git repo at *path* and return the commit sha."""

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


def _null_observed(*, commit_before: str | None = None) -> ObservedGit:
    return ObservedGit(
        commit_before=commit_before,
        commit_after=None,
        dirty_tree_digest=None,
        dirty_tree_algorithm=None,
    )


def _make_report(
    *, checks: list[CheckResult], run_passed: bool = True, pass_threshold: float = 1.0
) -> EvalReport:
    return EvalReport(
        run_id="run1",
        project_root="/tmp/project",
        output_dir="/tmp/project/out",
        started_at="2026-07-22T12:00:00+00:00",
        completed_at="2026-07-22T12:00:01+00:00",
        duration_ms=1000,
        total_checks=len(checks),
        passed_checks=sum(1 for c in checks if c.status == CheckStatus.passed),
        failed_checks=sum(1 for c in checks if c.status == CheckStatus.failed),
        errored_checks=sum(1 for c in checks if c.status == CheckStatus.error),
        points_earned=sum(c.score for c in checks),
        total_points=len(checks),
        percentage=100.0 if run_passed else 0.0,
        pass_threshold=pass_threshold,
        meets_threshold=run_passed,
        run_passed=run_passed,
        checks=checks,
    )


def _extract_fenced_json(*, text: str) -> dict[str, object]:
    lines = text.splitlines()
    start = lines.index("```eval-banana-result v1")
    end = lines.index("```", start + 1)
    return json.loads("\n".join(lines[start + 1 : end]))


def test_read_head_commit_reads_real_repo(tmp_path: Path) -> None:
    commit = _init_git_repo(path=tmp_path)

    assert read_head_commit(cwd=str(tmp_path)) == commit


def test_read_head_commit_returns_none_outside_git(tmp_path: Path) -> None:
    assert read_head_commit(cwd=str(tmp_path)) is None


def test_observe_dirty_tree_records_digest_in_repo(tmp_path: Path) -> None:
    _init_git_repo(path=tmp_path)

    dirty = observe_dirty_tree(cwd=str(tmp_path))

    assert dirty.digest is not None
    assert dirty.digest.startswith("sha256:")
    assert dirty.algorithm == DIRTY_TREE_ALGORITHM


def test_observe_dirty_tree_tracks_unstaged_change(tmp_path: Path) -> None:
    _init_git_repo(path=tmp_path)
    clean = observe_dirty_tree(cwd=str(tmp_path))

    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    dirty = observe_dirty_tree(cwd=str(tmp_path))

    assert clean.digest != dirty.digest
    assert dirty.algorithm == DIRTY_TREE_ALGORITHM


def test_observe_dirty_tree_reflects_staged_content(tmp_path: Path) -> None:
    """Staged blob content changes the digest even when porcelain is identical."""

    _init_git_repo(path=tmp_path)
    tracked = tmp_path / "tracked.txt"

    def _git(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    tracked.write_text("AAAA\n", encoding="utf-8")
    _git("add", "tracked.txt")
    staged_a = observe_dirty_tree(cwd=str(tmp_path))

    tracked.write_text("BBBB\n", encoding="utf-8")
    _git("add", "tracked.txt")
    staged_b = observe_dirty_tree(cwd=str(tmp_path))

    # Both states share the porcelain line "M  tracked.txt" and an empty unstaged
    # diff; only git diff --cached distinguishes the staged blob content.
    assert staged_a.digest != staged_b.digest


def test_observe_dirty_tree_nulls_outside_git(tmp_path: Path) -> None:
    dirty = observe_dirty_tree(cwd=str(tmp_path))

    assert dirty.digest is None
    assert dirty.algorithm is None


def test_build_result_document_completed_captures_model_and_effort(
    make_check_result: Callable[..., CheckResult],
) -> None:
    checks = [
        make_check_result(
            check_id="goal_outcome",
            status=CheckStatus.passed,
            reason="looks good",
            details={"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
        )
    ]
    report = _make_report(checks=checks)

    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=1.0,
        harness_family="codex",
        observed=_null_observed(),
        provenance={"attempt": "attempt-7"},
        error=None,
    )

    assert document.status == "completed"
    assert document.run_passed is True
    assert document.harness.family == "codex"
    assert document.harness.effort == "xhigh"
    assert document.error is None
    assert len(document.checks) == 1
    assert document.checks[0].id == "goal_outcome"
    assert document.checks[0].model == "gpt-5.6-sol"
    assert document.tool_version == importlib.metadata.version("eval-banana")


def test_build_result_document_failure_has_empty_checks_and_error() -> None:
    document = build_result_document(
        status=ResultStatus.no_checks,
        report=None,
        pass_threshold=1.0,
        harness_family="codex",
        observed=_null_observed(commit_before="abc123"),
        provenance={"attempt": None},
        error="No checks found",
    )

    assert document.status == "no_checks"
    assert document.run_passed is False
    assert document.checks == []
    assert document.harness.effort is None
    assert document.error == "No checks found"
    assert document.observed.commit_before == "abc123"


def test_render_md_fenced_block_round_trips(
    make_check_result: Callable[..., CheckResult],
) -> None:
    report = _make_report(checks=[make_check_result(check_id="c1")])
    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=1.0,
        harness_family=None,
        observed=_null_observed(),
        provenance={"attempt": "a1"},
        error=None,
    )

    text = render_result_document(document=document, result_format="md", report=report)

    parsed = _extract_fenced_json(text=text)
    assert parsed["schema_version"] == 1
    assert parsed["status"] == "completed"
    assert parsed["provenance"] == {"attempt": "a1"}
    # The human report body follows the fenced machine block.
    assert "# eval-banana report" in text


def test_render_json_is_standalone_parseable(
    make_check_result: Callable[..., CheckResult],
) -> None:
    report = _make_report(checks=[make_check_result(check_id="c1")])
    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=1.0,
        harness_family=None,
        observed=_null_observed(),
        provenance={"attempt": "a1"},
        error=None,
    )

    text = render_result_document(
        document=document, result_format="json", report=report
    )

    parsed = json.loads(text)
    assert parsed["status"] == "completed"
    assert parsed["checks"][0]["id"] == "c1"


def test_write_result_document_is_atomic_and_cleans_temp(
    tmp_path: Path, make_check_result: Callable[..., CheckResult]
) -> None:
    report = _make_report(checks=[make_check_result(check_id="c1")])
    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=1.0,
        harness_family=None,
        observed=_null_observed(),
        provenance={"attempt": "a1"},
        error=None,
    )
    result_out = tmp_path / "nested" / "eval_results.md"

    write_result_document(
        document=document, result_out=result_out, result_format="md", report=report
    )

    assert result_out.is_file()
    # No temp sibling is left behind after an atomic replace.
    assert list(result_out.parent.iterdir()) == [result_out]


def test_write_result_document_refuses_symlink_target(
    tmp_path: Path, make_check_result: Callable[..., CheckResult]
) -> None:
    report = _make_report(checks=[make_check_result(check_id="c1")])
    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=1.0,
        harness_family=None,
        observed=_null_observed(),
        provenance={"attempt": "a1"},
        error=None,
    )
    real_file = tmp_path / "real.md"
    real_file.write_text("original\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real_file)

    with pytest.raises(SystemExit) as excinfo:
        write_result_document(
            document=document, result_out=link, result_format="md", report=report
        )

    assert "symlink" in str(excinfo.value)
    # The symlink target is left untouched.
    assert real_file.read_text(encoding="utf-8") == "original\n"
