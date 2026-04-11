from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import httpx
from openai import OpenAI

from eval_banana.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexAuth:
    token: str
    account_id: str


class CodexAuthError(Exception):
    pass


def resolve_codex_auth_path(configured_path: str | None, *, cwd: str) -> Path:
    candidates: list[Path] = []
    cwd_path = Path(cwd).resolve()

    if configured_path:
        configured = Path(configured_path)
        if not configured.is_absolute():
            configured = (cwd_path / configured).resolve()
        candidates.append(configured)

    env_path = os.getenv("EVAL_BANANA_CODEX_AUTH_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser().resolve())

    codex_home = os.getenv("CODEX_HOME")
    if codex_home:
        candidates.append((Path(codex_home).expanduser() / "auth.json").resolve())

    candidates.append((Path.home() / ".codex" / "auth.json").resolve())

    for candidate in candidates:
        logger.debug("Checking Codex auth path %s", candidate)
        if candidate.is_file():
            return candidate

    return candidates[0]


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        msg = "Invalid Codex token format"
        raise CodexAuthError(msg)

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}")
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        msg = "Invalid Codex token payload"
        raise CodexAuthError(msg) from exc


def load_codex_auth(configured_path: str | None, *, cwd: str) -> CodexAuth:
    auth_path = resolve_codex_auth_path(configured_path=configured_path, cwd=cwd)
    if not auth_path.is_file():
        msg = f"Codex auth file not found at {auth_path}. Run `codex login`."
        raise CodexAuthError(msg)

    try:
        raw = json.loads(auth_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Invalid Codex auth JSON in {auth_path}"
        raise CodexAuthError(msg) from exc

    tokens = raw.get("tokens", {})
    token = ""
    if isinstance(tokens, dict):
        token = str(tokens.get("access_token") or "")
    if not token:
        token = os.getenv("OPENAI_API_KEY", "")
    if not token:
        msg = f"No access token found in {auth_path}. Run `codex login`."
        raise CodexAuthError(msg)

    payload = _decode_jwt_payload(token=token)
    exp = payload.get("exp")
    if isinstance(exp, int) and exp <= int(time.time()):
        msg = "Codex auth token is expired. Run `codex login`."
        raise CodexAuthError(msg)

    auth_claim = payload.get("https://api.openai.com/auth", {})
    account_id = ""
    if isinstance(auth_claim, dict):
        account_id = str(auth_claim.get("chatgpt_account_id") or "")
    if not account_id:
        msg = "Codex auth token is missing chatgpt_account_id"
        raise CodexAuthError(msg)

    return CodexAuth(token=token, account_id=account_id)


def resolve_openai_compat_api_key(config: Config) -> str:
    explicit_key = os.getenv("EVAL_BANANA_API_KEY") or config.api_key
    api_base = config.api_base or ""

    if "openrouter.ai" in api_base:
        return explicit_key or os.getenv("OPENROUTER_API_KEY", "")
    if "api.openai.com" in api_base:
        return explicit_key or os.getenv("OPENAI_API_KEY", "")
    return explicit_key or ""


def create_openai_compat_client(config: Config) -> OpenAI:
    api_key = resolve_openai_compat_api_key(config=config)
    if not api_key:
        if "openrouter.ai" in config.api_base:
            msg = "Missing API key for OpenRouter. Set EVAL_BANANA_API_KEY or OPENROUTER_API_KEY."
        elif "api.openai.com" in config.api_base:
            msg = (
                "Missing API key for OpenAI. Set EVAL_BANANA_API_KEY or OPENAI_API_KEY."
            )
        else:
            msg = "Missing API key for OpenAI-compatible endpoint. Set EVAL_BANANA_API_KEY."
        raise ValueError(msg)
    return OpenAI(api_key=api_key, base_url=config.api_base, timeout=None)


CODEX_BACKEND_BASE_URL = "https://chatgpt.com/backend-api"


def run_codex_judge_request(
    *, model: str, auth: CodexAuth, system_prompt: str, user_prompt: str
) -> str:
    base_url = CODEX_BACKEND_BASE_URL
    headers = {
        "Authorization": f"Bearer {auth.token}",
        "chatgpt-account-id": auth.account_id,
        "OpenAI-Beta": "responses=experimental",
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    }
    with httpx.Client(timeout=None) as client:
        response = client.post(f"{base_url}/responses", headers=headers, json=payload)
        response.raise_for_status()
        raw = response.json()

    if isinstance(raw.get("output_text"), str):
        return raw["output_text"]

    output = raw.get("output", [])
    if not isinstance(output, list):
        msg = "Codex response did not contain output text"
        raise CodexAuthError(msg)

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                return text

    msg = "Codex response did not contain output text"
    raise CodexAuthError(msg)
