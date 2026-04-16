from __future__ import annotations

from pathlib import Path
import site
import subprocess
import sys
import zipfile

import pytest
import yaml


def _venv_python(*, venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_eb(*, venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "eb.exe"
    return venv_dir / "bin" / "eb"


@pytest.mark.packaging
def test_wheel_contains_skills_and_installs_them(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    wheel_dir = tmp_path / "dist"
    build_result = subprocess.run(
        args=["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
        check=True,
        capture_output=True,
        cwd=repo_root,
        text=True,
    )

    wheel_paths = sorted(wheel_dir.glob("*.whl"))
    assert build_result.returncode == 0
    assert len(wheel_paths) == 1
    wheel_path = wheel_paths[0]

    with zipfile.ZipFile(file=wheel_path) as wheel_zip:
        wheel_names = set(wheel_zip.namelist())

    assert "eval_banana/skills/eval-banana/SKILL.md" in wheel_names
    assert "eval_banana/skills/gemini_media_use/scripts/upload_media.py" in wheel_names

    venv_dir = tmp_path / "venv"
    subprocess.run(
        args=[sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
        check=True,
        capture_output=True,
        cwd=repo_root,
        text=True,
    )
    venv_python = _venv_python(venv_dir=venv_dir)
    venv_eb = _venv_eb(venv_dir=venv_dir)
    venv_site_packages = Path(
        subprocess.run(
            args=[
                str(venv_python),
                "-c",
                "import site; print(site.getsitepackages()[0])",
            ],
            check=True,
            capture_output=True,
            cwd=repo_root,
            text=True,
        ).stdout.strip()
    )
    current_site_packages = Path(site.getsitepackages()[0])
    (venv_site_packages / "shared-deps.pth").write_text(
        f"{current_site_packages}\n", encoding="utf-8"
    )

    subprocess.run(
        args=[str(venv_python), "-m", "pip", "install", "--no-deps", str(wheel_path)],
        check=True,
        capture_output=True,
        cwd=repo_root,
        text=True,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    install_result = subprocess.run(
        args=[str(venv_eb), "install", "--cwd", str(project_root)],
        check=True,
        capture_output=True,
        cwd=repo_root,
        text=True,
    )

    skill_md_path = project_root / ".claude" / "skills" / "eval-banana" / "SKILL.md"
    codex_yaml_path = (
        project_root
        / ".codex"
        / "skills"
        / "gemini_media_use"
        / "agents"
        / "openai.yaml"
    )
    skill_lines = skill_md_path.read_text(encoding="utf-8").splitlines()
    frontmatter_end = skill_lines.index("---", 1)
    frontmatter = yaml.safe_load("\n".join(skill_lines[1:frontmatter_end]))

    assert install_result.returncode == 0
    assert frontmatter["name"] == "eval-banana"
    assert codex_yaml_path.is_file()
