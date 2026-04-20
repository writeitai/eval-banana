from __future__ import annotations

import os
from pathlib import Path

from eval_banana.harness.template import AgentTemplate
from eval_banana.harness.template import build_provider_env
from eval_banana.harness.template import build_template_env


def build_harness_env(
    *,
    template: AgentTemplate,
    model: str | None,
    harness_env: dict[str, str] | None,
    project_root: Path,
    run_id: str | None = None,
    run_output_dir: Path | None = None,
    harness_output_dir: Path | None = None,
    agent_type: str | None = None,
) -> dict[str, str]:
    """Assemble the full subprocess environment for a harness invocation."""
    effective_model = model if model is not None else template.default_model
    env = dict(os.environ)
    env.update(build_provider_env(template=template))
    env.update(harness_env or {})
    env.update(build_template_env(template=template, effective_model=effective_model))
    env["EVAL_BANANA_PROJECT_ROOT"] = str(project_root)
    if run_id is not None:
        env["EVAL_BANANA_RUN_ID"] = run_id
    if run_output_dir is not None:
        env["EVAL_BANANA_RUN_OUTPUT_DIR"] = str(run_output_dir)
    if harness_output_dir is not None:
        env["EVAL_BANANA_OUTPUT_DIR"] = str(harness_output_dir)
    if agent_type is not None:
        env["EVAL_BANANA_HARNESS_AGENT"] = agent_type
    return env
