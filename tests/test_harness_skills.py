from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import importlib.metadata
import os
from pathlib import Path

import pytest
import yaml

from eval_banana.harness.skills import _build_codex_agent_metadata_yaml
from eval_banana.harness.skills import _parse_skill_frontmatter
from eval_banana.harness.skills import AGENT_SKILL_TARGETS
from eval_banana.harness.skills import discover_bundled_skills
from eval_banana.harness.skills import install_bundled_skills
from eval_banana.harness.skills import OWNERSHIP_MARKER


def _write_skill_source(
    *,
    root_dir: Path,
    dir_name: str = "gemini_media_use",
    frontmatter_name: str = "gemini_media_use",
    description: str = "Use Gemini media APIs.",
    body: str = "# Skill body\n",
    include_openai_yaml: bool = False,
) -> Path:
    skill_dir = root_dir / dir_name
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
            "interface:\n  display_name: packaged\n", encoding="utf-8"
        )
    return skill_dir


def _patch_bundled_sources(
    *, monkeypatch: pytest.MonkeyPatch, skill_sources: dict[str, Path]
) -> None:
    monkeypatch.setattr(
        "eval_banana.harness.skills.discover_bundled_skills",
        lambda: sorted(skill_sources),
    )
    monkeypatch.setattr(
        "eval_banana.harness.skills._bundled_skill_resource",
        lambda *, skill_name: skill_sources[skill_name],
    )

    @contextmanager
    def _fake_as_file(resource: object) -> Iterator[Path]:
        if not isinstance(resource, Path):
            msg = f"Expected Path resource, got {type(resource)!r}"
            raise AssertionError(msg)
        yield resource

    monkeypatch.setattr(
        "eval_banana.harness.skills.importlib.resources.as_file", _fake_as_file
    )


def test_discover_bundled_skills_lists_packaged_directories() -> None:
    assert discover_bundled_skills() == ["eval-banana", "gemini_media_use"]


def test_install_bundled_skills_dedupes_shared_agent_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["openhands", "opencode", "codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    agents_target = tmp_path / ".agents" / "skills" / "gemini_media_use"
    codex_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    marker_text = (codex_target / OWNERSHIP_MARKER).read_text(encoding="utf-8")

    assert report.installed == [
        f"gemini_media_use -> {agents_target}",
        f"gemini_media_use -> {codex_target}",
    ]
    assert report.failed == []
    assert agents_target.is_dir()
    assert codex_target.is_dir()
    assert (codex_target / "agents" / "openai.yaml").is_file()
    assert "eval_banana_version=" in marker_text
    assert capsys.readouterr().out.count("Installing gemini_media_use ->") == 2


def test_install_bundled_skills_dry_run_reports_skipped_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude", "codex"],
        skill_names=["eval-banana"],
        force=False,
        dry_run=True,
    )

    assert report.installed == []
    assert report.failed == []
    assert len(report.skipped) == 2
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()
    assert "Would install eval-banana ->" in capsys.readouterr().out


def test_install_bundled_skills_overwrites_owned_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )
    target_dir = tmp_path / ".claude" / "skills" / "gemini_media_use"
    (target_dir / "stale.txt").write_text("old\n", encoding="utf-8")

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )
    output = capsys.readouterr().out

    assert report.failed == []
    assert report.installed == [f"gemini_media_use -> {target_dir}"]
    assert not (target_dir / "stale.txt").exists()
    assert f"Overwriting existing: {target_dir}" in output
    assert f"Installing gemini_media_use -> {target_dir}" in output


def test_install_bundled_skills_requires_force_for_non_owned_directory_and_continues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claude_target = tmp_path / ".claude" / "skills" / "gemini_media_use"
    claude_target.mkdir(parents=True)
    (claude_target / "custom.txt").write_text("keep\n", encoding="utf-8")

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude", "codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    codex_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    failure_output = capsys.readouterr().err

    assert report.installed == [f"gemini_media_use -> {codex_target}"]
    assert len(report.failed) == 1
    assert "target exists and was not installed by eval-banana" in report.failed[0]
    assert (claude_target / "custom.txt").read_text(encoding="utf-8") == "keep\n"
    assert codex_target.is_dir()
    assert "Failed:" in failure_output


def test_install_bundled_skills_force_overwrites_non_owned_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target_dir = tmp_path / ".claude" / "skills" / "gemini_media_use"
    target_dir.mkdir(parents=True)
    (target_dir / "custom.txt").write_text("old\n", encoding="utf-8")

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=True,
        dry_run=False,
    )
    output = capsys.readouterr().out

    assert report.failed == []
    assert report.installed == [f"gemini_media_use -> {target_dir}"]
    assert not (target_dir / "custom.txt").exists()
    assert f"Overwriting existing: {target_dir}" in output
    assert f"Installing gemini_media_use -> {target_dir}" in output


def test_install_bundled_skills_rejects_file_target_and_continues(
    tmp_path: Path,
) -> None:
    file_target = tmp_path / ".claude" / "skills" / "gemini_media_use"
    file_target.parent.mkdir(parents=True)
    file_target.write_text("not a directory\n", encoding="utf-8")

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude", "codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    codex_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    assert report.installed == [f"gemini_media_use -> {codex_target}"]
    assert len(report.failed) == 1
    assert "Skill target exists and is not a directory" in report.failed[0]
    assert codex_target.is_dir()


def test_install_bundled_skills_rejects_symlink_target_and_continues(
    tmp_path: Path,
) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink_target = tmp_path / ".claude" / "skills" / "gemini_media_use"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.symlink_to(real_dir, target_is_directory=True)

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude", "codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    codex_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    assert report.installed == [f"gemini_media_use -> {codex_target}"]
    assert len(report.failed) == 1
    assert "Refusing to replace symlinked skill target" in report.failed[0]
    assert codex_target.is_dir()


def test_install_bundled_skills_force_does_not_bypass_file_target_rejection(
    tmp_path: Path,
) -> None:
    file_target = tmp_path / ".claude" / "skills" / "gemini_media_use"
    file_target.parent.mkdir(parents=True)
    file_target.write_text("not a directory\n", encoding="utf-8")

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=True,
        dry_run=False,
    )

    assert report.installed == []
    assert len(report.failed) == 1
    assert "Skill target exists and is not a directory" in report.failed[0]
    assert file_target.is_file()
    assert file_target.read_text(encoding="utf-8") == "not a directory\n"


def test_install_bundled_skills_force_does_not_bypass_symlink_target_rejection(
    tmp_path: Path,
) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink_target = tmp_path / ".claude" / "skills" / "gemini_media_use"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.symlink_to(real_dir, target_is_directory=True)

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=True,
        dry_run=False,
    )

    assert report.installed == []
    assert len(report.failed) == 1
    assert "Refusing to replace symlinked skill target" in report.failed[0]
    assert symlink_target.is_symlink()


def test_install_bundled_skills_leaves_existing_target_untouched_when_staging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_bundled_skills(
        project_root=tmp_path,
        agent_types=["codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )
    target_dir = tmp_path / ".codex" / "skills" / "gemini_media_use"
    sentinel_path = target_dir / "sentinel.txt"
    sentinel_path.write_text("keep\n", encoding="utf-8")

    monkeypatch.setattr(
        "eval_banana.harness.skills._ensure_codex_metadata",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("metadata failed")),
    )

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    assert report.installed == []
    assert len(report.failed) == 1
    assert sentinel_path.read_text(encoding="utf-8") == "keep\n"
    assert list((tmp_path / ".codex" / "skills").glob(".eval-banana-staging-*")) == []


def test_install_bundled_skills_restores_existing_target_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )
    target_dir = tmp_path / ".claude" / "skills" / "gemini_media_use"
    sentinel_path = target_dir / "sentinel.txt"
    sentinel_path.write_text("keep\n", encoding="utf-8")
    original_replace = os.replace
    call_count = 0

    def flaky_replace(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("swap failed")
        original_replace(src, dst)

    monkeypatch.setattr("eval_banana.harness.skills.os.replace", flaky_replace)

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    assert report.installed == []
    assert len(report.failed) == 1
    assert "swap failed" in report.failed[0]
    assert sentinel_path.read_text(encoding="utf-8") == "keep\n"
    assert (target_dir / OWNERSHIP_MARKER).is_file()
    assert list((tmp_path / ".claude" / "skills").glob(".eval-banana-staging-*")) == []
    assert list((tmp_path / ".claude" / "skills").glob(".eval-banana-backup-*")) == []


def test_install_bundled_skills_reports_parent_permission_error_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_ensure_target_root = __import__(
        "eval_banana.harness.skills", fromlist=["_ensure_target_root"]
    )._ensure_target_root

    def fake_ensure_target_root(*, target_root: Path) -> None:
        if target_root == tmp_path / ".claude" / "skills":
            raise PermissionError("Permission denied")
        original_ensure_target_root(target_root=target_root)

    monkeypatch.setattr(
        "eval_banana.harness.skills._ensure_target_root", fake_ensure_target_root
    )

    report = install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude", "codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    codex_target = tmp_path / ".codex" / "skills" / "gemini_media_use"
    assert report.installed == [f"gemini_media_use -> {codex_target}"]
    assert len(report.failed) == 1
    assert "Permission denied" in report.failed[0]


def test_install_bundled_skills_preserves_packaged_openai_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "sources"
    skill_dir = _write_skill_source(root_dir=source_root, include_openai_yaml=True)
    _patch_bundled_sources(
        monkeypatch=monkeypatch, skill_sources={"gemini_media_use": skill_dir}
    )

    report = install_bundled_skills(
        project_root=tmp_path / "project",
        agent_types=["codex"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    openai_yaml_path = (
        tmp_path
        / "project"
        / AGENT_SKILL_TARGETS["codex"]
        / "gemini_media_use"
        / "agents"
        / "openai.yaml"
    )

    assert report.failed == []
    assert openai_yaml_path.read_text(encoding="utf-8") == (
        "interface:\n  display_name: packaged\n"
    )


def test_install_bundled_skills_invalid_packaged_skill_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "sources"
    invalid_skill_dir = source_root / "gemini_media_use"
    invalid_skill_dir.mkdir(parents=True)
    _patch_bundled_sources(
        monkeypatch=monkeypatch, skill_sources={"gemini_media_use": invalid_skill_dir}
    )

    report = install_bundled_skills(
        project_root=tmp_path / "project",
        agent_types=["claude"],
        skill_names=["gemini_media_use"],
        force=False,
        dry_run=False,
    )

    assert report.installed == []
    assert len(report.failed) == 1
    assert "Missing SKILL.md" in report.failed[0]


def test_parse_skill_frontmatter_requires_frontmatter_delimiters(
    tmp_path: Path,
) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_text("name: gemini_media_use\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must start with '---' frontmatter delimiter"):
        _parse_skill_frontmatter(skill_md_path=skill_md_path)


def test_parse_skill_frontmatter_allows_bom_and_crlf(tmp_path: Path) -> None:
    skill_md_path = tmp_path / "SKILL.md"
    skill_md_path.write_bytes(
        b"\xef\xbb\xbf---\r\nname: gemini_media_use\r\ndescription: desc\r\n---\r\n"
    )

    assert _parse_skill_frontmatter(skill_md_path=skill_md_path) == (
        "gemini_media_use",
        "desc",
    )


def test_build_codex_agent_metadata_yaml() -> None:
    payload = yaml.safe_load(
        _build_codex_agent_metadata_yaml(
            name="gemini_media_use", description="Use Gemini media APIs."
        )
    )

    assert payload == {
        "interface": {
            "display_name": "gemini_media_use",
            "short_description": "Use Gemini media APIs.",
            "default_prompt": (
                "Use $gemini_media_use when the task requires this skill."
            ),
        }
    }


def test_install_bundled_skills_marker_contains_package_version(tmp_path: Path) -> None:
    install_bundled_skills(
        project_root=tmp_path,
        agent_types=["claude"],
        skill_names=["eval-banana"],
        force=False,
        dry_run=False,
    )

    marker_path = tmp_path / ".claude" / "skills" / "eval-banana" / OWNERSHIP_MARKER
    expected_version = importlib.metadata.version("eval-banana")

    assert marker_path.read_text(encoding="utf-8") == (
        f"skill=eval-banana eval_banana_version={expected_version}\n"
    )
