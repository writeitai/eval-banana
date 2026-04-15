from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
import logging
import os
from pathlib import Path
import tomllib
from typing import Any
from typing import cast

from eval_banana.harness.template import AgentTemplate
from eval_banana.harness.template import DEFAULT_AGENT_TEMPLATES

logger = logging.getLogger(__name__)

_CORE_SECTION = """\
[core]
# Directory where run artifacts (report.json, report.md, per-check output) are
# written. Relative paths resolve from the project root.
# Env: EVAL_BANANA_OUTPUT_DIR
output_dir = ".eval-banana/results"

# Minimum pass ratio (0.0-1.0) for `run_passed` to be true. 1.0 means every
# check must pass. Set lower (e.g. 0.8) to tolerate some failing checks.
# Env: EVAL_BANANA_PASS_THRESHOLD
pass_threshold = 1.0

# Maximum characters of each target file sent to llm_judge checks. Content
# beyond this is truncated with a [TRUNCATED] marker. Prevents huge prompts,
# runaway costs, and context-window overflow on large files.
# Env: EVAL_BANANA_LLM_MAX_INPUT_CHARS
llm_max_input_chars = 12000
"""

_LLM_SECTION_COMMON = """\
[llm]
# LLM provider used by llm_judge checks.
#   "openai_compat" - OpenAI-compatible HTTP API (OpenRouter, OpenAI direct,
#                     local Ollama, vLLM, etc.). Uses `api_base` + `api_key`.
#   "codex"         - Local ChatGPT subscription via `codex login`. Hardcoded
#                     backend; `api_base` is ignored in this mode.
# Env: EVAL_BANANA_PROVIDER
provider = "openai_compat"

# Model identifier. Format is provider-specific:
#   OpenRouter: "<vendor>/<model>" (e.g. "openai/gpt-4.1-mini", "anthropic/claude-3.5-sonnet")
#   OpenAI:     "<model>"          (e.g. "gpt-4.1-mini")
#   Codex:      "<model>"          (e.g. "gpt-4.1-mini")
# Env: EVAL_BANANA_MODEL
model = "openai/gpt-4.1-mini"

# Base URL for the openai_compat provider. Common values:
#   https://openrouter.ai/api/v1  (default)
#   https://api.openai.com/v1     (OpenAI direct)
#   http://localhost:11434/v1     (local Ollama)
# Ignored when provider = "codex".
# Env: EVAL_BANANA_API_BASE
api_base = "https://openrouter.ai/api/v1"
"""

_LLM_SECRETS_GLOBAL = """\

# API key for the openai_compat provider. Prefer environment variables:
#   OPENROUTER_API_KEY - automatically used when api_base contains "openrouter.ai"
#   OPENAI_API_KEY     - automatically used when api_base contains "api.openai.com"
#   EVAL_BANANA_API_KEY - overrides both above
# Leave empty to force env-var lookup.
api_key = ""

# Override path to the Codex auth file (JSON written by `codex login`). Leave
# empty to use $CODEX_HOME/auth.json or ~/.codex/auth.json.
# Env: EVAL_BANANA_CODEX_AUTH_PATH
codex_auth_path = ""
"""

_HARNESS_TEMPLATE = """\
# [harness]
# # AI coding agent to run once before the check loop. One of:
# #   claude, codex, gemini, openhands, opencode, pi
# # Env: EVAL_BANANA_HARNESS_AGENT
# agent = "codex"
#
# # Task prompt for the agent. Use `prompt` for a short inline string, or
# # `prompt_file` for a path (relative to project root). They are mutually
# # exclusive.
# # Env: EVAL_BANANA_HARNESS_PROMPT / EVAL_BANANA_HARNESS_PROMPT_FILE
# # prompt = "Fix the failing tests"
# prompt_file = "prompts/task.md"
#
# # Override the agent's default model. Format is agent-specific.
# # Env: EVAL_BANANA_HARNESS_MODEL
# model = "gpt-5.4"
#
# # Agent-specific reasoning-effort level. Common values: "low", "medium", "high".
# # Not all agents honor this. Env: EVAL_BANANA_HARNESS_REASONING_EFFORT
# reasoning_effort = "high"
#
# # Repo-local skills directory distributed to the agent before it runs.
# # Relative to project root. See `eval-banana distribute-skills`.
# skills_dir = "skills"
#
# # Extra environment variables injected into the harness subprocess.
# [harness.env]
# CI = "1"
# PYTHONUNBUFFERED = "1"
"""

_DISCOVERY_SECTION = """\
[discovery]
# Directories skipped when auto-discovering eval_checks/ folders. Override this
# if your project uses a non-standard layout.
exclude_dirs = [".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]
"""

_GLOBAL_CONFIG_TEXT = f"""\
# Global eval-banana configuration.
# Project-level .eval-banana/config.toml overrides these values.
# All keys support environment-variable overrides (noted inline).

{_CORE_SECTION}

{_LLM_SECTION_COMMON}
{_LLM_SECRETS_GLOBAL}

{_HARNESS_TEMPLATE}

{_DISCOVERY_SECTION}"""

_LOCAL_CONFIG_TEXT = f"""\
# Project-level eval-banana configuration.
# Values here override ~/.eval-banana/config.toml.
# Do not commit API keys -- use environment variables instead.

{_CORE_SECTION}

{_LLM_SECTION_COMMON}

{_HARNESS_TEMPLATE}

{_DISCOVERY_SECTION}"""


@dataclass
class Config:
    output_dir: str = ".eval-banana/results"
    pass_threshold: float = 1.0
    provider: str = "openai_compat"
    model: str = "openai/gpt-4.1-mini"
    api_base: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    codex_auth_path: str = ""
    llm_max_input_chars: int = 12000
    discovery_exclude_dirs: list[str] = field(
        default_factory=lambda: [
            ".git",
            ".hg",
            ".svn",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            "dist",
            "build",
        ]
    )
    cwd: str = "."
    project_root: Path | None = None
    global_config_path: Path | None = None
    local_config_path: Path | None = None
    harness_agent: str | None = None
    harness_prompt: str | None = None
    harness_prompt_file: str | None = None
    harness_model: str | None = None
    harness_reasoning_effort: str | None = None
    harness_env: dict[str, str] = field(default_factory=dict)
    skills_dir: str = "skills"
    skip_harness: bool = False
    agent_templates: dict[str, AgentTemplate] = field(default_factory=dict)


def get_global_config_template() -> str:
    return _GLOBAL_CONFIG_TEXT


def get_local_config_template() -> str:
    return _LOCAL_CONFIG_TEXT


def find_local_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        config_path = candidate / ".eval-banana" / "config.toml"
        logger.debug("Checking for local config at %s", config_path)
        if config_path.is_file():
            return config_path
    return None


def _load_toml_file(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in {path}: {exc}"
        raise SystemExit(msg) from exc
    logger.debug("Loaded TOML config from %s", path)
    return dict(data)


def _deep_merge(
    base: dict[str, object], override: dict[str, object]
) -> dict[str, object]:
    merged: dict[str, object] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(
                base=cast(dict[str, object], merged[key]),
                override=cast(dict[str, object], value),
            )
            continue
        merged[key] = value
    return merged


def _get_section(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, object], value)


def _resolve_project_root(cwd: Path, local_config_path: Path | None) -> Path:
    if local_config_path is not None:
        return local_config_path.parent.parent.resolve()
    return cwd.resolve()


def _coerce_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    msg = f"Invalid boolean value: {value}"
    raise ValueError(msg)


def _set_nested_value(
    data: dict[str, object], *, section: str, key: str, value: object
) -> None:
    section_data = dict(_get_section(data=data, key=section))
    section_data[key] = value
    data[section] = section_data


def _get_nested_value(
    data: dict[str, object], *, section: str, key: str
) -> object | None:
    section_data = _get_section(data=data, key=section)
    return section_data.get(key)


def _get_string(
    data: dict[str, object], *, section: str, key: str, default: str
) -> str:
    value = _get_nested_value(data, section=section, key=key)
    if isinstance(value, str):
        return value
    return default


def _get_float(
    data: dict[str, object], *, section: str, key: str, default: float
) -> float:
    value = _get_nested_value(data, section=section, key=key)
    if isinstance(value, int | float):
        return float(value)
    return default


def _get_int(data: dict[str, object], *, section: str, key: str, default: int) -> int:
    value = _get_nested_value(data, section=section, key=key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _get_string_list(
    data: dict[str, object], *, section: str, key: str, default: list[str]
) -> list[str]:
    value = _get_nested_value(data, section=section, key=key)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return default


def _get_string_dict(
    data: dict[str, object], *, section: str, key: str
) -> dict[str, str]:
    value = _get_nested_value(data, section=section, key=key)
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        msg = f"[{section}.{key}] must be a TOML table of string values"
        raise SystemExit(msg)
    return dict(value)


def _normalize_optional_string(*, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "Expected a string value"
        raise SystemExit(msg)
    if value == "":
        return None
    return value


def _parse_prompt_position(*, agent_name: str, raw_value: object | None) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        msg = f"[agents.{agent_name}] prompt_position must be a string"
        raise SystemExit(msg)
    if raw_value not in {"tail", "after_command"}:
        msg = f"[agents.{agent_name}] prompt_position must be 'tail' or 'after_command'"
        raise SystemExit(msg)
    return raw_value


def _parse_tuple_field(
    *, agent_name: str, raw_value: object | None, field_name: str
) -> tuple[str, ...] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, list) or not all(
        isinstance(item, str) for item in raw_value
    ):
        msg = f"[agents.{agent_name}] {field_name} must be a list of strings"
        raise SystemExit(msg)
    return tuple(raw_value)


def _parse_provider_env(
    *, agent_name: str, raw_value: object | None
) -> tuple[tuple[str, str], ...] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, dict) or not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in raw_value.items()
    ):
        msg = f"[agents.{agent_name}.provider_env] must be a TOML table of strings"
        raise SystemExit(msg)
    return tuple((key, value) for key, value in raw_value.items())


def _parse_agent_templates(data: dict[str, object]) -> dict[str, AgentTemplate]:
    raw_agents = data.get("agents")
    if raw_agents is None:
        return {}
    if not isinstance(raw_agents, dict):
        msg = "[agents] must be a TOML table"
        raise SystemExit(msg)

    parsed_templates: dict[str, AgentTemplate] = {}
    for agent_name, raw_agent_config in raw_agents.items():
        if not isinstance(agent_name, str) or not isinstance(raw_agent_config, dict):
            msg = "[agents] entries must be TOML tables"
            raise SystemExit(msg)

        allowed_keys = {
            "command",
            "shared_flags",
            "prompt_flag",
            "prompt_position",
            "model_flag",
            "model_env_vars",
            "default_model",
            "reasoning_effort",
            "reasoning_effort_flag",
            "provider_env",
        }
        unknown_keys = set(raw_agent_config) - allowed_keys
        if unknown_keys:
            unknown_keys_text = ", ".join(sorted(unknown_keys))
            msg = f"[agents.{agent_name}] contains unknown keys: {unknown_keys_text}"
            raise SystemExit(msg)

        if agent_name in DEFAULT_AGENT_TEMPLATES:
            template = DEFAULT_AGENT_TEMPLATES[agent_name]
        else:
            template = AgentTemplate(command=())

        command = _parse_tuple_field(
            agent_name=agent_name,
            raw_value=raw_agent_config.get("command"),
            field_name="command",
        )
        shared_flags = _parse_tuple_field(
            agent_name=agent_name,
            raw_value=raw_agent_config.get("shared_flags"),
            field_name="shared_flags",
        )
        model_env_vars = _parse_tuple_field(
            agent_name=agent_name,
            raw_value=raw_agent_config.get("model_env_vars"),
            field_name="model_env_vars",
        )
        reasoning_effort_flag = _parse_tuple_field(
            agent_name=agent_name,
            raw_value=raw_agent_config.get("reasoning_effort_flag"),
            field_name="reasoning_effort_flag",
        )
        prompt_position = _parse_prompt_position(
            agent_name=agent_name, raw_value=raw_agent_config.get("prompt_position")
        )

        try:
            prompt_flag = _normalize_optional_string(
                value=raw_agent_config.get("prompt_flag")
            )
            model_flag = _normalize_optional_string(
                value=raw_agent_config.get("model_flag")
            )
            default_model = _normalize_optional_string(
                value=raw_agent_config.get("default_model")
            )
            reasoning_effort = _normalize_optional_string(
                value=raw_agent_config.get("reasoning_effort")
            )
        except SystemExit as exc:
            msg = f"[agents.{agent_name}] {exc}"
            raise SystemExit(msg) from exc

        provider_env = _parse_provider_env(
            agent_name=agent_name, raw_value=raw_agent_config.get("provider_env")
        )

        if command is None and agent_name not in DEFAULT_AGENT_TEMPLATES:
            msg = f"[agents.{agent_name}] command is required for custom agents"
            raise SystemExit(msg)

        updates: dict[str, object] = {}
        if command is not None:
            updates["command"] = command
        if shared_flags is not None:
            updates["shared_flags"] = shared_flags
        if "prompt_flag" in raw_agent_config:
            updates["prompt_flag"] = prompt_flag
        if prompt_position is not None:
            updates["prompt_position"] = prompt_position
        if "model_flag" in raw_agent_config:
            updates["model_flag"] = model_flag
        if model_env_vars is not None:
            updates["model_env_vars"] = model_env_vars
        if "default_model" in raw_agent_config:
            updates["default_model"] = default_model
        if "reasoning_effort" in raw_agent_config:
            updates["reasoning_effort"] = reasoning_effort
        if reasoning_effort_flag is not None:
            updates["reasoning_effort_flag"] = reasoning_effort_flag
        if provider_env is not None:
            updates["provider_env"] = provider_env

        parsed_templates[agent_name] = replace(template, **updates)

    return parsed_templates


def load_config(
    *,
    output_dir: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    codex_auth_path: str | None = None,
    pass_threshold: float | None = None,
    cwd: str | None = None,
    harness_agent: str | None = None,
    harness_prompt: str | None = None,
    harness_prompt_file: str | None = None,
    harness_model: str | None = None,
    harness_reasoning_effort: str | None = None,
    skip_harness: bool | None = None,
) -> Config:
    cwd_path = Path(cwd or ".").resolve()
    global_config_path = Path.home() / ".eval-banana" / "config.toml"
    local_config_path = find_local_config(start=cwd_path)
    project_root = _resolve_project_root(
        cwd=cwd_path, local_config_path=local_config_path
    )

    merged: dict[str, object] = {}
    if global_config_path.is_file():
        merged = _deep_merge(
            base=merged, override=_load_toml_file(path=global_config_path)
        )
    if local_config_path is not None:
        merged = _deep_merge(
            base=merged, override=_load_toml_file(path=local_config_path)
        )

    env_specs: list[tuple[str, str, str, type[Any]]] = [
        ("EVAL_BANANA_OUTPUT_DIR", "core", "output_dir", str),
        ("EVAL_BANANA_PASS_THRESHOLD", "core", "pass_threshold", float),
        ("EVAL_BANANA_LLM_MAX_INPUT_CHARS", "core", "llm_max_input_chars", int),
        ("EVAL_BANANA_PROVIDER", "llm", "provider", str),
        ("EVAL_BANANA_MODEL", "llm", "model", str),
        ("EVAL_BANANA_API_BASE", "llm", "api_base", str),
        ("EVAL_BANANA_API_KEY", "llm", "api_key", str),
        ("EVAL_BANANA_CODEX_AUTH_PATH", "llm", "codex_auth_path", str),
        ("EVAL_BANANA_HARNESS_AGENT", "harness", "agent", str),
        ("EVAL_BANANA_HARNESS_PROMPT", "harness", "prompt", str),
        ("EVAL_BANANA_HARNESS_PROMPT_FILE", "harness", "prompt_file", str),
        ("EVAL_BANANA_HARNESS_MODEL", "harness", "model", str),
        ("EVAL_BANANA_HARNESS_REASONING_EFFORT", "harness", "reasoning_effort", str),
    ]
    for env_name, section, key, caster in env_specs:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=caster(raw))
    raw_skip_harness = os.getenv("EVAL_BANANA_SKIP_HARNESS")
    if raw_skip_harness is not None:
        _set_nested_value(
            merged, section="harness", key="skip", value=_coerce_bool(raw_skip_harness)
        )

    cli_overrides: list[tuple[object | None, str, str]] = [
        (output_dir, "core", "output_dir"),
        (pass_threshold, "core", "pass_threshold"),
        (provider, "llm", "provider"),
        (model, "llm", "model"),
        (api_base, "llm", "api_base"),
        (api_key, "llm", "api_key"),
        (codex_auth_path, "llm", "codex_auth_path"),
        (harness_agent, "harness", "agent"),
        (harness_prompt, "harness", "prompt"),
        (harness_prompt_file, "harness", "prompt_file"),
        (harness_model, "harness", "model"),
        (harness_reasoning_effort, "harness", "reasoning_effort"),
    ]
    for value, section, key in cli_overrides:
        if value is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=value)
    if skip_harness is not None:
        _set_nested_value(merged, section="harness", key="skip", value=skip_harness)

    provider_value = str(
        _get_nested_value(merged, section="llm", key="provider") or "openai_compat"
    )
    model_explicit = _get_nested_value(merged, section="llm", key="model") is not None
    api_base_explicit = (
        _get_nested_value(merged, section="llm", key="api_base") is not None
    )
    api_key_explicit = (
        _get_nested_value(merged, section="llm", key="api_key") is not None
    )

    if provider_value == "codex":
        if not model_explicit:
            _set_nested_value(merged, section="llm", key="model", value="gpt-4.1-mini")
        if not api_base_explicit:
            _set_nested_value(merged, section="llm", key="api_base", value="")
    elif provider_value == "openai_compat":
        if not model_explicit:
            _set_nested_value(
                merged, section="llm", key="model", value="openai/gpt-4.1-mini"
            )
        if not api_base_explicit:
            _set_nested_value(
                merged,
                section="llm",
                key="api_base",
                value="https://openrouter.ai/api/v1",
            )

    resolved_api_base = str(
        _get_nested_value(merged, section="llm", key="api_base") or ""
    )
    if not api_key_explicit:
        provider_fallback_key = ""
        if "openrouter.ai" in resolved_api_base:
            provider_fallback_key = os.getenv("OPENROUTER_API_KEY", "")
        elif "api.openai.com" in resolved_api_base:
            provider_fallback_key = os.getenv("OPENAI_API_KEY", "")
        if provider_fallback_key:
            _set_nested_value(
                merged, section="llm", key="api_key", value=provider_fallback_key
            )

    raw_harness_skip = _get_nested_value(merged, section="harness", key="skip")
    if raw_harness_skip is None:
        resolved_skip_harness = False
    elif isinstance(raw_harness_skip, bool):
        resolved_skip_harness = raw_harness_skip
    else:
        msg = "[harness] skip must be a boolean"
        raise SystemExit(msg)

    agent_templates = _parse_agent_templates(merged)

    config = Config(
        output_dir=_get_string(
            merged, section="core", key="output_dir", default=".eval-banana/results"
        ),
        pass_threshold=_get_float(
            merged, section="core", key="pass_threshold", default=1.0
        ),
        provider=provider_value,
        model=_get_string(
            merged, section="llm", key="model", default="openai/gpt-4.1-mini"
        ),
        api_base=_get_string(
            merged,
            section="llm",
            key="api_base",
            default="https://openrouter.ai/api/v1"
            if provider_value == "openai_compat"
            else "",
        ),
        api_key=_get_string(merged, section="llm", key="api_key", default=""),
        codex_auth_path=_get_string(
            merged, section="llm", key="codex_auth_path", default=""
        ),
        llm_max_input_chars=_get_int(
            merged, section="core", key="llm_max_input_chars", default=12000
        ),
        discovery_exclude_dirs=_get_string_list(
            merged,
            section="discovery",
            key="exclude_dirs",
            default=Config().discovery_exclude_dirs,
        ),
        cwd=str(cwd_path),
        project_root=project_root,
        global_config_path=global_config_path,
        local_config_path=local_config_path,
        harness_agent=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="agent")
        ),
        harness_prompt=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="prompt")
        ),
        harness_prompt_file=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="prompt_file")
        ),
        harness_model=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="model")
        ),
        harness_reasoning_effort=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="reasoning_effort")
        ),
        harness_env=_get_string_dict(merged, section="harness", key="env"),
        skills_dir=_get_string(
            merged, section="harness", key="skills_dir", default="skills"
        ),
        skip_harness=resolved_skip_harness,
        agent_templates=agent_templates,
    )

    output_path = Path(config.output_dir)
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()
    config.output_dir = str(output_path)

    skills_path = Path(config.skills_dir)
    if not skills_path.is_absolute():
        skills_path = (project_root / skills_path).resolve()
    config.skills_dir = str(skills_path)

    logger.debug("Resolved config: %s", config)
    return config
