from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from datetime import timezone
import logging
from pathlib import Path
from typing import Literal
import uuid

import yaml

from eval_banana.config import Config
from eval_banana.discovery import discover_check_files
from eval_banana.harness.registry import resolve_template
from eval_banana.harness.runner import run_harness
from eval_banana.loader import load_check_definition
from eval_banana.loader import load_check_definitions
from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckType
from eval_banana.models import EvalReport
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus
from eval_banana.reporter import emit_console_report
from eval_banana.reporter import write_report_files
from eval_banana.runners.deterministic import run_deterministic_check
from eval_banana.runners.llm_judge import run_llm_judge_check
from eval_banana.scorer import score_results

logger = logging.getLogger(__name__)

_HARNESS_ABORT_STATUSES = {HarnessStatus.failed, HarnessStatus.error}


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


def _resolve_harness_prompt(
    *, config: Config
) -> tuple[str, Literal["inline", "file"], str | None]:
    if config.harness_prompt is not None and config.harness_prompt_file is not None:
        msg = "Harness prompt and prompt_file are mutually exclusive"
        raise SystemExit(msg)
    if config.harness_prompt is None and config.harness_prompt_file is None:
        msg = "Harness requires either prompt or prompt_file"
        raise SystemExit(msg)
    if config.harness_prompt is not None:
        return config.harness_prompt, "inline", None

    if config.project_root is None or config.harness_prompt_file is None:
        msg = "Config.project_root must be set before resolving harness prompts"
        raise SystemExit(msg)

    prompt_path = Path(config.harness_prompt_file)
    if not prompt_path.is_absolute():
        prompt_path = (config.project_root / prompt_path).resolve()
    if not prompt_path.is_file():
        msg = f"Harness prompt file not found: {prompt_path}"
        raise SystemExit(msg)
    return (prompt_path.read_text(encoding="utf-8"), "file", str(prompt_path))


def _select_runner(check: CheckDefinition) -> Callable[..., CheckResult]:
    if check.type == "deterministic":
        return run_deterministic_check
    return run_llm_judge_check


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


def _filter_checks_by_tags(
    *, checks: list[tuple[Path, CheckDefinition]], tags: list[str] | None
) -> list[tuple[Path, CheckDefinition]]:
    if not tags:
        return checks

    requested_tags = set(tags)
    return [
        (source_path, definition)
        for source_path, definition in checks
        if requested_tags.intersection(definition.tags)
    ]


def require_harness_for_llm_judge(
    *, config: Config, selected_checks: list[tuple[Path, CheckDefinition]]
) -> None:
    # llm_judge checks work with or without a harness: they evaluate
    # existing artifacts via direct LLM API calls regardless of whether
    # an agent ran first.
    pass


def run_checks(
    *,
    config: Config,
    check_dir: Path | None = None,
    check_id: str | None = None,
    tags: list[str] | None = None,
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

    selected_checks = _filter_checks_by_tags(checks=selected_checks, tags=tags)

    if not selected_checks:
        msg = "No checks found"
        raise SystemExit(msg)

    require_harness_for_llm_judge(config=config, selected_checks=selected_checks)

    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    run_id = _make_run_id()
    run_output_dir = _prepare_run_output_dir(config=config, run_id=run_id)
    checks_output_dir = run_output_dir / "checks"
    harness_result: HarnessResult | None = None

    if config.harness_agent is not None:
        prompt_text, prompt_source, prompt_file = _resolve_harness_prompt(config=config)
        template = resolve_template(
            agent_type=config.harness_agent, user_templates=config.agent_templates
        )
        if config.harness_reasoning_effort is not None:
            template = replace(
                template, reasoning_effort=config.harness_reasoning_effort
            )
        harness_result = run_harness(
            agent_type=config.harness_agent,
            template=template,
            prompt=prompt_text,
            prompt_source=prompt_source,
            prompt_file=prompt_file,
            project_root=config.project_root,
            run_id=run_id,
            run_output_dir=run_output_dir,
            model=config.harness_model,
            harness_env=config.harness_env,
        )
        if harness_result.status in _HARNESS_ABORT_STATUSES:
            completed = datetime.now(timezone.utc)
            report = score_results(
                run_id=run_id,
                project_root=config.project_root,
                output_dir=run_output_dir,
                started_at=started_at,
                completed_at=completed.isoformat(),
                pass_threshold=config.pass_threshold,
                results=[],
                harness=harness_result,
            )
            emit_console_report(report=report)
            write_report_files(report=report, output_dir=run_output_dir)
            return report

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
        harness=harness_result,
    )
    emit_console_report(report=report)
    write_report_files(report=report, output_dir=run_output_dir)
    return report
