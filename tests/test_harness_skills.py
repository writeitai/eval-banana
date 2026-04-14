from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval_banana.harness.skills import _build_codex_openai_yaml
from eval_banana.harness.skills import _parse_skill_frontmatter
from eval_banana.harness.skills import distribute_skills


def _write_skill(
    *,
    skills_dir: Path,
    dir_name: str = "gemini_media_use",
    frontmatter_name: str = "gemini_media_use",
    description: str = "Use Gemini media APIs.",
    body: str = "# Skill body\n",
    include_openai_yaml: bool = False,
) -> Path:
    skill_dir = skills_dir / dir_name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "references").mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {frontmatter_name}",
                f"description: {description}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "upload_media.py").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )
    (skill_dir / "references" / "supported_formats.md").write_text(
        "formats\n", encoding="utf-8"
    )
    if include_openai_yaml:
        (skill_dir / "agents").mkdir()
        (skill_dir / "agents" / "openai.yaml").write_text(
            "interface:\n  display_name: custom\n", encoding="utf-8"
        )
    return skill_dir


def test_distribute_skills_none_skills_dir(tmp_path: Path) -> None:
    assert (
        distribute_skills(project_root=tmp_path, agent_type="claude", skills_dir=None)
        == []
    )


def test_distribute_skills_missing_skills_dir(tmp_path: Path) -> None:
    assert (
        distribute_skills(
            project_root=tmp_path,
            agent_type="claude",
            skills_dir=tmp_path / "missing-skills",
        )
        == []
    )


def test_distribute_skills_unsupported_agent(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)

    assert (
        distribute_skills(
            project_root=tmp_path, agent_type="mystery_agent", skills_dir=skills_dir
        )
        == []
    )


def test_distribute_skills_openhands(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="openhands", skills_dir=skills_dir
    )

    target_dir = tmp_path / ".agents" / "skills" / "gemini_media_use"
    assert distributed == ["gemini_media_use"]
    assert (target_dir / "SKILL.md").is_file()
    assert not (target_dir / "agents" / "openai.yaml").exists()


def test_distribute_skills_opencode(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="opencode", skills_dir=skills_dir
    )

    target_dir = tmp_path / ".agents" / "skills" / "gemini_media_use"
    assert distributed == ["gemini_media_use"]
    assert (target_dir / "SKILL.md").is_file()
    assert not (target_dir / "agents" / "openai.yaml").exists()


def test_distribute_skills_gemini(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="gemini", skills_dir=skills_dir
    )

    target_dir = tmp_path / ".gemini" / "skills" / "gemini_media_use"
    assert distributed == ["gemini_media_use"]
    assert (target_dir / "SKILL.md").is_file()
    assert not (target_dir / "agents" / "openai.yaml").exists()


def test_distribute_skills_claude(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
    )

    target_dir = tmp_path / ".claude" / "skills" / "gemini_media_use"
    assert distributed == ["gemini_media_use"]
    assert (target_dir / "SKILL.md").is_file()
    assert (target_dir / "scripts" / "upload_media.py").is_file()
    assert (target_dir / "references" / "supported_formats.md").is_file()
    assert not (target_dir / "agents" / "openai.yaml").exists()


def test_distribute_skills_codex_generates_openai_yaml(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir=skills_dir,
        description="Use Gemini media APIs to upload and analyze files.",
    )

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="codex", skills_dir=skills_dir
    )

    openai_yaml_path = (
        tmp_path / ".codex" / "skills" / "gemini_media_use" / "agents" / "openai.yaml"
    )
    payload = yaml.safe_load(openai_yaml_path.read_text(encoding="utf-8"))

    assert distributed == ["gemini_media_use"]
    assert payload["interface"]["display_name"] == "gemini_media_use"
    assert (
        payload["interface"]["short_description"]
        == "Use Gemini media APIs to upload and analyze files."
    )


def test_distribute_skills_codex_preserves_openai_yaml(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir, include_openai_yaml=True)

    distribute_skills(project_root=tmp_path, agent_type="codex", skills_dir=skills_dir)

    openai_yaml_path = (
        tmp_path / ".codex" / "skills" / "gemini_media_use" / "agents" / "openai.yaml"
    )
    assert openai_yaml_path.read_text(encoding="utf-8") == (
        "interface:\n  display_name: custom\n"
    )


def test_distribute_skills_malformed_frontmatter_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "gemini_media_use"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: [broken\ndescription: ok\n---\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="Invalid YAML frontmatter"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_missing_skill_md_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    (skills_dir / "gemini_media_use").mkdir(parents=True)

    with pytest.raises(SystemExit, match="Missing SKILL.md"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_replaces_existing_target(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)
    target_dir = tmp_path / ".claude" / "skills" / "gemini_media_use"
    target_dir.mkdir(parents=True)
    (target_dir / "stale.txt").write_text("old\n", encoding="utf-8")

    distribute_skills(project_root=tmp_path, agent_type="claude", skills_dir=skills_dir)

    assert not (target_dir / "stale.txt").exists()
    assert (target_dir / "SKILL.md").is_file()


def test_distribute_skills_skips_non_directory_entries(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / ".gitkeep").write_text("", encoding="utf-8")
    _write_skill(skills_dir=skills_dir)

    distributed = distribute_skills(
        project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
    )

    assert distributed == ["gemini_media_use"]


def test_distribute_skills_name_mismatch_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir=skills_dir,
        dir_name="gemini_media_use",
        frontmatter_name="wrong_name",
    )

    with pytest.raises(SystemExit, match="does not match directory name"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_name_missing_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "gemini_media_use"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: desc\n---\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="Missing required 'name'"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_description_missing_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "gemini_media_use"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: gemini_media_use\n---\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="Missing required 'description'"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_skills_dir_is_file(tmp_path: Path) -> None:
    skills_file = tmp_path / "skills"
    skills_file.write_text("not a directory\n", encoding="utf-8")

    assert (
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_file
        )
        == []
    )


def test_distribute_skills_symlink_target_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    symlink_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.symlink_to(real_target, target_is_directory=True)

    with pytest.raises(SystemExit, match="symlinked skill target"):
        distribute_skills(
            project_root=tmp_path, agent_type="codex", skills_dir=skills_dir
        )


def test_distribute_skills_source_symlink_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)
    real_file = tmp_path / "real_file.txt"
    real_file.write_text("content\n", encoding="utf-8")
    (skills_dir / "gemini_media_use" / "scripts" / "linked.py").symlink_to(real_file)

    with pytest.raises(SystemExit, match="contains symlink"):
        distribute_skills(
            project_root=tmp_path, agent_type="claude", skills_dir=skills_dir
        )


def test_distribute_skills_none_creates_no_directories(tmp_path: Path) -> None:
    distribute_skills(project_root=tmp_path, agent_type="claude", skills_dir=None)
    assert not (tmp_path / ".claude").exists()


def test_distribute_skills_missing_dir_creates_no_directories(tmp_path: Path) -> None:
    distribute_skills(
        project_root=tmp_path,
        agent_type="claude",
        skills_dir=tmp_path / "missing-skills",
    )
    assert not (tmp_path / ".claude").exists()


def test_parse_frontmatter_empty_file(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="must start with '---'"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_distribute_skills_broken_symlink_target_raises(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir=skills_dir)
    symlink_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.symlink_to(tmp_path / "nonexistent", target_is_directory=True)

    with pytest.raises(SystemExit, match="symlinked skill target"):
        distribute_skills(
            project_root=tmp_path, agent_type="codex", skills_dir=skills_dir
        )


def test_parse_frontmatter_no_opening_delimiter(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text("name: gemini_media_use\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must start with '---'"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_no_closing_delimiter(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text(
        "---\nname: gemini_media_use\ndescription: desc\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="No closing '---'"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_empty_block(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text("---\n---\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Frontmatter is not a YAML mapping"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_non_mapping(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text("---\n- one\n- two\n---\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Frontmatter is not a YAML mapping"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_non_string_name(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text(
        "---\nname: 123\ndescription: desc\n---\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="'name' must be a string"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_non_string_description(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text(
        "---\nname: gemini_media_use\ndescription: 123\n---\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="'description' must be a string"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_frontmatter_windows_newlines(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_bytes(
        b"\xef\xbb\xbf---\r\nname: gemini_media_use\r\ndescription: desc\r\n---\r\n"
    )

    assert _parse_skill_frontmatter(skill_md_path=skill_md_path) == (
        "gemini_media_use",
        "desc",
    )


def test_codex_openai_yaml_round_trips(tmp_path: Path) -> None:
    yaml_path = tmp_path / "openai.yaml"
    yaml_path.write_text(
        _build_codex_openai_yaml(
            name="gemini_media_use", description="Use Gemini media APIs."
        ),
        encoding="utf-8",
    )

    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    assert payload == {
        "interface": {
            "display_name": "gemini_media_use",
            "short_description": "Use Gemini media APIs.",
            "default_prompt": (
                "Use $gemini_media_use when the task requires this skill."
            ),
        }
    }
