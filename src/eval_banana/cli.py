from __future__ import annotations

import logging
from pathlib import Path

import click

from eval_banana.config import Config
from eval_banana.config import get_local_config_template
from eval_banana.config import load_config
from eval_banana.discovery import discover_check_files
from eval_banana.loader import load_check_definitions
from eval_banana.result_output import build_result_document
from eval_banana.result_output import observe_dirty_tree
from eval_banana.result_output import ObservedGit
from eval_banana.result_output import read_head_commit
from eval_banana.result_output import ResultStatus
from eval_banana.result_output import write_result_document
from eval_banana.runner import require_harness_for_harness_judge
from eval_banana.runner import run_checks

logger = logging.getLogger(__name__)


def _configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(format="%(name)s: %(message)s", level=level)


def _build_provenance(
    *, attempt: str | None, fields: tuple[str, ...]
) -> dict[str, str | None]:
    """Echo caller provenance verbatim: the opaque attempt plus ``k=v`` pairs."""

    provenance: dict[str, str | None] = {"attempt": attempt}
    for pair in fields:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            msg = f"--provenance-field must be key=value, got: {pair}"
            raise click.UsageError(msg)
        provenance[key] = value
    return provenance


def _classify_run_failure(*, message: str) -> str:
    """Map a pre-report load/run failure message to a status envelope.

    Classification keys on specific known messages, not loose substrings: only a
    genuinely empty selection ("No checks found") is ``no_checks``; the harness
    requirement message is ``harness_error``; every other failure (a bad
    ``--check-id``, invalid config/YAML, duplicate ids, load errors) defaults to
    ``config_error``.
    """

    if "No checks found" in message:
        return ResultStatus.no_checks
    if "requires a harness" in message:
        return ResultStatus.harness_error
    return ResultStatus.config_error


@click.group()
def main() -> None:
    return None


@main.command()
@click.option("--force", is_flag=True)
def init(force: bool) -> None:
    config_path = Path.cwd() / ".eval-banana" / "config.toml"
    config_text = get_local_config_template()

    if config_path.exists() and not force:
        raise click.ClickException(
            f"Refusing to overwrite existing file: {config_path}"
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    click.echo(f"Wrote {config_path}")


@main.command(name="run")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option("--check-id")
@click.option(
    "--tag", "tags", multiple=True, help="Filter checks by tag (repeatable, OR logic)"
)
@click.option("--output-dir")
@click.option(
    "--flat-output",
    is_flag=True,
    help="Write artifacts directly into an explicit, empty --output-dir.",
)
@click.option("--pass-threshold", type=float)
@click.option("--harness-agent")
@click.option("--harness-model")
@click.option("--harness-reasoning-effort")
@click.option(
    "--harness-timeout-seconds",
    type=click.IntRange(min=1),
    help="Maximum wall-clock seconds for each harness_judge agent subprocess.",
)
@click.option(
    "--max-parallel-checks",
    type=click.IntRange(min=1),
    help="Maximum number of checks executed concurrently (default 4).",
)
@click.option(
    "--no-project-config",
    is_flag=True,
    help="Do not discover or load .eval-banana/config.toml.",
)
@click.option(
    "--result-out",
    help="Write a provenance-stamped result document to this exact path.",
)
@click.option(
    "--result-format",
    type=click.Choice(["md", "json"]),
    default="md",
    help="Result document format written to --result-out (default md).",
)
@click.option(
    "--provenance-attempt",
    help="Opaque caller attempt id echoed verbatim into the result document.",
)
@click.option(
    "--provenance-field",
    "provenance_field",
    multiple=True,
    help="Extra caller key=value pair echoed into provenance (repeatable).",
)
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def run_cli(
    check_dir: Path | None,
    check_id: str | None,
    tags: tuple[str, ...],
    output_dir: str | None,
    flat_output: bool,
    pass_threshold: float | None,
    harness_agent: str | None,
    harness_model: str | None,
    harness_reasoning_effort: str | None,
    harness_timeout_seconds: int | None,
    max_parallel_checks: int | None,
    no_project_config: bool,
    result_out: str | None,
    result_format: str,
    provenance_attempt: str | None,
    provenance_field: tuple[str, ...],
    cwd: str,
    verbose: bool,
) -> None:
    """Execute selected checks and exit with a status matching the run verdict.

    ``--no-project-config`` makes the invocation hermetic, while
    ``--flat-output`` lets an orchestrator own the exact artifact directory.
    ``--result-out`` additionally writes a single provenance-stamped result
    document; without it, behavior is exactly as before.
    """

    _configure_logging(verbose=verbose)
    if flat_output and output_dir is None:
        raise click.UsageError("--flat-output requires an explicit --output-dir")

    if result_out is None:
        config = load_config(
            output_dir=output_dir,
            pass_threshold=pass_threshold,
            harness_agent=harness_agent,
            harness_model=harness_model,
            harness_reasoning_effort=harness_reasoning_effort,
            harness_timeout_seconds=harness_timeout_seconds,
            max_parallel_checks=max_parallel_checks,
            use_project_config=not no_project_config,
            cwd=cwd,
        )
        report = run_checks(
            config=config,
            check_dir=check_dir,
            check_id=check_id,
            tags=list(tags) or None,
            flat_output=flat_output,
        )
        raise SystemExit(0 if report.run_passed else 1)

    provenance = _build_provenance(attempt=provenance_attempt, fields=provenance_field)
    _run_with_result_document(
        output_dir=output_dir,
        pass_threshold=pass_threshold,
        harness_agent=harness_agent,
        harness_model=harness_model,
        harness_reasoning_effort=harness_reasoning_effort,
        harness_timeout_seconds=harness_timeout_seconds,
        max_parallel_checks=max_parallel_checks,
        no_project_config=no_project_config,
        cwd=cwd,
        check_dir=check_dir,
        check_id=check_id,
        tags=list(tags) or None,
        flat_output=flat_output,
        result_out=Path(result_out),
        result_format=result_format,
        provenance=provenance,
    )


def _run_with_result_document(
    *,
    output_dir: str | None,
    pass_threshold: float | None,
    harness_agent: str | None,
    harness_model: str | None,
    harness_reasoning_effort: str | None,
    harness_timeout_seconds: int | None,
    max_parallel_checks: int | None,
    no_project_config: bool,
    cwd: str,
    check_dir: Path | None,
    check_id: str | None,
    tags: list[str] | None,
    flat_output: bool,
    result_out: Path,
    result_format: str,
    provenance: dict[str, str | None],
) -> None:
    """Load config, run checks, and always write a stamped result document.

    The git subject is observed against the resolved ``--cwd``: ``commit_before``
    and the dirty-tree digest are captured at run start -- before load/run, so a
    harness that dirties the tree mid-run cannot backdate the subject -- and
    ``commit_after`` after the run. Any failure before a report exists, including
    a config-load failure, is classified into a status envelope, stamped with the
    observed subject and empty checks, then re-raised so the non-zero exit is
    preserved.
    """

    git_cwd = str(Path(cwd).resolve())
    commit_before = read_head_commit(cwd=git_cwd)
    dirty = observe_dirty_tree(cwd=git_cwd)

    config: Config | None = None
    try:
        config = load_config(
            output_dir=output_dir,
            pass_threshold=pass_threshold,
            harness_agent=harness_agent,
            harness_model=harness_model,
            harness_reasoning_effort=harness_reasoning_effort,
            harness_timeout_seconds=harness_timeout_seconds,
            max_parallel_checks=max_parallel_checks,
            use_project_config=not no_project_config,
            cwd=cwd,
        )
        report = run_checks(
            config=config,
            check_dir=check_dir,
            check_id=check_id,
            tags=tags,
            flat_output=flat_output,
        )
    except (SystemExit, ValueError) as exc:
        if config is not None:
            failure_pass_threshold = config.pass_threshold
            failure_family = config.harness_agent
        else:
            failure_pass_threshold = (
                pass_threshold if pass_threshold is not None else 1.0
            )
            failure_family = harness_agent
        document = build_result_document(
            status=_classify_run_failure(message=str(exc)),
            report=None,
            pass_threshold=failure_pass_threshold,
            harness_family=failure_family,
            observed=ObservedGit(
                commit_before=commit_before,
                commit_after=read_head_commit(cwd=git_cwd),
                dirty_tree_digest=dirty.digest,
                dirty_tree_algorithm=dirty.algorithm,
            ),
            provenance=provenance,
            error=str(exc),
        )
        write_result_document(
            document=document,
            result_out=result_out,
            result_format=result_format,
            report=None,
        )
        raise

    document = build_result_document(
        status=ResultStatus.completed,
        report=report,
        pass_threshold=config.pass_threshold,
        harness_family=config.harness_agent,
        observed=ObservedGit(
            commit_before=commit_before,
            commit_after=read_head_commit(cwd=git_cwd),
            dirty_tree_digest=dirty.digest,
            dirty_tree_algorithm=dirty.algorithm,
        ),
        provenance=provenance,
        error=None,
    )
    write_result_document(
        document=document,
        result_out=result_out,
        result_format=result_format,
        report=report,
    )
    raise SystemExit(0 if report.run_passed else 1)


@main.command(name="list")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option(
    "--tag", "tags", multiple=True, help="Filter checks by tag (repeatable, OR logic)"
)
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def list_checks(
    check_dir: Path | None, tags: tuple[str, ...], cwd: str, verbose: bool
) -> None:
    _configure_logging(verbose=verbose)
    try:
        config = load_config(cwd=cwd)
        explicit_check_dir = check_dir
        if explicit_check_dir is not None and config.project_root is not None:
            if not explicit_check_dir.is_absolute():
                explicit_check_dir = (
                    config.project_root / explicit_check_dir
                ).resolve()
        paths = discover_check_files(
            start_dir=config.project_root or Path(cwd).resolve(),
            explicit_check_dir=explicit_check_dir,
            exclude_dirs=config.discovery_exclude_dirs,
        )
        loaded = load_check_definitions(paths=paths)
        if tags:
            requested_tags = set(tags)
            loaded = [
                (source_path, check)
                for source_path, check in loaded
                if requested_tags.intersection(check.tags)
            ]
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    for source_path, check in loaded:
        click.echo(f"{check.id}\t{check.type}\t{check.description}\t{source_path}")


@main.command(name="validate")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option(
    "--harness-agent",
    help=(
        "Agent template used to validate harness_judge checks. This only "
        "validates configuration; no agent is executed."
    ),
)
@click.option(
    "--no-project-config",
    is_flag=True,
    help="Do not discover or load .eval-banana/config.toml.",
)
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def validate_checks(
    check_dir: Path | None,
    harness_agent: str | None,
    no_project_config: bool,
    cwd: str,
    verbose: bool,
) -> None:
    """Validate check definitions and harness configuration without executing them."""

    _configure_logging(verbose=verbose)
    try:
        config = load_config(
            cwd=cwd,
            harness_agent=harness_agent,
            use_project_config=not no_project_config,
        )
        explicit_check_dir = check_dir
        if explicit_check_dir is not None and config.project_root is not None:
            if not explicit_check_dir.is_absolute():
                explicit_check_dir = (
                    config.project_root / explicit_check_dir
                ).resolve()
        paths = discover_check_files(
            start_dir=config.project_root or Path(cwd).resolve(),
            explicit_check_dir=explicit_check_dir,
            exclude_dirs=config.discovery_exclude_dirs,
        )
        loaded = load_check_definitions(paths=paths)
        require_harness_for_harness_judge(config=config, selected_checks=loaded)
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(f"Validated {len(loaded)} checks successfully.")
