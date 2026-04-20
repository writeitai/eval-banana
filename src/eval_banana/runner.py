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
from eval_banana.runners.harness_judge import run_harness_judge_check
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
    return run_harness_judge_check


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


def require_harness_for_harness_judge(
    *, config: Config, selected_checks: list[tuple[Path, CheckDefinition]]
) -> None:
    """Abort with :class:`SystemExit` if any selected check is a
    ``harness_judge`` but no harness agent is configured.

    Called before execution begins so the user gets an actionable error
    message naming the first offending YAML file and pointing at the
    ``[harness] agent`` config key and ``--harness-agent`` CLI flag.
    """
    if config.harness_agent is not None:
        return

    ordered_checks = sorted(selected_checks, key=lambda item: str(item[0]))
    harness_judge_paths = [
        str(path)
        for path, definition in ordered_checks
        if definition.type == "harness_judge"
    ]
    if not harness_judge_paths:
        return

    msg = (
        "harness_judge check requires a harness but none is configured "
        f"(first offender: {harness_judge_paths[0]}). "
        "Fix: set [harness] agent in .eval-banana/config.toml or pass "
        "--harness-agent on the command line."
    )
    raise SystemExit(msg)


def run_checks(
    *,
    config: Config,
    check_dir: Path | None = None,
    check_id: str | None = None,
    tags: list[str] | None = None,
) -> EvalReport:
    """Top-level orchestration: discover checks, execute checks, and score.

    Steps (in order):
    1. Discover YAML check files under *config.project_root*.
    2. Load and validate check definitions (or a single one via *check_id*).
    3. Filter by *tags* if provided.
    4. Validate that ``harness_judge`` checks have a configured harness.
    5. Execute each selected check via its type-specific runner.
    6. Score results, emit reports, and return the :class:`EvalReport`.
    """
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

    require_harness_for_harness_judge(config=config, selected_checks=selected_checks)

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
