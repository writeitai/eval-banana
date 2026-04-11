from __future__ import annotations

from pathlib import Path

import pytest

from eval_banana.config import _deep_merge
from eval_banana.config import find_local_config
from eval_banana.config import HarnessConfig
from eval_banana.config import load_config


def _write_config(path: Path, *, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
                "deterministic_timeout_seconds = 11",
                "llm_timeout_seconds = 22",
                "task_timeout_seconds = 33",
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
    assert config.deterministic_timeout_seconds == 11
    assert config.llm_timeout_seconds == 22
    assert config.task_timeout_seconds == 33
    assert config.llm_max_input_chars == 44
    assert config.provider == "openai_compat"
    assert config.model == "my-model"
    assert config.api_base == "https://example.com/v1"
    assert config.api_key == "secret"
    assert config.codex_auth_path == "/tmp/auth.json"
    assert config.discovery_exclude_dirs == ["one", "two"]


def test_harnesses_section_deep_merges_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        home / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.codex]\n"
            'command = ["codex", "exec"]\n'
            "\n"
            "[harnesses.claude]\n"
            'command = ["claude"]\n'
        ),
    )
    _write_config(
        project / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.codex]\n"
            'command = ["codex", "run"]\n'
            "\n"
            "[harnesses.gemini]\n"
            'command = ["gemini"]\n'
        ),
    )

    config = load_config(cwd=str(project))

    assert config.harnesses == {
        "codex": HarnessConfig(command=["codex", "run"]),
        "claude": HarnessConfig(command=["claude"]),
        "gemini": HarnessConfig(command=["gemini"]),
    }


def test_harness_provider_env_deep_merges_by_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        home / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.claude]\n"
            'command = ["claude"]\n'
            "\n"
            "[harnesses.claude.provider_env]\n"
            'ANTHROPIC_BASE_URL = "https://example.test"\n'
            'ANTHROPIC_AUTH_TOKEN = "{env:OPENROUTER_API_KEY}"\n'
        ),
    )
    _write_config(
        project / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.claude]\n"
            'command = ["claude"]\n'
            "\n"
            "[harnesses.claude.provider_env]\n"
            'ANTHROPIC_AUTH_TOKEN = "{env:PROJECT_KEY}"\n'
            'ANTHROPIC_API_KEY = ""\n'
        ),
    )

    config = load_config(cwd=str(project))

    assert config.harnesses["claude"].provider_env == {
        "ANTHROPIC_BASE_URL": "https://example.test",
        "ANTHROPIC_AUTH_TOKEN": "{env:PROJECT_KEY}",
        "ANTHROPIC_API_KEY": "",
    }


def test_harness_list_fields_replace_on_local_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        home / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.codex]\n"
            'command = ["codex", "exec"]\n'
            'shared_flags = ["--global"]\n'
            'model_env_vars = ["GLOBAL_MODEL", "SECOND_GLOBAL_MODEL"]\n'
        ),
    )
    _write_config(
        project / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.codex]\n"
            'command = ["codex", "run"]\n'
            'shared_flags = ["--local"]\n'
            'model_env_vars = ["LOCAL_MODEL"]\n'
        ),
    )

    config = load_config(cwd=str(project))

    assert config.harnesses["codex"].command == ["codex", "run"]
    assert config.harnesses["codex"].shared_flags == ["--local"]
    assert config.harnesses["codex"].model_env_vars == ["LOCAL_MODEL"]


def test_harness_config_parses_all_supported_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text=(
            "[harnesses.claude_openrouter]\n"
            'command = ["claude"]\n'
            'shared_flags = ["--dangerously-skip-permissions"]\n'
            'default_model = "anthropic/claude-sonnet-4.6"\n'
            'model_flag = "--model"\n'
            'model_env_vars = ["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"]\n'
            "\n"
            "[harnesses.claude_openrouter.provider_env]\n"
            'ANTHROPIC_BASE_URL = "https://openrouter.ai/api"\n'
            'ANTHROPIC_AUTH_TOKEN = "{env:OPENROUTER_API_KEY}"\n'
            'ANTHROPIC_API_KEY = ""\n'
        ),
    )

    config = load_config(cwd=str(project))

    assert config.harnesses["claude_openrouter"] == HarnessConfig(
        command=["claude"],
        shared_flags=["--dangerously-skip-permissions"],
        default_model="anthropic/claude-sonnet-4.6",
        model_flag="--model",
        model_env_vars=["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"],
        provider_env={
            "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
            "ANTHROPIC_AUTH_TOKEN": "{env:OPENROUTER_API_KEY}",
            "ANTHROPIC_API_KEY": "",
        },
    )


def test_harness_config_requires_command_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = "codex exec"\n',
    )

    with pytest.raises(
        SystemExit, match="command is required and must be a non-empty list of strings"
    ):
        load_config(cwd=str(project))


def test_harness_config_rejects_empty_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text="[harnesses.codex]\ncommand = []\n",
    )

    with pytest.raises(
        SystemExit, match="command is required and must be a non-empty list of strings"
    ):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_string_default_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = ["codex"]\ndefault_model = 42\n',
    )

    with pytest.raises(SystemExit, match="default_model must be a string when set"):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_string_model_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = ["codex"]\nmodel_flag = 42\n',
    )

    with pytest.raises(SystemExit, match="model_flag must be a string when set"):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_list_model_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = ["codex"]\nmodel_env_vars = "FOO"\n',
    )

    with pytest.raises(
        SystemExit, match="model_env_vars must be a list of strings when set"
    ):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_list_shared_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = ["codex"]\nshared_flags = "FOO"\n',
    )

    with pytest.raises(
        SystemExit, match="shared_flags must be a list of strings when set"
    ):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_table_provider_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text='[harnesses.codex]\ncommand = ["codex"]\nprovider_env = "x"\n',
    )

    with pytest.raises(
        SystemExit, match="provider_env must be a table of string values when set"
    ):
        load_config(cwd=str(project))


def test_harness_config_rejects_non_string_provider_env_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml",
        text=(
            '[harnesses.codex]\ncommand = ["codex"]\n'
            "\n"
            "[harnesses.codex.provider_env]\n"
            "FOO = 42\n"
        ),
    )

    with pytest.raises(
        SystemExit, match="provider_env must be a table of string values when set"
    ):
        load_config(cwd=str(project))


def test_harnesses_section_rejects_non_table_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml", text='harnesses = "not a table"\n'
    )

    with pytest.raises(SystemExit, match=r"\[harnesses\] must be a table"):
        load_config(cwd=str(project))


def test_harnesses_absent_section_loads_empty_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    monkeypatch.setenv("HOME", str(home))
    _write_config(
        project / ".eval-banana" / "config.toml", text='[core]\noutput_dir = "out"\n'
    )

    config = load_config(cwd=str(project))

    assert config.harnesses == {}
