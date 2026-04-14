from __future__ import annotations

import logging
from pathlib import Path
import shutil

import yaml

logger = logging.getLogger(__name__)

AGENT_SKILL_TARGETS: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".codex/skills",
}


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


def _ensure_no_source_symlinks(*, source_dir: Path) -> None:
    for path in [source_dir, *source_dir.rglob("*")]:
        if path.is_symlink():
            msg = f"Source skill directory contains symlink: {path}"
            raise SystemExit(msg)


def _copy_skill_directory(*, source_dir: Path, target_dir: Path) -> None:
    if target_dir.is_symlink():
        msg = f"Refusing to replace symlinked skill target: {target_dir}"
        raise SystemExit(msg)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    _ensure_no_source_symlinks(source_dir=source_dir)
    shutil.copytree(source_dir, target_dir, symlinks=False)


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


def distribute_skills(
    *, project_root: Path, agent_type: str, skills_dir: Path | None = None
) -> list[str]:
    """Distribute skill packages to agent-specific directories."""
    if skills_dir is None:
        logger.debug("No skills directory configured; skipping skill distribution")
        return []
    if not skills_dir.is_dir():
        logger.info("No skills directory found at %s; skipping", skills_dir)
        return []

    target_root_relative = AGENT_SKILL_TARGETS.get(agent_type)
    if target_root_relative is None:
        logger.debug("Agent type %s has no skill target; skipping", agent_type)
        return []

    target_root = project_root / target_root_relative
    target_root.mkdir(parents=True, exist_ok=True)

    distributed: list[str] = []
    for source_dir in sorted(skills_dir.iterdir()):
        if not source_dir.is_dir():
            continue

        skill_md_path = source_dir / "SKILL.md"
        if not skill_md_path.is_file():
            msg = f"Missing SKILL.md in skill directory: {source_dir}"
            raise SystemExit(msg)
        name, description = _parse_skill_frontmatter(skill_md_path=skill_md_path)
        if name != source_dir.name:
            msg = (
                f"Skill name '{name}' in SKILL.md does not match directory name "
                f"'{source_dir.name}'"
            )
            raise SystemExit(msg)

        target_dir = target_root / source_dir.name
        _copy_skill_directory(source_dir=source_dir, target_dir=target_dir)
        if agent_type == "codex":
            _ensure_codex_metadata(
                target_dir=target_dir, name=name, description=description
            )
        distributed.append(source_dir.name)

    return distributed
