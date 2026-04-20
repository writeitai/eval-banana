from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from eval_banana.models import CheckResult
from eval_banana.scorer import score_results


def test_counts_and_percentage(
    make_check_result: Callable[..., CheckResult], tmp_path: Path
) -> None:
    report = score_results(
        run_id="run1",
        project_root=tmp_path,
        output_dir=tmp_path / "out",
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:10+00:00",
        pass_threshold=0.5,
        results=[
            make_check_result(check_id="one", status="passed", score=1),
            make_check_result(check_id="two", status="failed", score=0),
            make_check_result(check_id="three", status="error", score=0),
        ],
    )

    assert report.passed_checks == 1
    assert report.failed_checks == 1
    assert report.errored_checks == 1
    assert report.percentage == 33.3


def test_threshold_evaluation(
    make_check_result: Callable[..., CheckResult], tmp_path: Path
) -> None:
    report = score_results(
        run_id="run1",
        project_root=tmp_path,
        output_dir=tmp_path / "out",
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:10+00:00",
        pass_threshold=0.5,
        results=[
            make_check_result(check_id="one", status="passed", score=1),
            make_check_result(check_id="two", status="passed", score=1),
        ],
    )

    assert report.meets_threshold is True
    assert report.run_passed is True


def test_empty_result_set(
    make_check_result: Callable[..., CheckResult], tmp_path: Path
) -> None:
    report = score_results(
        run_id="run1",
        project_root=tmp_path,
        output_dir=tmp_path / "out",
        started_at="2026-04-09T12:00:00+00:00",
        completed_at="2026-04-09T12:00:10+00:00",
        pass_threshold=1.0,
        results=[],
    )

    assert report.percentage == 0.0
    assert report.run_passed is False
