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
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import HarnessJudgeCheckDefinition

logger = logging.getLogger(__name__)

_HARNESS_JUDGE_TIMEOUT_SECONDS = 300
_JUDGE_PROMPT_PREFIX = (
    "You are an evaluation judge. Read the following files and evaluate them "
    "according to the instructions below. Respond with ONLY a JSON object in this "
    'exact format:\n{"score": 0 or 1, "reason": "your reasoning in one or two sentences"}'
)


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    """Return elapsed wall-clock milliseconds between two UTC datetimes."""
    return int((completed - started).total_seconds() * 1000)


def _read_target_text(*, path: Path, max_chars: int) -> str:
    """Read a target file as UTF-8, optionally truncating to *max_chars*.

    When *max_chars* is ``<= 0`` truncation is disabled and the full content
    is returned.  Non-UTF-8 bytes are replaced with the Unicode replacement
    character rather than raising.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("Non-UTF-8 target encountered at %s", path)
        text = path.read_text(encoding="utf-8", errors="replace")

    if max_chars <= 0 or len(text) <= max_chars:
        return text

    logger.warning("Truncating target text for %s", path)
    return f"{text[:max_chars]}\n\n[TRUNCATED]"


def _build_judge_prompt(
    *, check: HarnessJudgeCheckDefinition, project_root: Path, max_chars: int
) -> str:
    """Assemble the full prompt sent to the harness agent for judging.

    The prompt contains the judge preamble, the check description and
    instructions, and the content of every target file (optionally
    truncated by *max_chars*).
    """
    sections = [
        _JUDGE_PROMPT_PREFIX,
        "",
        "Check Description:",
        check.description,
        "",
        "Instructions:",
        check.instructions,
        "",
        "Target Files:",
    ]
    for target in check.target_paths:
        resolved = (project_root / target).resolve()
        sections.extend(
            [
                f"--- BEGIN FILE: {target} ({resolved}) ---",
                _read_target_text(path=resolved, max_chars=max_chars),
                f"--- END FILE: {target} ---",
                "",
            ]
        )
    return "\n".join(sections).strip()


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
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
) -> CheckResult:
    """Run a ``harness_judge`` check by invoking the harness agent subprocess.

    Builds a judging prompt from *check* instructions and target-file
    contents, invokes the configured harness agent via ``subprocess.run``
    (with a 300 s timeout), and extracts the last valid
    ``{"score": 0|1, "reason": "..."}`` JSON from the agent's stdout.

    Returns a :class:`CheckResult` with ``status=passed`` when the agent
    scores 1, ``status=failed`` for 0, and ``status=error`` for crashes,
    timeouts, or unparseable output.
    """
    del output_dir
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()

    if config.harness_agent is None:
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail="Harness judge requires config.harness_agent to be set",
            details={"target_count": len(check.target_paths)},
        )

    template = resolve_template(
        agent_type=config.harness_agent, user_templates=config.agent_templates
    )
    if config.harness_reasoning_effort is not None:
        template = replace(template, reasoning_effort=config.harness_reasoning_effort)

    command_model = check.model or config.harness_model
    effective_model = command_model or template.default_model
    details: dict[str, object] = {
        "model": effective_model,
        "agent_type": config.harness_agent,
        "raw_response": "",
        "target_count": len(check.target_paths),
    }

    try:
        prompt = _build_judge_prompt(
            check=check, project_root=project_root, max_chars=config.llm_max_input_chars
        )
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
            command,
            capture_output=True,
            check=False,
            cwd=project_root,
            env=env,
            text=True,
            timeout=_HARNESS_JUDGE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_text = _normalize_timeout_text(value=exc.stdout)
        stderr_text = _normalize_timeout_text(value=exc.stderr)
        details["raw_response"] = stdout_text
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.harness_judge,
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
                f"{_HARNESS_JUDGE_TIMEOUT_SECONDS} seconds"
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

    stdout_text = completed_process.stdout
    stderr_text = completed_process.stderr
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
    return CheckResult(
        check_id=check.id,
        check_type=CheckType.harness_judge,
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
