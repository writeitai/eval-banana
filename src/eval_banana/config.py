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

# Maximum characters of each target file sent to harness_judge checks. Content
# beyond this limit is truncated with a [TRUNCATED] marker.
# Set to 0 (the default) to disable truncation entirely — the full file
# content is sent to the harness agent regardless of size.
# Env: EVAL_BANANA_LLM_MAX_INPUT_CHARS
llm_max_input_chars = 0
"""


_HARNESS_TEMPLATE = """\
# [harness]
# # AI coding agent used by harness_judge checks. One of:
# #   claude, codex, gemini, openhands, opencode, pi
# # Env: EVAL_BANANA_HARNESS_AGENT
# agent = "codex"
#
# # Override the agent's default model. Format is agent-specific.
# # Env: EVAL_BANANA_HARNESS_MODEL
# model = "gpt-5.4"
#
# # Agent-specific reasoning-effort level. Common values: "low", "medium", "high".
# # Not all agents honor this. Env: EVAL_BANANA_HARNESS_REASONING_EFFORT
# reasoning_effort = "high"
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

_LOCAL_CONFIG_TEXT = f"""\
# Project-level eval-banana configuration.

{_CORE_SECTION}

{_HARNESS_TEMPLATE}

{_DISCOVERY_SECTION}"""


@dataclass
class Config:
    output_dir: str = ".eval-banana/results"
    pass_threshold: float = 1.0
    llm_max_input_chars: int = 0
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
    local_config_path: Path | None = None
    harness_agent: str | None = None
    harness_model: str | None = None
    harness_reasoning_effort: str | None = None
    harness_env: dict[str, str] = field(default_factory=dict)
    agent_templates: dict[str, AgentTemplate] = field(default_factory=dict)


def get_local_config_template() -> str:
    """Return the TOML template text written by ``eval-banana init``."""
    return _LOCAL_CONFIG_TEXT


def find_local_config(start: Path | None = None) -> Path | None:
    """Walk upward from *start* to find ``.eval-banana/config.toml``."""
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


def _reject_legacy_llm_section(*, data: dict[str, object], path: Path) -> None:
    if "llm" not in data:
        return
    msg = (
        f"Legacy [llm] section was removed from {path}. "
        "Delete the [llm] section and configure harness agents under [harness] "
        "and [agents.*] instead."
    )
    raise SystemExit(msg)


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


def _sanitize_harness_section(data: dict[str, object]) -> None:
    raw_harness = data.get("harness")
    if raw_harness is None:
        return
    if not isinstance(raw_harness, dict):
        msg = "[harness] must be a TOML table"
        raise SystemExit(msg)

    if "skip" in raw_harness:
        msg = (
            "[harness] skip was removed; delete the key from your config. "
            "harness is skipped automatically when [harness] agent is unset."
        )
        raise SystemExit(msg)

    allowed_keys = {"agent", "model", "reasoning_effort", "env", "skills_dir"}
    unknown_keys = set(raw_harness) - allowed_keys
    if unknown_keys:
        unknown_keys_text = ", ".join(sorted(unknown_keys))
        msg = f"[harness] contains unknown keys: {unknown_keys_text}"
        raise SystemExit(msg)

    if "skills_dir" not in raw_harness:
        return

    sanitized_harness = dict(raw_harness)
    sanitized_harness.pop("skills_dir")
    data["harness"] = sanitized_harness


def load_config(
    *,
    output_dir: str | None = None,
    pass_threshold: float | None = None,
    cwd: str | None = None,
    harness_agent: str | None = None,
    harness_model: str | None = None,
    harness_reasoning_effort: str | None = None,
) -> Config:
    """Build a fully-resolved :class:`Config` from TOML, env vars, and CLI overrides.

    Resolution order (highest priority first):
    1. Keyword arguments (from CLI flags).
    2. ``EVAL_BANANA_*`` environment variables.
    3. Project-level ``.eval-banana/config.toml`` (walked upward from *cwd*).
    4. Built-in defaults on :class:`Config`.

    Raises :class:`SystemExit` on invalid TOML or legacy ``[llm]`` sections.
    """
    cwd_path = Path(cwd or ".").resolve()
    local_config_path = find_local_config(start=cwd_path)
    project_root = _resolve_project_root(
        cwd=cwd_path, local_config_path=local_config_path
    )

    merged: dict[str, object] = {}
    if local_config_path is not None:
        local_config = _load_toml_file(path=local_config_path)
        _reject_legacy_llm_section(data=local_config, path=local_config_path)
        merged = _deep_merge(base=merged, override=local_config)

    env_specs: list[tuple[str, str, str, type[Any]]] = [
        ("EVAL_BANANA_OUTPUT_DIR", "core", "output_dir", str),
        ("EVAL_BANANA_PASS_THRESHOLD", "core", "pass_threshold", float),
        ("EVAL_BANANA_LLM_MAX_INPUT_CHARS", "core", "llm_max_input_chars", int),
        ("EVAL_BANANA_HARNESS_AGENT", "harness", "agent", str),
        ("EVAL_BANANA_HARNESS_MODEL", "harness", "model", str),
        ("EVAL_BANANA_HARNESS_REASONING_EFFORT", "harness", "reasoning_effort", str),
    ]
    for env_name, section, key, caster in env_specs:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=caster(raw))

    cli_overrides: list[tuple[object | None, str, str]] = [
        (output_dir, "core", "output_dir"),
        (pass_threshold, "core", "pass_threshold"),
        (harness_agent, "harness", "agent"),
        (harness_model, "harness", "model"),
        (harness_reasoning_effort, "harness", "reasoning_effort"),
    ]
    for value, section, key in cli_overrides:
        if value is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=value)

    _sanitize_harness_section(merged)

    agent_templates = _parse_agent_templates(merged)

    config = Config(
        output_dir=_get_string(
            merged, section="core", key="output_dir", default=".eval-banana/results"
        ),
        pass_threshold=_get_float(
            merged, section="core", key="pass_threshold", default=1.0
        ),
        llm_max_input_chars=_get_int(
            merged, section="core", key="llm_max_input_chars", default=0
        ),
        discovery_exclude_dirs=_get_string_list(
            merged,
            section="discovery",
            key="exclude_dirs",
            default=Config().discovery_exclude_dirs,
        ),
        cwd=str(cwd_path),
        project_root=project_root,
        local_config_path=local_config_path,
        harness_agent=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="agent")
        ),
        harness_model=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="model")
        ),
        harness_reasoning_effort=_normalize_optional_string(
            value=_get_nested_value(merged, section="harness", key="reasoning_effort")
        ),
        harness_env=_get_string_dict(merged, section="harness", key="env"),
        agent_templates=agent_templates,
    )

    output_path = Path(config.output_dir)
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()
    config.output_dir = str(output_path)

    logger.debug("Resolved config: %s", config)
    return config
