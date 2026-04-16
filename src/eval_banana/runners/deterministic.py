from __future__ import annotations

from datetime import datetime
from datetime import timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import DeterministicCheckDefinition

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _resolve_script_path(
    *, check: DeterministicCheckDefinition, source_path: Path, temp_dir: Path
) -> Path:
    if check.script is not None:
        return _write_inline_script(script=check.script, temp_dir=temp_dir)

    if check.script_path is None:
        msg = "deterministic check is missing script source"
        raise FileNotFoundError(msg)

    script_path = (source_path.parent / check.script_path).resolve()
    if not script_path.is_file():
        msg = f"Deterministic script not found: {script_path}"
        raise FileNotFoundError(msg)
    return script_path


def _build_context_payload(
    *,
    check: DeterministicCheckDefinition,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    for target in check.target_paths:
        resolved = (project_root / target).resolve()
        targets.append(
            {
                "path": target,
                "resolved_path": str(resolved),
                "exists": resolved.exists(),
                "is_dir": resolved.is_dir(),
            }
        )

    return {
        "check_id": check.id,
        "description": check.description,
        "project_root": str(project_root),
        "source_path": str(source_path.resolve()),
        "output_dir": str((output_dir / check.id).resolve()),
        "targets": targets,
    }


def _write_inline_script(*, script: str, temp_dir: Path) -> Path:
    script_path = temp_dir / "inline_check.py"
    script_path.write_text(script, encoding="utf-8")
    return script_path


def run_deterministic_check(
    *,
    check: DeterministicCheckDefinition,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
) -> CheckResult:
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    check_output_dir = output_dir / check.id
    check_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix=f"{check.id}_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            script_path = _resolve_script_path(
                check=check, source_path=source_path, temp_dir=temp_dir
            )
            context_payload = _build_context_payload(
                check=check,
                source_path=source_path,
                project_root=project_root,
                output_dir=output_dir,
            )
            context_path = temp_dir / "context.json"
            context_path.write_text(
                json.dumps(context_payload, indent=2), encoding="utf-8"
            )
            logger.debug("Running deterministic check %s via %s", check.id, script_path)
            completed_process = subprocess.run(
                [sys.executable, str(script_path), str(context_path)],
                capture_output=True,
                check=False,
                cwd=project_root,
                text=True,
            )
    except (FileNotFoundError, OSError, PermissionError) as exc:
        logger.error("Deterministic check %s failed to execute: %s", check.id, exc)
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
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
        check_type=CheckType.deterministic,
        description=check.description,
        source_path=str(source_path.resolve()),
        tags=check.tags,
        status=status,
        score=score,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        stdout=completed_process.stdout,
        stderr=completed_process.stderr,
        exit_code=completed_process.returncode,
    )
