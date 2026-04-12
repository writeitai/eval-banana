from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import logging
import os
from pathlib import Path
import tomllib
from typing import Any
from typing import cast

logger = logging.getLogger(__name__)

_GLOBAL_CONFIG_TEXT = """# Global eval-banana configuration.
# Project-level .eval-banana/config.toml overrides these values.


[core]
output_dir = ".eval-banana/results"
pass_threshold = 1.0
llm_max_input_chars = 12000


[llm]
provider = "openai_compat"
model = "openai/gpt-4.1-mini"
api_base = "https://openrouter.ai/api/v1"
api_key = ""
codex_auth_path = ""


[discovery]
exclude_dirs = [".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]
"""

_LOCAL_CONFIG_TEXT = """# Project-level eval-banana configuration.
# Values here override ~/.eval-banana/config.toml.
# Do not commit API keys.


[core]
output_dir = ".eval-banana/results"
pass_threshold = 1.0
llm_max_input_chars = 12000


[llm]
provider = "openai_compat"
model = "openai/gpt-4.1-mini"
api_base = "https://openrouter.ai/api/v1"


[discovery]
exclude_dirs = [".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]
"""


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
    if isinstance(value, int):
        return value
    return default


def _get_string_list(
    data: dict[str, object], *, section: str, key: str, default: list[str]
) -> list[str]:
    value = _get_nested_value(data, section=section, key=key)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return default


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
    ]
    for env_name, section, key, caster in env_specs:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=caster(raw))

    cli_overrides: list[tuple[object | None, str, str]] = [
        (output_dir, "core", "output_dir"),
        (pass_threshold, "core", "pass_threshold"),
        (provider, "llm", "provider"),
        (model, "llm", "model"),
        (api_base, "llm", "api_base"),
        (api_key, "llm", "api_key"),
        (codex_auth_path, "llm", "codex_auth_path"),
    ]
    for value, section, key in cli_overrides:
        if value is None:
            continue
        _set_nested_value(merged, section=section, key=key, value=value)

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
    )

    output_path = Path(config.output_dir)
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()
    config.output_dir = str(output_path)

    logger.debug("Resolved config: %s", config)
    return config
