from __future__ import annotations

import logging
from pathlib import Path

import click

from eval_banana.config import get_local_config_template
from eval_banana.config import load_config
from eval_banana.discovery import discover_check_files
from eval_banana.harness.skills import AGENT_SKILL_TARGETS
from eval_banana.harness.skills import discover_bundled_skills
from eval_banana.harness.skills import install_bundled_skills
from eval_banana.loader import load_check_definitions
from eval_banana.runner import require_harness_for_llm_judge
from eval_banana.runner import run_checks

logger = logging.getLogger(__name__)
_BUNDLED_SKILL_CHOICES = discover_bundled_skills()

_EXAMPLE_CHECK_TEXT = """schema_version: 1
id: example_check
type: deterministic
description: Example check -- verifies that a README file exists.
target_paths:
  - README.md
script: |
  import json
  import sys
  from pathlib import Path

  context = json.loads(Path(sys.argv[1]).read_text())
  for item in context["targets"]:
      p = Path(item["resolved_path"])
      if not p.exists():
          print(f"Missing: {item['path']}", file=sys.stderr)
          sys.exit(1)
  print("All target files exist.")
"""


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

    checks_dir = Path.cwd() / "eval_checks"
    checks_dir.mkdir(parents=True, exist_ok=True)
    example_check_path = checks_dir / "example_check.yaml"
    if not example_check_path.exists() or force:
        example_check_path.write_text(_EXAMPLE_CHECK_TEXT, encoding="utf-8")
        click.echo(f"Wrote {example_check_path}")


@main.command(name="run")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option("--check-id")
@click.option(
    "--tag", "tags", multiple=True, help="Filter checks by tag (repeatable, OR logic)"
)
@click.option("--output-dir")
@click.option("--provider")
@click.option("--model")
@click.option("--api-base")
@click.option("--api-key")
@click.option("--codex-auth-path")
@click.option("--pass-threshold", type=float)
@click.option("--harness-agent")
@click.option("--harness-prompt")
@click.option("--harness-prompt-file", type=click.Path(path_type=Path))
@click.option("--harness-model")
@click.option("--harness-reasoning-effort")
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def run_cli(
    check_dir: Path | None,
    check_id: str | None,
    tags: tuple[str, ...],
    output_dir: str | None,
    provider: str | None,
    model: str | None,
    api_base: str | None,
    api_key: str | None,
    codex_auth_path: str | None,
    pass_threshold: float | None,
    harness_agent: str | None,
    harness_prompt: str | None,
    harness_prompt_file: Path | None,
    harness_model: str | None,
    harness_reasoning_effort: str | None,
    cwd: str,
    verbose: bool,
) -> None:
    _configure_logging(verbose=verbose)
    config = load_config(
        output_dir=output_dir,
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        codex_auth_path=codex_auth_path,
        pass_threshold=pass_threshold,
        harness_agent=harness_agent,
        harness_prompt=harness_prompt,
        harness_prompt_file=(
            str(harness_prompt_file) if harness_prompt_file is not None else None
        ),
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
        require_harness_for_llm_judge(config=config, selected_checks=loaded)
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(f"Validated {len(loaded)} checks successfully.")


def _run_install_command(
    *,
    target_agents: tuple[str, ...],
    skills: tuple[str, ...],
    cwd: str,
    verbose: bool,
    dry_run: bool,
    force: bool,
) -> None:
    _configure_logging(verbose=verbose)
    try:
        config = load_config(cwd=cwd)
        project_root = config.project_root or Path(cwd).resolve()
        agents = list(target_agents) if target_agents else sorted(AGENT_SKILL_TARGETS)
        selected_skills = list(skills) if skills else list(_BUNDLED_SKILL_CHOICES)
        report = install_bundled_skills(
            project_root=project_root,
            agent_types=agents,
            skill_names=selected_skills,
            force=force,
            dry_run=dry_run,
        )
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(
        "Summary: "
        f"installed={len(report.installed)} "
        f"skipped={len(report.skipped)} "
        f"failed={len(report.failed)}"
    )
    if report.failed:
        raise SystemExit(1)


@main.command(
    name="install",
    help=(
        "Install bundled eval-banana agent skills into a project's native agent "
        "skill directories."
    ),
)
@click.option(
    "--target-agents",
    multiple=True,
    type=click.Choice(sorted(AGENT_SKILL_TARGETS)),
    help=(
        "Repeatable. Limit installation to specific agent targets. Default: all "
        "agent names in AGENT_SKILL_TARGETS. Note: install work is deduped by "
        "unique destination directory."
    ),
)
@click.option(
    "--skills",
    multiple=True,
    type=click.Choice(_BUNDLED_SKILL_CHOICES),
    help=(
        "Repeatable. Limit installation to specific bundled skills. Default: all "
        "bundled skills discovered from package resources."
    ),
)
@click.option(
    "--cwd",
    default=".",
    help=(
        "Target project directory. Uses load_config(cwd=PATH) project-root "
        "resolution: if .eval-banana/config.toml is found upward, use that "
        "project root; otherwise use PATH itself."
    ),
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned installs without writing files."
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing unmarked target directories. Does not replace files or symlinks.",
)
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def install_skills_cli(
    target_agents: tuple[str, ...],
    skills: tuple[str, ...],
    cwd: str,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    _run_install_command(
        target_agents=target_agents,
        skills=skills,
        cwd=cwd,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )


@main.command(name="distribute-skills", help="Deprecated alias for 'install'.")
@click.option(
    "--target-agents",
    multiple=True,
    type=click.Choice(sorted(AGENT_SKILL_TARGETS)),
    help=(
        "Repeatable. Limit installation to specific agent targets. Default: all "
        "agent names in AGENT_SKILL_TARGETS. Note: install work is deduped by "
        "unique destination directory."
    ),
)
@click.option(
    "--skills",
    multiple=True,
    type=click.Choice(_BUNDLED_SKILL_CHOICES),
    help=(
        "Repeatable. Limit installation to specific bundled skills. Default: all "
        "bundled skills discovered from package resources."
    ),
)
@click.option(
    "--cwd",
    default=".",
    help=(
        "Target project directory. Uses load_config(cwd=PATH) project-root "
        "resolution: if .eval-banana/config.toml is found upward, use that "
        "project root; otherwise use PATH itself."
    ),
)
@click.option(
    "--dry-run", is_flag=True, help="Print the planned installs without writing files."
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing unmarked target directories. Does not replace files or symlinks.",
)
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def distribute_skills_cli(
    target_agents: tuple[str, ...],
    skills: tuple[str, ...],
    cwd: str,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    click.echo(
        "DeprecationWarning: 'distribute-skills' is deprecated; use 'eb install'",
        err=True,
    )
    _run_install_command(
        target_agents=target_agents,
        skills=skills,
        cwd=cwd,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
    )
