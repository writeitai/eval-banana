from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
import json
import logging
from pathlib import Path
import subprocess

from eval_banana.config import Config
from eval_banana.harness.registry import build_command_from_template
from eval_banana.harness.registry import resolve_template
from eval_banana.harness.runner import build_harness_env
from eval_banana.harness.template import template_supports_model
from eval_banana.harness.template import template_supports_reasoning_effort
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import HarnessJudgeCheckDefinition
from eval_banana.reporter import safe_file_stem

logger = logging.getLogger(__name__)

_JUDGE_PROMPT_PREFIX = (
    "You are an evaluation judge. Read the following files and evaluate them "
    "according to the instructions below. Respond with ONLY a JSON object in this "
    'exact format:\n{"score": 0 or 1, "reason": "your reasoning in one or two sentences"}'
)


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    """Return elapsed wall-clock milliseconds between two UTC datetimes."""
    return int((completed - started).total_seconds() * 1000)


def _build_judge_prompt(*, check: HarnessJudgeCheckDefinition) -> str:
    """Assemble the full prompt sent to the harness agent for judging."""
    sections = [
        _JUDGE_PROMPT_PREFIX,
        "",
        "Check Description:",
        check.description,
        "",
        "Instructions:",
        check.instructions,
    ]
    return "\n".join(sections).strip()


def _persist_judge_prompt(*, output_dir: Path, check_id: str, prompt: str) -> Path:
    """Persist the exact judge input under its shared safe artifact stem."""

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_file_stem(text=check_id)
    prompt_path = output_dir / f"{stem}.prompt.txt"
    prompt_path.write_text(data=prompt, encoding="utf-8")
    return prompt_path


def _build_json_string_mask(*, text: str) -> list[bool]:
    """Return a boolean mask where ``True`` marks characters inside JSON strings.

    Used by :func:`_extract_last_verdict` so that braces inside quoted
    values are not treated as JSON structural delimiters.
    """
    mask = [False] * len(text)
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        mask[index] = in_string
        if escaped:
            escaped = False
            continue
        if in_string and char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
    return mask


def _parse_verdict_payload(*, text: str) -> tuple[int, str | None]:
    """Parse a JSON string into a ``(score, reason)`` tuple.

    Raises :class:`ValueError` if *text* is not a JSON object with a
    ``score`` of ``0`` or ``1``.
    """
    raw = json.loads(text)
    if not isinstance(raw, dict):
        msg = "Harness judge response must be a JSON object"
        raise ValueError(msg)

    score = raw.get("score")
    if score not in {0, 1}:
        msg = "Harness judge response score must be 0 or 1"
        raise ValueError(msg)

    reason = raw.get("reason")
    if reason is not None and not isinstance(reason, str):
        msg = "Harness judge response reason must be a string"
        raise ValueError(msg)
    return score, reason


def _extract_last_verdict(*, text: str) -> tuple[int, str | None]:
    """Find the **last** valid ``{"score": 0|1}`` JSON object in *text*.

    Agents may emit preamble, streaming events, or multiple JSON blobs.
    This function scans backwards with brace-depth tracking (respecting
    quoted strings via :func:`_build_json_string_mask`) so the final
    verdict wins.  Raises :class:`ValueError` if no valid verdict is found.
    """
    mask = _build_json_string_mask(text=text)
    for end_index in range(len(text) - 1, -1, -1):
        if text[end_index] != "}" or mask[end_index]:
            continue

        depth = 1
        for start_index in range(end_index - 1, -1, -1):
            if mask[start_index]:
                continue
            if text[start_index] == "}":
                depth += 1
                continue
            if text[start_index] != "{":
                continue
            depth -= 1
            if depth != 0:
                continue
            candidate = text[start_index : end_index + 1]
            try:
                return _parse_verdict_payload(text=candidate)
            except (json.JSONDecodeError, ValueError):
                break

    msg = (
        "Harness judge output did not contain a valid JSON verdict with "
        '"score": 0 or 1.'
    )
    raise ValueError(msg)


def _normalize_timeout_text(*, value: str | bytes | None) -> str:
    """Coerce ``TimeoutExpired.stdout``/``stderr`` (bytes, str, or None) to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_harness_judge_check(
    *,
    check: HarnessJudgeCheckDefinition,
    check_definition_sha256: str,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
) -> CheckResult:
    """Run a ``harness_judge`` check by invoking the harness agent subprocess.

    Builds a judging prompt from *check* instructions and target-file
    contents, invokes the configured harness agent via ``subprocess.run``
    (with the resolved harness timeout), and extracts the last valid
    ``{"score": 0|1, "reason": "..."}`` JSON from the agent's stdout.

    Returns a :class:`CheckResult` with ``status=passed`` when the agent exits
    zero and scores 1, ``status=failed`` when it exits zero and scores 0, and
    ``status=error`` for every non-zero exit, launch failure, timeout, or
    unparseable output. Result details record the resolved agent, model,
    nullable reasoning effort, and effective timeout.
    """
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()

    if config.harness_agent is None:
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail="Harness judge requires config.harness_agent to be set",
            details={"timeout_seconds": config.harness_timeout_seconds},
        )

    template = resolve_template(
        agent_type=config.harness_agent, user_templates=config.agent_templates
    )
    if config.harness_reasoning_effort is not None:
        template = replace(template, reasoning_effort=config.harness_reasoning_effort)

    command_model = check.model or config.harness_model
    effective_model = command_model or template.default_model
    effective_reasoning_effort = template.reasoning_effort
    unsupported: list[str] = []
    if effective_model is not None and not template_supports_model(template=template):
        unsupported.append(
            f"model {effective_model!r} (configure model_flag or model_env_vars)"
        )
    if effective_reasoning_effort is not None and not (
        template_supports_reasoning_effort(template=template)
    ):
        unsupported.append(
            "reasoning effort "
            f"{effective_reasoning_effort!r} (configure reasoning_effort_flag "
            "with an {effort} placeholder)"
        )
    if unsupported:
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=(
                f"Harness judge agent template {config.harness_agent!r} cannot "
                f"inject the selected {' and '.join(unsupported)}"
            ),
            details={
                "model": None,
                "agent_type": config.harness_agent,
                "reasoning_effort": None,
                "timeout_seconds": config.harness_timeout_seconds,
                "raw_response": "",
            },
        )
    details: dict[str, object] = {
        "model": effective_model,
        "agent_type": config.harness_agent,
        "reasoning_effort": effective_reasoning_effort,
        "timeout_seconds": config.harness_timeout_seconds,
        "raw_response": "",
    }

    try:
        prompt = _build_judge_prompt(check=check)
        _persist_judge_prompt(output_dir=output_dir, check_id=check.id, prompt=prompt)
        command = build_command_from_template(
            template=template, prompt=prompt, model=command_model
        )
        env = build_harness_env(
            template=template,
            model=command_model,
            harness_env=config.harness_env,
            project_root=project_root,
            agent_type=config.harness_agent,
        )
        completed_process = subprocess.run(
            args=command,
            capture_output=True,
            check=False,
            cwd=project_root,
            encoding="utf-8",
            env=env,
            errors="replace",
            text=True,
            timeout=config.harness_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_text = _normalize_timeout_text(value=exc.stdout)
        stderr_text = _normalize_timeout_text(value=exc.stderr)
        details["raw_response"] = stdout_text
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=(
                f"Harness judge subprocess timed out after "
                f"{config.harness_timeout_seconds} seconds"
            ),
            stdout=stdout_text,
            stderr=stderr_text,
            details=details,
        )
    except (FileNotFoundError, OSError, PermissionError) as exc:
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=f"{type(exc).__name__}: {exc}",
            details=details,
        )

    stdout_text = _normalize_timeout_text(value=completed_process.stdout)
    stderr_text = _normalize_timeout_text(value=completed_process.stderr)
    exit_code = completed_process.returncode
    details["raw_response"] = stdout_text

    try:
        score, reason = _extract_last_verdict(text=stdout_text)
    except ValueError as exc:
        completed = datetime.now(timezone.utc)
        error_detail = str(exc)
        if exit_code != 0:
            error_detail = f"Agent exited with code {exit_code}: {exc}"
        logger.error("Harness judge check %s failed: %s", check.id, error_detail)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=error_detail,
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            details=details,
        )

    completed = datetime.now(timezone.utc)
    if exit_code != 0:
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=f"Harness judge agent exited with code {exit_code}",
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            details=details,
        )
    return CheckResult(
        check_id=check.id,
        check_type=CheckType.harness_judge,
        check_definition_sha256=check_definition_sha256,
        description=check.description,
        source_path=str(source_path.resolve()),
        tags=check.tags,
        status=CheckStatus.passed if score == 1 else CheckStatus.failed,
        score=score,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        reason=reason,
        stdout=stdout_text,
        stderr=stderr_text,
        exit_code=exit_code,
        details=details,
    )
