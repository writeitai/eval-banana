from __future__ import annotations

import logging
from pathlib import Path

import click

from eval_banana.config import get_local_config_template
from eval_banana.config import load_config
from eval_banana.discovery import discover_check_files
from eval_banana.loader import load_check_definitions
from eval_banana.runner import require_harness_for_harness_judge
from eval_banana.runner import run_checks

logger = logging.getLogger(__name__)


def _configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(format="%(name)s: %(message)s", level=level)


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
@click.option("--pass-threshold", type=float)
@click.option("--harness-agent")
@click.option("--harness-model")
@click.option("--harness-reasoning-effort")
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def run_cli(
    check_dir: Path | None,
    check_id: str | None,
    tags: tuple[str, ...],
    output_dir: str | None,
    pass_threshold: float | None,
    harness_agent: str | None,
    harness_model: str | None,
    harness_reasoning_effort: str | None,
    cwd: str,
    verbose: bool,
) -> None:
    _configure_logging(verbose=verbose)
    config = load_config(
        output_dir=output_dir,
        pass_threshold=pass_threshold,
        harness_agent=harness_agent,
        harness_model=harness_model,
        harness_reasoning_effort=harness_reasoning_effort,
        cwd=cwd,
    )
    report = run_checks(
        config=config, check_dir=check_dir, check_id=check_id, tags=list(tags) or None
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
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def validate_checks(check_dir: Path | None, cwd: str, verbose: bool) -> None:
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
        require_harness_for_harness_judge(config=config, selected_checks=loaded)
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(f"Validated {len(loaded)} checks successfully.")
