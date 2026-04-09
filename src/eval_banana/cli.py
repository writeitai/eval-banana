from __future__ import annotations

import logging
from pathlib import Path

import click

from eval_banana.config import get_global_config_template
from eval_banana.config import get_local_config_template
from eval_banana.config import load_config
from eval_banana.discovery import discover_check_files
from eval_banana.loader import load_check_definitions
from eval_banana.runner import run_checks

logger = logging.getLogger(__name__)

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
@click.option("--global", "use_global", is_flag=True)
@click.option("--force", is_flag=True)
def init(use_global: bool, force: bool) -> None:
    if use_global:
        config_path = Path.home() / ".eval-banana" / "config.toml"
        config_text = get_global_config_template()
    else:
        config_path = Path.cwd() / ".eval-banana" / "config.toml"
        config_text = get_local_config_template()

    if config_path.exists() and not force:
        raise click.ClickException(
            f"Refusing to overwrite existing file: {config_path}"
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    click.echo(f"Wrote {config_path}")

    if use_global:
        return

    checks_dir = Path.cwd() / "eval_checks"
    checks_dir.mkdir(parents=True, exist_ok=True)
    example_check_path = checks_dir / "example_check.yaml"
    if not example_check_path.exists() or force:
        example_check_path.write_text(_EXAMPLE_CHECK_TEXT, encoding="utf-8")
        click.echo(f"Wrote {example_check_path}")


@main.command(name="run")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option("--check-id")
@click.option("--output-dir")
@click.option("--provider")
@click.option("--model")
@click.option("--api-base")
@click.option("--api-key")
@click.option("--codex-auth-path")
@click.option("--pass-threshold", type=float)
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def run_cli(
    check_dir: Path | None,
    check_id: str | None,
    output_dir: str | None,
    provider: str | None,
    model: str | None,
    api_base: str | None,
    api_key: str | None,
    codex_auth_path: str | None,
    pass_threshold: float | None,
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
        cwd=cwd,
    )
    report = run_checks(config=config, check_dir=check_dir, check_id=check_id)
    raise SystemExit(0 if report.run_passed else 1)


@main.command(name="list")
@click.option("--check-dir", type=click.Path(path_type=Path))
@click.option("--cwd", default=".")
@click.option("--verbose", is_flag=True)
def list_checks(check_dir: Path | None, cwd: str, verbose: bool) -> None:
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
    except (SystemExit, ValueError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    click.echo(f"Validated {len(loaded)} checks successfully.")
