from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import EvalReport
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus

logger = logging.getLogger(__name__)


def score_results(
    *,
    run_id: str,
    project_root: Path,
    output_dir: Path,
    started_at: str,
    completed_at: str,
    pass_threshold: float,
    results: list[CheckResult],
    harness: HarnessResult | None = None,
) -> EvalReport:
    started = datetime.fromisoformat(started_at)
    completed = datetime.fromisoformat(completed_at)
    duration_ms = int((completed - started).total_seconds() * 1000)

    total_points = len(results)
    points_earned = sum(result.score for result in results)
    passed_checks = sum(1 for result in results if result.status == CheckStatus.passed)
    failed_checks = sum(1 for result in results if result.status == CheckStatus.failed)
    errored_checks = sum(1 for result in results if result.status == CheckStatus.error)

    if total_points == 0:
        percentage = 0.0
        meets_threshold = False
    else:
        percentage = round((points_earned / total_points) * 100, 1)
        meets_threshold = (points_earned / total_points) >= pass_threshold

    harness_allows_pass = harness is None or harness.status in {
        HarnessStatus.succeeded,
        HarnessStatus.skipped,
    }

    return EvalReport(
        run_id=run_id,
        project_root=str(project_root),
        output_dir=str(output_dir),
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        total_checks=len(results),
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        errored_checks=errored_checks,
        points_earned=points_earned,
        total_points=total_points,
        percentage=percentage,
        pass_threshold=pass_threshold,
        meets_threshold=meets_threshold,
        run_passed=meets_threshold and errored_checks == 0 and harness_allows_pass,
        checks=results,
        harness=harness,
    )
