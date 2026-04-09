from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from eval_banana.auth import CodexAuthError
from eval_banana.auth import load_codex_auth
from eval_banana.auth import resolve_codex_auth_path
from eval_banana.auth import resolve_openai_compat_api_key
from eval_banana.config import Config


def test_provider_aware_key_resolution_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_BANANA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    key = resolve_openai_compat_api_key(
        Config(api_base="https://openrouter.ai/api/v1", provider="openai_compat")
    )

    assert key == "router-key"


def test_provider_aware_key_resolution_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_BANANA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    key = resolve_openai_compat_api_key(
        Config(api_base="https://api.openai.com/v1", provider="openai_compat")
    )

    assert key == "openai-key"


def test_provider_aware_key_resolution_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_BANANA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    key = resolve_openai_compat_api_key(
        Config(api_base="https://custom.example/v1", provider="openai_compat")
    )

    assert key == ""


def test_codex_auth_path_fallback_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit.json"
    explicit.write_text("{}", encoding="utf-8")
    env_path = tmp_path / "env.json"
    env_path.write_text("{}", encoding="utf-8")
    code_home = tmp_path / "code_home"
    (code_home).mkdir()
    (code_home / "auth.json").write_text("{}", encoding="utf-8")
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("EVAL_BANANA_CODEX_AUTH_PATH", str(env_path))
    monkeypatch.setenv("CODEX_HOME", str(code_home))

    explicit_result = resolve_codex_auth_path(str(explicit), cwd=str(tmp_path))
    env_result = resolve_codex_auth_path(None, cwd=str(tmp_path))

    monkeypatch.delenv("EVAL_BANANA_CODEX_AUTH_PATH")
    code_home_result = resolve_codex_auth_path(None, cwd=str(tmp_path))

    monkeypatch.delenv("CODEX_HOME")
    home_result = resolve_codex_auth_path(None, cwd=str(tmp_path))

    assert explicit_result == explicit
    assert env_result == env_path
    assert code_home_result == code_home / "auth.json"
    assert home_result == home / ".codex" / "auth.json"


def test_expired_jwt_handling(tmp_path: Path, make_jwt: Callable[..., str]) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        f'{{"tokens": {{"access_token": "{make_jwt(exp=1)}"}}}}', encoding="utf-8"
    )

    with pytest.raises(CodexAuthError):
        load_codex_auth(str(auth_path), cwd=str(tmp_path))
