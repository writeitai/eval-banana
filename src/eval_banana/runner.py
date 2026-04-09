from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from datetime import timezone
import logging
from pathlib import Path
import uuid

import yaml

from eval_banana.config import Config
from eval_banana.discovery import discover_check_files
from eval_banana.loader import load_check_definition
from eval_banana.loader import load_check_definitions
from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import EvalReport
from eval_banana.reporter import emit_console_report
from eval_banana.reporter import write_report_files
from eval_banana.runners.deterministic import run_deterministic_check
from eval_banana.runners.llm_judge import run_llm_judge_check
from eval_banana.runners.task_based import run_task_based_check
from eval_banana.scorer import score_results

logger = logging.getLogger(__name__)


def _make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{suffix}"


def _prepare_run_output_dir(*, config: Config, run_id: str) -> Path:
    base_output_dir = Path(config.output_dir)
    run_output_dir = (base_output_dir / run_id).resolve()
    run_output_dir.mkdir(parents=True, exist_ok=True)
    (run_output_dir / "checks").mkdir(parents=True, exist_ok=True)
    return run_output_dir


def _select_runner(check: CheckDefinition) -> Callable[..., CheckResult]:
    if check.type == "deterministic":
        return run_deterministic_check
    if check.type == "llm_judge":
        return run_llm_judge_check
    if check.type == "task_based":
        return run_task_based_check
    msg = f"Unsupported check type: {check.type}"
    raise ValueError(msg)


def _find_check_path_by_id(*, paths: list[Path], check_id: str) -> Path | None:
    matches: list[Path] = []
    for path in paths:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("id") == check_id:
            matches.append(path)
    if len(matches) > 1:
        locations = ", ".join(str(p) for p in matches)
        msg = f"Duplicate check id '{check_id}' found in: {locations}"
        raise SystemExit(msg)
    return matches[0] if matches else None


def run_checks(
    *, config: Config, check_dir: Path | None = None, check_id: str | None = None
) -> EvalReport:
    if config.project_root is None:
        msg = "Config.project_root must be set"
        raise SystemExit(msg)

    explicit_check_dir: Path | None = None
    if check_dir is not None:
        explicit_check_dir = check_dir
        if not explicit_check_dir.is_absolute():
            explicit_check_dir = (config.project_root / explicit_check_dir).resolve()

    discovered_paths = discover_check_files(
        start_dir=config.project_root,
        explicit_check_dir=explicit_check_dir,
        exclude_dirs=config.discovery_exclude_dirs,
    )
    logger.debug("Discovered %s check files", len(discovered_paths))

    selected_checks: list[tuple[Path, CheckDefinition]]
    if check_id is not None:
        selected_path = _find_check_path_by_id(
            paths=discovered_paths, check_id=check_id
        )
        if selected_path is None:
            msg = f"No check found with id '{check_id}'"
            raise SystemExit(msg)
        selected_checks = [(selected_path, load_check_definition(path=selected_path))]
    else:
        selected_checks = load_check_definitions(paths=discovered_paths)

    if not selected_checks:
        msg = "No checks found"
        raise SystemExit(msg)

    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    run_id = _make_run_id()
    run_output_dir = _prepare_run_output_dir(config=config, run_id=run_id)
    checks_output_dir = run_output_dir / "checks"

    results: list[CheckResult] = []
    for source_path, definition in sorted(
        selected_checks, key=lambda item: str(item[0])
    ):
        logger.info("Running check %s", definition.id)
        runner = _select_runner(definition)
        result = runner(
            check=definition,
            source_path=source_path,
            project_root=config.project_root,
            output_dir=checks_output_dir,
            config=config,
        )
        results.append(result)

    completed = datetime.now(timezone.utc)
    report = score_results(
        run_id=run_id,
        project_root=config.project_root,
        output_dir=run_output_dir,
        started_at=started_at,
        completed_at=completed.isoformat(),
        pass_threshold=config.pass_threshold,
        results=results,
    )
    emit_console_report(report=report)
    write_report_files(report=report, output_dir=run_output_dir)
    return report
