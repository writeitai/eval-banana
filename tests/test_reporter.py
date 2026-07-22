from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

from eval_banana.models import CheckResult
from eval_banana.models import EvalReport
from eval_banana.reporter import bound_stdout_tail
from eval_banana.reporter import build_markdown_report
from eval_banana.reporter import persist_check_stdout
from eval_banana.reporter import safe_file_stem
from eval_banana.reporter import write_report_files


def test_json_and_markdown_file_creation(
    tmp_path: Path, make_check_result: Callable[..., CheckResult]
) -> None:
    """Write versioned JSON plus the human and per-check report artifacts."""
    report = EvalReport(
        run_id="run1",
        project_root=str(tmp_path),
        output_dir=str(tmp_path / "out"),
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
        checks=[make_check_result(stdout="hello", stderr="bad")],
    )

    write_report_files(report=report, output_dir=tmp_path / "report")

    assert (tmp_path / "report" / "report.json").is_file()
    report_payload = json.loads(
        (tmp_path / "report" / "report.json").read_text(encoding="utf-8")
    )
    assert report_payload["schema_version"] == 1
    assert (tmp_path / "report" / "report.md").is_file()
    stem = safe_file_stem(text="check_one")
    assert (tmp_path / "report" / "checks" / f"{stem}.json").is_file()
    assert (tmp_path / "report" / "checks" / f"{stem}.stderr.txt").is_file()
    # The full stdout stream is persisted by the runner, not the reporter, so
    # write_report_files never rewrites the (bounded) stdout tail to disk.
    assert not (tmp_path / "report" / "checks" / f"{stem}.stdout.txt").exists()


def test_bound_stdout_tail_returns_short_output_unchanged() -> None:
    """Leave output that fits under the tail budget exactly as produced."""

    assert (
        bound_stdout_tail(
            stdout="short output", raw_response_path="checks/x.stdout.txt"
        )
        == "short output"
    )


def test_bound_stdout_tail_truncates_long_output_with_banner() -> None:
    """Replace long output with a banner naming the file plus the trailing tail."""

    text = "HEAD" + ("z" * 5000) + "TAIL"
    bounded = bound_stdout_tail(
        stdout=text, raw_response_path="checks/judge.stdout.txt"
    )

    assert len(bounded) < len(text)
    assert "HEAD" not in bounded
    assert "checks/judge.stdout.txt" in bounded
    assert "truncated to the last 2000" in bounded
    assert bounded.endswith(text[-2000:])


def test_persist_check_stdout_writes_full_stream_and_returns_relpath(
    tmp_path: Path,
) -> None:
    """Persist the untruncated stream and return its run-relative location."""

    checks_dir = tmp_path / "checks"
    relpath = persist_check_stdout(
        output_dir=checks_dir, check_id="judge", stdout="the full stream"
    )

    assert relpath is not None
    assert relpath.startswith("checks/")
    assert (tmp_path / relpath).read_text(encoding="utf-8") == "the full stream"


def test_persist_check_stdout_skips_empty_output(tmp_path: Path) -> None:
    """Skip persistence entirely when a check produced no stdout."""

    assert (
        persist_check_stdout(
            output_dir=tmp_path / "checks", check_id="judge", stdout=""
        )
        is None
    )
    assert not (tmp_path / "checks").exists()


def test_safe_filename_generation() -> None:
    check_id = "bad name/with spaces"
    digest = hashlib.sha256(string=check_id.encode(encoding="utf-8")).hexdigest()

    assert safe_file_stem(text=check_id) == f"bad_name_with_spaces-{digest}"


def test_markdown_contains_tables(
    tmp_path: Path, make_check_result: Callable[..., CheckResult]
) -> None:
    report = EvalReport(
        run_id="run1",
        project_root=str(tmp_path),
        output_dir=str(tmp_path / "out"),
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
        checks=[make_check_result(status="failed", score=0, reason="bad")],
    )

    markdown = build_markdown_report(report=report)

    assert "| Field | Value |" in markdown
    assert "| Check ID | Type | Status | Score | Duration (ms) |" in markdown
    assert "Reason: bad" in markdown
