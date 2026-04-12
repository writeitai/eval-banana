from __future__ import annotations

from datetime import datetime
from datetime import timezone
import logging
import os
from pathlib import Path
import subprocess
from typing import Literal

from eval_banana.harness.registry import build_command_from_template
from eval_banana.harness.template import AgentTemplate
from eval_banana.harness.template import build_provider_env
from eval_banana.harness.template import build_template_env
from eval_banana.models import HarnessResult
from eval_banana.models import HarnessStatus

logger = logging.getLogger(__name__)


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _text_size_bytes(*, text: str) -> int:
    return len(text.encode("utf-8"))


def build_harness_result(
    *,
    agent_type: str,
    command: list[str],
    working_directory: Path,
    status: HarnessStatus,
    started_at: str,
    completed_at: str,
    duration_ms: int,
    model: str | None,
    reasoning_effort: str | None,
    prompt_source: Literal["inline", "file"] | None,
    prompt_file: str | None,
    exit_code: int | None = None,
    error_detail: str | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    prompt_artifact_path: str | None = None,
    result_path: str | None = None,
    stdout_bytes: int | None = None,
    stderr_bytes: int | None = None,
) -> HarnessResult:
    """Construct a ``HarnessResult`` Pydantic model from individual fields."""
    return HarnessResult(
        agent_type=agent_type,
        command=command,
        working_directory=str(working_directory),
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        model=model,
        reasoning_effort=reasoning_effort,
        prompt_source=prompt_source,
        prompt_file=prompt_file,
        exit_code=exit_code,
        error_detail=error_detail,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        prompt_artifact_path=prompt_artifact_path,
        result_path=result_path,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )


def run_harness(
    *,
    agent_type: str,
    template: AgentTemplate,
    prompt: str,
    prompt_source: Literal["inline", "file"],
    prompt_file: str | None,
    project_root: Path,
    run_id: str,
    run_output_dir: Path,
    model: str | None = None,
    harness_env: dict[str, str] | None = None,
) -> HarnessResult:
    """Execute a harness agent synchronously and return the result.

    Builds the command from the template, assembles the subprocess
    environment, runs the agent via ``subprocess.run()``, captures
    stdout/stderr, and writes all artifacts to ``run_output_dir/harness/``.
    """
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    harness_output_dir = run_output_dir / "harness"
    harness_output_dir.mkdir(parents=True, exist_ok=True)

    prompt_artifact_path = Path("harness") / "prompt.txt"
    stdout_path = Path("harness") / "stdout.txt"
    stderr_path = Path("harness") / "stderr.txt"
    result_path = Path("harness") / "result.json"

    (run_output_dir / prompt_artifact_path).write_text(prompt, encoding="utf-8")

    command = build_command_from_template(template=template, prompt=prompt, model=model)
    effective_model = model if model is not None else template.default_model
    env = dict(os.environ)
    env.update(build_provider_env(template=template))
    env.update(harness_env or {})
    env.update(build_template_env(template=template, effective_model=effective_model))
    env["EVAL_BANANA_PROJECT_ROOT"] = str(project_root)
    env["EVAL_BANANA_RUN_ID"] = run_id
    env["EVAL_BANANA_RUN_OUTPUT_DIR"] = str(run_output_dir)
    env["EVAL_BANANA_OUTPUT_DIR"] = str(harness_output_dir)
    env["EVAL_BANANA_HARNESS_AGENT"] = agent_type

    stdout_text = ""
    stderr_text = ""

    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            check=False,
            cwd=project_root,
            env=env,
            text=True,
        )
        stdout_text = completed_process.stdout
        stderr_text = completed_process.stderr
        status = (
            HarnessStatus.succeeded
            if completed_process.returncode == 0
            else HarnessStatus.failed
        )
        exit_code = completed_process.returncode
        error_detail = None
    except (FileNotFoundError, OSError, PermissionError) as exc:
        status = HarnessStatus.error
        exit_code = None
        error_detail = str(exc)

    (run_output_dir / stdout_path).write_text(stdout_text, encoding="utf-8")
    (run_output_dir / stderr_path).write_text(stderr_text, encoding="utf-8")

    completed = datetime.now(timezone.utc)
    result = build_harness_result(
        agent_type=agent_type,
        command=command,
        working_directory=project_root,
        status=status,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        model=effective_model,
        reasoning_effort=template.reasoning_effort,
        prompt_source=prompt_source,
        prompt_file=prompt_file,
        exit_code=exit_code,
        error_detail=error_detail,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        prompt_artifact_path=str(prompt_artifact_path),
        result_path=str(result_path),
        stdout_bytes=_text_size_bytes(text=stdout_text),
        stderr_bytes=_text_size_bytes(text=stderr_text),
    )
    (run_output_dir / result_path).write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    return result
