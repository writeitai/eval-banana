from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

from eval_banana.models import CheckResult
from eval_banana.models import EvalReport
from eval_banana.reporter import _build_markdown_report
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
    assert (tmp_path / "report" / "checks" / f"{stem}.stdout.txt").is_file()
    assert (tmp_path / "report" / "checks" / f"{stem}.stderr.txt").is_file()


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

    markdown = _build_markdown_report(report=report)

    assert "| Field | Value |" in markdown
    assert "| Check ID | Type | Status | Score | Duration (ms) |" in markdown
    assert "Reason: bad" in markdown
