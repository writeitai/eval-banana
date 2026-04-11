from __future__ import annotations

from datetime import datetime
from datetime import timezone
import logging
import os
from pathlib import Path
import subprocess

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import TaskBasedCheckDefinition

logger = logging.getLogger(__name__)


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _build_env(
    *, check: TaskBasedCheckDefinition, project_root: Path, output_dir: Path
) -> dict[str, str]:
    env = dict(os.environ)
    env.update(check.env)
    env["EVAL_BANANA_PROJECT_ROOT"] = str(project_root)
    env["EVAL_BANANA_OUTPUT_DIR"] = str(output_dir / check.id)
    env["EVAL_BANANA_CHECK_ID"] = check.id
    return env


def run_task_based_check(
    *,
    check: TaskBasedCheckDefinition,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
) -> CheckResult:
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()

    working_directory = project_root
    if check.working_directory is not None:
        working_directory = (project_root / check.working_directory).resolve()

    try:
        completed_process = subprocess.run(
            check.command,
            capture_output=True,
            check=False,
            cwd=working_directory,
            env=_build_env(
                check=check, project_root=project_root, output_dir=output_dir
            ),
            text=True,
        )
    except (FileNotFoundError, OSError, PermissionError) as exc:
        logger.error("Task-based check %s failed to execute: %s", check.id, exc)
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.task_based,
            description=check.description,
            source_path=str(source_path.resolve()),
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=str(exc),
        )

    completed = datetime.now(timezone.utc)
    if completed_process.returncode == 0:
        status = CheckStatus.passed
        score = 1
    else:
        status = CheckStatus.failed
        score = 0

    return CheckResult(
        check_id=check.id,
        check_type=CheckType.task_based,
        description=check.description,
        source_path=str(source_path.resolve()),
        status=status,
        score=score,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        stdout=completed_process.stdout,
        stderr=completed_process.stderr,
        exit_code=completed_process.returncode,
    )
