from __future__ import annotations

from datetime import datetime
from datetime import timezone
import logging
import os
from pathlib import Path
import re
import subprocess

from eval_banana.config import Config
from eval_banana.config import HarnessConfig
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import TaskBasedCheckDefinition

logger = logging.getLogger(__name__)

_MISSING_WARNED: set[str] = set()
_PLACEHOLDER_RE = re.compile(r"\{env:([A-Z_][A-Z0-9_]*)\}")
_SINGLE_PLACEHOLDER_RE = re.compile(r"^\{env:([A-Z_][A-Z0-9_]*)\}$")


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _warn_missing(*, name: str) -> None:
    if name in _MISSING_WARNED:
        return
    _MISSING_WARNED.add(name)
    logger.warning(
        "Harness env placeholder {env:%s} is unset; substituting empty string", name
    )


def _reset_warn_state() -> None:
    _MISSING_WARNED.clear()


def _substitute(*, value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        found = os.environ.get(name)
        if found is not None:
            return found
        _warn_missing(name=name)
        return ""

    return _PLACEHOLDER_RE.sub(replace, value)


def resolve_provider_env(*, raw_env: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in raw_env.items():
        single_match = _SINGLE_PLACEHOLDER_RE.match(value)
        if single_match is not None:
            name = single_match.group(1)
            found = os.environ.get(name)
            if found is None:
                _warn_missing(name=name)
                continue
            resolved[key] = found
            continue
        resolved[key] = _substitute(value=value)
    return resolved


def _build_base_env(
    *, check: TaskBasedCheckDefinition, project_root: Path, output_dir: Path
) -> dict[str, str]:
    env = dict(os.environ)
    env["EVAL_BANANA_PROJECT_ROOT"] = str(project_root)
    env["EVAL_BANANA_OUTPUT_DIR"] = str(output_dir / check.id)
    env["EVAL_BANANA_CHECK_ID"] = check.id
    return env


def _build_legacy_env(
    *, check: TaskBasedCheckDefinition, project_root: Path, output_dir: Path
) -> dict[str, str]:
    env = dict(os.environ)
    env.update(check.env)
    env["EVAL_BANANA_PROJECT_ROOT"] = str(project_root)
    env["EVAL_BANANA_OUTPUT_DIR"] = str(output_dir / check.id)
    env["EVAL_BANANA_CHECK_ID"] = check.id
    return env


def _get_harness(
    *, check: TaskBasedCheckDefinition, config: Config
) -> HarnessConfig | None:
    if check.harness is None:
        return None
    return config.harnesses.get(check.harness)


def _resolve_model(
    *, check: TaskBasedCheckDefinition, harness: HarnessConfig
) -> str | None:
    if check.model is not None:
        return check.model
    return harness.default_model


def _render_argv(
    *, check: TaskBasedCheckDefinition, harness: HarnessConfig, model: str | None
) -> list[str]:
    argv: list[str] = []
    argv.extend(harness.command)
    argv.extend(harness.shared_flags)
    if model is not None and harness.model_flag is not None:
        argv.extend([harness.model_flag, model])
    argv.extend(check.command)
    return argv


def _build_harness_env(
    *,
    check: TaskBasedCheckDefinition,
    project_root: Path,
    output_dir: Path,
    harness: HarnessConfig,
    model: str | None,
) -> dict[str, str]:
    env = _build_base_env(check=check, project_root=project_root, output_dir=output_dir)
    env.update(resolve_provider_env(raw_env=harness.provider_env))
    if model is not None:
        for env_name in harness.model_env_vars:
            env[env_name] = model
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

    argv = check.command
    env = _build_legacy_env(
        check=check, project_root=project_root, output_dir=output_dir
    )
    if check.harness is not None:
        harness = _get_harness(check=check, config=config)
        if harness is None:
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
                error_detail=(
                    f"Unknown harness {check.harness!r}. Define it in "
                    f"[harnesses.{check.harness}] in your config.toml."
                ),
            )
        model = _resolve_model(check=check, harness=harness)
        argv = _render_argv(check=check, harness=harness, model=model)
        env = _build_harness_env(
            check=check,
            project_root=project_root,
            output_dir=output_dir,
            harness=harness,
            model=model,
        )

    try:
        completed_process = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            cwd=working_directory,
            env=env,
            text=True,
            timeout=check.timeout_seconds or config.task_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Task-based check %s timed out", check.id)
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
            error_detail=f"Task-based check timed out after {exc.timeout} seconds",
            stdout=_coerce_output(exc.stdout),
            stderr=_coerce_output(exc.stderr),
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
