from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
from typing import Literal

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER_PATTERN = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}")
_WARNED_MISSING_ENV_VARS: set[str] = set()


@dataclass(frozen=True)
class AgentTemplate:
    """Describes how to invoke a single CLI coding agent.

    Each field maps to a structural piece of the agent's command line or
    environment.  Built-in templates for well-known agents are defined in
    DEFAULT_AGENT_TEMPLATES; users can override or extend them via
    ``[agents.*]`` TOML config sections.
    """

    command: tuple[str, ...]
    shared_flags: tuple[str, ...] = ()
    prompt_flag: str | None = None
    prompt_position: Literal["tail", "after_command"] = "tail"
    model_flag: str | None = "--model"
    model_env_vars: tuple[str, ...] = ()
    default_model: str | None = None
    reasoning_effort: str | None = None
    reasoning_effort_flag: tuple[str, ...] = ()
    provider_env: tuple[tuple[str, str], ...] = ()


DEFAULT_AGENT_TEMPLATES: dict[str, AgentTemplate] = {
    "codex": AgentTemplate(
        command=("codex", "exec"),
        shared_flags=(
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ),
        model_flag="--model",
        default_model="gpt-5.4",
        reasoning_effort_flag=("-c", "model_reasoning_effort={effort}"),
    ),
    "gemini": AgentTemplate(
        command=("gemini",),
        shared_flags=("--approval-mode", "yolo", "--output-format", "stream-json"),
        prompt_flag="-p",
        model_flag="--model",
    ),
    "claude": AgentTemplate(
        command=("claude",),
        shared_flags=(
            "-p",
            "--dangerously-skip-permissions",
            "--output-format",
            "stream-json",
            "--verbose",
        ),
        model_flag="--model",
        model_env_vars=(
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
        ),
        reasoning_effort_flag=("--effort", "{effort}"),
    ),
    "openhands": AgentTemplate(
        command=("openhands",),
        shared_flags=("--headless", "--json", "--override-with-envs"),
        prompt_flag="-t",
        prompt_position="tail",
        model_flag=None,
        model_env_vars=("LLM_MODEL",),
    ),
    "opencode": AgentTemplate(command=("opencode",), model_flag=None),
    "pi": AgentTemplate(command=("pi", "--print", "--no-session"), model_flag=None),
}


def build_template_env(
    *, template: AgentTemplate, effective_model: str | None
) -> dict[str, str]:
    """Return env vars that inject the effective model into agent-specific names.

    For example, the Claude template sets ANTHROPIC_MODEL,
    ANTHROPIC_DEFAULT_SONNET_MODEL, and ANTHROPIC_DEFAULT_OPUS_MODEL.
    Returns an empty dict when no model is effective or the template has
    no model_env_vars.
    """
    if effective_model is None:
        return {}
    return {env_name: effective_model for env_name in template.model_env_vars}


def _warn_once_for_missing_env(*, env_name: str) -> None:
    if env_name in _WARNED_MISSING_ENV_VARS:
        return
    _WARNED_MISSING_ENV_VARS.add(env_name)
    logger.warning(
        "Harness provider env placeholder referenced missing environment variable %s",
        env_name,
    )


def _resolve_provider_env_value(*, value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        resolved = os.getenv(env_name)
        if resolved is None:
            _warn_once_for_missing_env(env_name=env_name)
            return ""
        return resolved

    return _ENV_PLACEHOLDER_PATTERN.sub(_replace, value)


def build_provider_env(*, template: AgentTemplate) -> dict[str, str]:
    """Resolve provider_env placeholders from the parent shell environment.

    Values may contain ``{env:VARNAME}`` placeholders that are replaced with
    the corresponding ``os.environ`` value at call time.  Missing env vars
    resolve to ``""`` with a one-time warning.
    """
    return {
        key: _resolve_provider_env_value(value=value)
        for key, value in template.provider_env
    }


def render_reasoning_effort_flags(
    *, template: AgentTemplate, reasoning_effort: str | None = None
) -> list[str]:
    """Return argv tokens for the agent's reasoning effort level.

    Each token in ``template.reasoning_effort_flag`` has its ``{effort}``
    placeholder replaced with the effective level.  Returns an empty list
    when no reasoning effort is configured.
    """
    effective_reasoning_effort = reasoning_effort or template.reasoning_effort
    if effective_reasoning_effort is None:
        return []
    return [
        item.replace("{effort}", effective_reasoning_effort)
        for item in template.reasoning_effort_flag
    ]
