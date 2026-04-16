from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import importlib.metadata
import importlib.resources
from importlib.resources.abc import Traversable
import logging
import os
from pathlib import Path
import shutil
import uuid

import yaml

logger = logging.getLogger(__name__)

AGENT_SKILL_TARGETS: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "openhands": ".agents/skills",
    "opencode": ".agents/skills",
    "gemini": ".gemini/skills",
}
BUNDLED_SKILLS_PACKAGE = "eval_banana.skills"
OWNERSHIP_MARKER = ".eval-banana-installed"


@dataclass
class InstallReport:
    installed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _parse_skill_frontmatter(*, skill_md_path: Path) -> tuple[str, str]:
    text = skill_md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        msg = f"SKILL.md must start with '---' frontmatter delimiter: {skill_md_path}"
        raise SystemExit(msg)

    first_line = lines[0].lstrip("\ufeff").rstrip()
    if first_line != "---":
        msg = f"SKILL.md must start with '---' frontmatter delimiter: {skill_md_path}"
        raise SystemExit(msg)

    frontmatter_lines: list[str] = []
    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            closing_index = index
            break
        frontmatter_lines.append(line)

    if closing_index is None:
        msg = f"No closing '---' frontmatter delimiter found in: {skill_md_path}"
        raise SystemExit(msg)

    frontmatter_text = "\n".join(frontmatter_lines)
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML frontmatter in: {skill_md_path}: {exc}"
        raise SystemExit(msg) from exc

    if not isinstance(frontmatter, dict):
        msg = f"Frontmatter is not a YAML mapping in: {skill_md_path}"
        raise SystemExit(msg)

    name = frontmatter.get("name")
    if name is None:
        msg = f"Missing required 'name' in frontmatter: {skill_md_path}"
        raise SystemExit(msg)
    if not isinstance(name, str):
        msg = f"'name' must be a string in frontmatter: {skill_md_path}"
        raise SystemExit(msg)

    description = frontmatter.get("description")
    if description is None:
        msg = f"Missing required 'description' in frontmatter: {skill_md_path}"
        raise SystemExit(msg)
    if not isinstance(description, str):
        msg = f"'description' must be a string in frontmatter: {skill_md_path}"
        raise SystemExit(msg)

    return name, description


def _build_codex_openai_yaml(*, name: str, description: str) -> str:
    payload = {
        "interface": {
            "display_name": name,
            "short_description": description,
            "default_prompt": f"Use ${name} when the task requires this skill.",
        }
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _ensure_codex_metadata(*, target_dir: Path, name: str, description: str) -> None:
    openai_yaml_path = target_dir / "agents" / "openai.yaml"
    if openai_yaml_path.is_file():
        return
    openai_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    openai_yaml_path.write_text(
        _build_codex_openai_yaml(name=name, description=description), encoding="utf-8"
    )


def _bundled_skills_root() -> Traversable:
    package_name, resource_name = BUNDLED_SKILLS_PACKAGE.rsplit(".", maxsplit=1)
    return importlib.resources.files(package_name).joinpath(resource_name)


def discover_bundled_skills() -> list[str]:
    return sorted(
        child.name for child in _bundled_skills_root().iterdir() if child.is_dir()
    )


def _dedupe_values(*, values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _resolve_target_roots(
    *, project_root: Path, agent_types: list[str]
) -> list[tuple[str, Path]]:
    unique_roots: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for agent_type in _dedupe_values(values=agent_types):
        target_root_relative = AGENT_SKILL_TARGETS.get(agent_type)
        if target_root_relative is None:
            msg = f"Unsupported agent type: {agent_type}"
            raise ValueError(msg)
        if target_root_relative in seen:
            continue
        seen.add(target_root_relative)
        unique_roots.append((target_root_relative, project_root / target_root_relative))
    return unique_roots


def _ensure_target_root(*, target_root: Path) -> None:
    if target_root.is_symlink():
        msg = f"Refusing to install into symlinked skill target root: {target_root}"
        raise SystemExit(msg)
    if target_root.exists() and not target_root.is_dir():
        msg = f"Skill target root exists and is not a directory: {target_root}"
        raise SystemExit(msg)
    target_root.mkdir(parents=True, exist_ok=True)


def _validate_skill_directory(*, source_dir: Path, skill_name: str) -> tuple[str, str]:
    skill_md_path = source_dir / "SKILL.md"
    if not skill_md_path.is_file():
        msg = f"Missing SKILL.md in skill directory: {source_dir}"
        raise SystemExit(msg)

    name, description = _parse_skill_frontmatter(skill_md_path=skill_md_path)
    if name != skill_name:
        msg = (
            f"Skill name '{name}' in SKILL.md does not match directory name "
            f"'{skill_name}'"
        )
        raise SystemExit(msg)
    return name, description


def _is_eval_banana_owned(*, target_dir: Path) -> bool:
    return (target_dir / OWNERSHIP_MARKER).exists()


def _should_overwrite_existing_target(*, target_dir: Path, force: bool) -> bool:
    if target_dir.is_symlink():
        msg = f"Refusing to replace symlinked skill target: {target_dir}"
        raise SystemExit(msg)
    if target_dir.exists() and not target_dir.is_dir():
        msg = f"Skill target exists and is not a directory: {target_dir}"
        raise SystemExit(msg)
    if not target_dir.exists():
        return False
    if force or _is_eval_banana_owned(target_dir=target_dir):
        return True
    msg = (
        "target exists and was not installed by eval-banana: "
        f"{target_dir}. Move/remove it, or pass --force to overwrite."
    )
    raise SystemExit(msg)


def _make_staging_dir(*, target_root: Path, skill_name: str) -> Path:
    return target_root / f".eval-banana-staging-{skill_name}-{uuid.uuid4().hex}"


def _format_report_item(*, skill_name: str, target_dir: Path) -> str:
    return f"{skill_name} -> {target_dir}"


def _bundled_skill_resource(*, skill_name: str) -> Traversable:
    return importlib.resources.files("eval_banana").joinpath("skills", skill_name)


def install_bundled_skills(
    *,
    project_root: Path,
    agent_types: list[str],
    skill_names: list[str],
    force: bool,
    dry_run: bool,
) -> InstallReport:
    available_skills = set(discover_bundled_skills())
    selected_skills = _dedupe_values(values=skill_names)
    unknown_skills = sorted(
        skill_name
        for skill_name in selected_skills
        if skill_name not in available_skills
    )
    if unknown_skills:
        msg = f"Unknown bundled skills: {', '.join(unknown_skills)}"
        raise ValueError(msg)

    target_roots = _resolve_target_roots(
        project_root=project_root, agent_types=agent_types
    )
    report = InstallReport()
    eval_banana_version = importlib.metadata.version("eval-banana")

    for skill_name in selected_skills:
        skill_resource = _bundled_skill_resource(skill_name=skill_name)
        for target_root_relative, target_root in target_roots:
            target_dir = target_root / skill_name
            report_item = _format_report_item(
                skill_name=skill_name, target_dir=target_dir
            )
            try:
                if dry_run:
                    if target_root.is_symlink():
                        msg = (
                            "Refusing to install into symlinked skill target root: "
                            f"{target_root}"
                        )
                        raise SystemExit(msg)
                    if target_root.exists() and not target_root.is_dir():
                        msg = (
                            "Skill target root exists and is not a directory: "
                            f"{target_root}"
                        )
                        raise SystemExit(msg)
                else:
                    _ensure_target_root(target_root=target_root)
                with importlib.resources.as_file(skill_resource) as source_dir:
                    if not source_dir.is_dir():
                        msg = f"Missing bundled skill directory: {skill_name}"
                        raise SystemExit(msg)
                    name, description = _validate_skill_directory(
                        source_dir=source_dir, skill_name=skill_name
                    )
                    overwrite_existing = _should_overwrite_existing_target(
                        target_dir=target_dir, force=force
                    )

                    if dry_run:
                        if overwrite_existing:
                            print(f"Would overwrite existing: {target_dir}")
                        else:
                            print(f"Would install {skill_name} -> {target_dir}")
                        report.skipped.append(report_item)
                        continue

                    if overwrite_existing:
                        print(f"Overwriting existing: {target_dir}")
                    print(f"Installing {skill_name} -> {target_dir}")

                    staging_dir = _make_staging_dir(
                        target_root=target_root, skill_name=skill_name
                    )
                    backup_dir = (
                        target_dir.parent
                        / f".eval-banana-backup-{target_dir.name}-{os.getpid()}"
                    )
                    try:
                        shutil.copytree(source_dir, staging_dir, symlinks=False)
                        if target_root_relative == AGENT_SKILL_TARGETS["codex"]:
                            _ensure_codex_metadata(
                                target_dir=staging_dir,
                                name=name,
                                description=description,
                            )
                        marker_path = staging_dir / OWNERSHIP_MARKER
                        marker_path.write_text(
                            (
                                f"skill={skill_name} "
                                f"eval_banana_version={eval_banana_version}\n"
                            ),
                            encoding="utf-8",
                        )
                        if target_dir.exists():
                            os.replace(target_dir, backup_dir)
                        if target_dir.exists():
                            msg = f"Failed to move existing target to backup: {target_dir}"
                            raise RuntimeError(msg)
                        try:
                            os.replace(staging_dir, target_dir)
                        except Exception:
                            if backup_dir.exists():
                                os.replace(backup_dir, target_dir)
                            raise
                        if backup_dir.exists():
                            shutil.rmtree(backup_dir, ignore_errors=True)
                    except Exception:
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        shutil.rmtree(backup_dir, ignore_errors=True)
                        raise

                    report.installed.append(report_item)
            except (Exception, SystemExit) as exc:
                failure = f"{report_item}: {exc}"
                print(f"Failed: {failure}")
                report.failed.append(failure)

    return report
