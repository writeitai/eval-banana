from __future__ import annotations

import logging

from eval_banana.harness.template import AgentTemplate
from eval_banana.harness.template import DEFAULT_AGENT_TEMPLATES
from eval_banana.harness.template import render_reasoning_effort_flags

logger = logging.getLogger(__name__)


def resolve_template(
    *, agent_type: str, user_templates: dict[str, AgentTemplate]
) -> AgentTemplate:
    if agent_type in user_templates:
        return user_templates[agent_type]
    if agent_type in DEFAULT_AGENT_TEMPLATES:
        return DEFAULT_AGENT_TEMPLATES[agent_type]
    msg = f"Unknown harness agent: {agent_type}"
    raise SystemExit(msg)


def build_command_from_template(
    *, template: AgentTemplate, prompt: str, model: str | None = None
) -> list[str]:
    command = list(template.command)
    prompt_args = (
        [template.prompt_flag, prompt] if template.prompt_flag is not None else [prompt]
    )
    if template.prompt_position == "after_command":
        command.extend(prompt_args)

    command.extend(template.shared_flags)

    effective_model = model if model is not None else template.default_model
    if effective_model is not None and template.model_flag is not None:
        command.extend([template.model_flag, effective_model])

    command.extend(render_reasoning_effort_flags(template=template))

    if template.prompt_position == "tail":
        command.extend(prompt_args)

    return command
