from __future__ import annotations

import logging

import pytest

from eval_banana.harness import template as harness_template


def test_default_agent_templates_match_expected_values() -> None:
    assert harness_template.DEFAULT_AGENT_TEMPLATES["codex"].command == (
        "codex",
        "exec",
    )
    assert harness_template.DEFAULT_AGENT_TEMPLATES["codex"].default_model == "gpt-5.4"
    assert harness_template.DEFAULT_AGENT_TEMPLATES["gemini"].prompt_flag == "-p"
    assert harness_template.DEFAULT_AGENT_TEMPLATES["claude"].shared_flags[0] == "-p"
    assert harness_template.DEFAULT_AGENT_TEMPLATES["openhands"].model_flag is None


def test_build_template_env_injects_effective_model() -> None:
    template = harness_template.AgentTemplate(
        command=("claude",),
        model_env_vars=("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL"),
    )

    env = harness_template.build_template_env(
        template=template, effective_model="claude-sonnet"
    )

    assert env == {
        "ANTHROPIC_MODEL": "claude-sonnet",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-sonnet",
    }


def test_render_reasoning_effort_flags_uses_placeholder_replacement() -> None:
    template = harness_template.AgentTemplate(
        command=("codex",),
        reasoning_effort_flag=("-c", "model_reasoning_effort={effort}"),
    )

    flags = harness_template.render_reasoning_effort_flags(
        template=template, reasoning_effort="medium"
    )

    assert flags == ["-c", "model_reasoning_effort=medium"]


def test_build_provider_env_resolves_env_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = harness_template.AgentTemplate(
        command=("claude",),
        provider_env=(
            ("ANTHROPIC_AUTH_TOKEN", "{env:OPENROUTER_API_KEY}"),
            ("STATIC_VALUE", "plain"),
        ),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")

    env = harness_template.build_provider_env(template=template)

    assert env == {"ANTHROPIC_AUTH_TOKEN": "secret", "STATIC_VALUE": "plain"}


def test_build_provider_env_warns_once_for_missing_env(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness_template._WARNED_MISSING_ENV_VARS.clear()
    template = harness_template.AgentTemplate(
        command=("claude",),
        provider_env=(("ANTHROPIC_AUTH_TOKEN", "{env:MISSING_API_KEY}"),),
    )

    with caplog.at_level(logging.WARNING):
        first = harness_template.build_provider_env(template=template)
        second = harness_template.build_provider_env(template=template)

    assert first == {"ANTHROPIC_AUTH_TOKEN": ""}
    assert second == {"ANTHROPIC_AUTH_TOKEN": ""}
    assert caplog.text.count("MISSING_API_KEY") == 1
