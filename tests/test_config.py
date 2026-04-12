from __future__ import annotations

from pathlib import Path

import pytest

from eval_banana.config import _deep_merge
from eval_banana.config import find_local_config
from eval_banana.config import get_global_config_template
from eval_banana.config import get_local_config_template
from eval_banana.config import load_config


def test_find_local_config_walks_upward(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    config_path = project_root / ".eval-banana" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '[core]\noutput_dir = ".eval-banana/results"\n', encoding="utf-8"
    )
    nested = project_root / "src" / "pkg"
    nested.mkdir(parents=True)

    assert find_local_config(start=nested) == config_path


def test_deep_merge_replaces_lists_and_merges_dicts() -> None:
    merged = _deep_merge(
        base={"core": {"output_dir": "a"}, "discovery": {"exclude_dirs": ["a"]}},
        override={
            "core": {"pass_threshold": 0.5},
            "discovery": {"exclude_dirs": ["b"]},
        },
    )

    assert merged == {
        "core": {"output_dir": "a", "pass_threshold": 0.5},
        "discovery": {"exclude_dirs": ["b"]},
    }


def test_env_var_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".eval-banana").mkdir(parents=True)
    (project / ".eval-banana").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (home / ".eval-banana" / "config.toml").write_text(
        '[core]\noutput_dir = "global-results"\n[llm]\nprovider = "openai_compat"\n',
        encoding="utf-8",
    )
    (project / ".eval-banana" / "config.toml").write_text(
        '[core]\noutput_dir = "local-results"\n[llm]\nprovider = "codex"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EVAL_BANANA_OUTPUT_DIR", "env-results")

    config = load_config(cwd=str(project))

    assert config.output_dir == str((project / "env-results").resolve())
    assert config.provider == "codex"


def test_relative_output_dir_resolves_from_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    (project / ".eval-banana").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (project / ".eval-banana" / "config.toml").write_text(
        '[core]\noutput_dir = "custom-results"\n', encoding="utf-8"
    )

    config = load_config(cwd=str(nested))

    assert config.project_root == project.resolve()
    assert config.output_dir == str((project / "custom-results").resolve())


def test_provider_defaults_normalization_for_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".eval-banana").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (project / ".eval-banana" / "config.toml").write_text(
        '[llm]\nprovider = "codex"\n', encoding="utf-8"
    )

    config = load_config(cwd=str(project))

    assert config.provider == "codex"
    assert config.model == "gpt-4.1-mini"
    assert config.api_base == ""


def test_toml_mapping_table_is_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".eval-banana").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (project / ".eval-banana" / "config.toml").write_text(
        "\n".join(
            [
                "[core]",
                'output_dir = "out"',
                "pass_threshold = 0.7",
                "llm_max_input_chars = 44",
                "",
                "[llm]",
                'provider = "openai_compat"',
                'model = "my-model"',
                'api_base = "https://example.com/v1"',
                'api_key = "secret"',
                'codex_auth_path = "/tmp/auth.json"',
                "",
                "[discovery]",
                'exclude_dirs = ["one", "two"]',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(cwd=str(project))

    assert config.output_dir == str((project / "out").resolve())
    assert config.pass_threshold == 0.7
    assert config.llm_max_input_chars == 44
    assert config.provider == "openai_compat"
    assert config.model == "my-model"
    assert config.api_base == "https://example.com/v1"
    assert config.api_key == "secret"
    assert config.codex_auth_path == "/tmp/auth.json"
    assert config.discovery_exclude_dirs == ["one", "two"]


def test_stale_timeout_toml_is_silently_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    (project / ".eval-banana").mkdir(parents=True)
    (project / ".eval-banana" / "config.toml").write_text(
        "\n".join(
            [
                "[core]",
                "deterministic_timeout_seconds = 30",
                "llm_timeout_seconds = 90",
                "task_timeout_seconds = 300",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(cwd=str(project))

    assert not hasattr(config, "deterministic_timeout_seconds")
    assert not hasattr(config, "llm_timeout_seconds")
    assert not hasattr(config, "task_timeout_seconds")


def test_config_templates_do_not_contain_timeout_keys() -> None:
    for template in (get_global_config_template(), get_local_config_template()):
        assert "deterministic_timeout_seconds" not in template
        assert "llm_timeout_seconds" not in template
        assert "task_timeout_seconds" not in template
        assert "timeout" not in template.lower()
