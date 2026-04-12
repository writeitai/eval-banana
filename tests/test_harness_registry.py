from __future__ import annotations

import pytest

from eval_banana.harness.registry import build_command_from_template
from eval_banana.harness.registry import resolve_template
from eval_banana.harness.template import AgentTemplate
from eval_banana.harness.template import DEFAULT_AGENT_TEMPLATES


def test_resolve_template_prefers_user_template_over_builtin() -> None:
    user_template = AgentTemplate(command=("custom-codex",))

    resolved = resolve_template(
        agent_type="codex", user_templates={"codex": user_template}
    )

    assert resolved is user_template


def test_resolve_template_raises_for_unknown_agent() -> None:
    with pytest.raises(SystemExit, match="Unknown harness agent"):
        resolve_template(agent_type="missing", user_templates={})


def test_build_command_codex_uses_tail_prompt_and_default_model() -> None:
    command = build_command_from_template(
        template=DEFAULT_AGENT_TEMPLATES["codex"], prompt="Fix the failing tests"
    )

    assert command[:2] == ["codex", "exec"]
    assert command[-1] == "Fix the failing tests"
    assert "--model" in command
    assert "gpt-5.4" in command


def test_build_command_gemini_uses_prompt_flag() -> None:
    command = build_command_from_template(
        template=DEFAULT_AGENT_TEMPLATES["gemini"], prompt="Investigate the failure"
    )

    assert command[-2:] == ["-p", "Investigate the failure"]


def test_build_command_claude_preserves_shared_p_flag_shape() -> None:
    command = build_command_from_template(
        template=DEFAULT_AGENT_TEMPLATES["claude"], prompt="Review the diff"
    )

    assert command[1] == "-p"
    assert command[-1] == "Review the diff"


def test_build_command_respects_model_flag_none() -> None:
    template = AgentTemplate(
        command=("opencode",), model_flag=None, default_model="ignored-model"
    )

    command = build_command_from_template(template=template, prompt="Prompt")

    assert command == ["opencode", "Prompt"]


def test_build_command_after_command_position_for_custom_template() -> None:
    template = AgentTemplate(
        command=("agent",),
        prompt_flag="--prompt",
        prompt_position="after_command",
        shared_flags=("--json",),
    )

    command = build_command_from_template(template=template, prompt="Prompt text")

    assert command == ["agent", "--prompt", "Prompt text", "--json"]


def test_build_command_explicit_model_overrides_default_and_keeps_reasoning_flags() -> (
    None
):
    template = AgentTemplate(
        command=("codex", "exec"),
        default_model="gpt-5.4",
        reasoning_effort="low",
        reasoning_effort_flag=("-c", "model_reasoning_effort={effort}"),
    )

    command = build_command_from_template(
        template=template, prompt="Prompt text", model="gpt-5.5"
    )

    assert command == [
        "codex",
        "exec",
        "--model",
        "gpt-5.5",
        "-c",
        "model_reasoning_effort=low",
        "Prompt text",
    ]
