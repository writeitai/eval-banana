from __future__ import annotations

from datetime import datetime
from datetime import timezone
import json
import logging
from pathlib import Path

from eval_banana.auth import create_openai_compat_client
from eval_banana.auth import load_codex_auth
from eval_banana.auth import run_codex_judge_request
from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import LlmJudgeCheckDefinition

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = (
    "You are an evaluation judge. Respond with JSON only in the exact shape "
    '{"score": 0|1, "reason": "..."} with a concise reason of one or two sentences.'
)


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _read_target_text(*, path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("Non-UTF-8 target encountered at %s", path)
        text = path.read_text(encoding="utf-8", errors="replace")

    if len(text) <= max_chars:
        return text

    logger.warning("Truncating target text for %s", path)
    return f"{text[:max_chars]}\n\n[TRUNCATED]"


def _build_user_prompt(
    *, check: LlmJudgeCheckDefinition, project_root: Path, max_chars: int
) -> str:
    sections = [
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


def _parse_llm_payload(*, text: str) -> tuple[int, str | None]:
    raw = json.loads(text)
    if not isinstance(raw, dict):
        msg = "LLM response must be a JSON object"
        raise ValueError(msg)

    score = raw.get("score")
    if score not in {0, 1}:
        msg = "LLM response score must be 0 or 1"
        raise ValueError(msg)

    reason = raw.get("reason")
    if reason is not None and not isinstance(reason, str):
        msg = "LLM response reason must be a string"
        raise ValueError(msg)
    return score, reason


def _extract_message_content(response: object) -> str:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        msg = "LLM response did not contain choices"
        raise ValueError(msg)
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        if parts:
            return "".join(parts)
    msg = "LLM response did not contain text content"
    raise ValueError(msg)


def run_llm_judge_check(
    *,
    check: LlmJudgeCheckDefinition,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
) -> CheckResult:
    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    raw_response = ""
    model_name = check.model or config.model
    details: dict[str, object] = {
        "model": model_name,
        "provider": config.provider,
        "raw_response": "",
        "target_count": len(check.target_paths),
    }

    try:
        user_prompt = _build_user_prompt(
            check=check, project_root=project_root, max_chars=config.llm_max_input_chars
        )

        if config.provider == "codex":
            auth = load_codex_auth(
                configured_path=config.codex_auth_path, cwd=config.cwd
            )
            raw_response = run_codex_judge_request(
                model=model_name,
                auth=auth,
                system_prompt=JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        else:
            client = create_openai_compat_client(config=config)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=None,
            )
            raw_response = _extract_message_content(response=response)
        details["raw_response"] = raw_response
        score, reason = _parse_llm_payload(text=raw_response)
    except Exception as exc:
        completed = datetime.now(timezone.utc)
        logger.error("LLM judge check %s failed: %s", check.id, exc)
        details["raw_response"] = raw_response
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.llm_judge,
            description=check.description,
            source_path=str(source_path.resolve()),
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=f"{type(exc).__name__}: {exc}",
            details=details,
        )

    completed = datetime.now(timezone.utc)
    return CheckResult(
        check_id=check.id,
        check_type=CheckType.llm_judge,
        description=check.description,
        source_path=str(source_path.resolve()),
        status=CheckStatus.passed if score == 1 else CheckStatus.failed,
        score=score,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        reason=reason,
        details=details,
    )
