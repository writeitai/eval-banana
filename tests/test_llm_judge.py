from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from eval_banana.auth import CodexAuth
from eval_banana.auth import create_openai_compat_client
from eval_banana.auth import run_codex_judge_request
from eval_banana.config import Config
from eval_banana.models import LlmJudgeCheckDefinition
from eval_banana.runners.llm_judge import run_llm_judge_check


def _fake_openai_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_openai_compatible_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install with uv sync", encoding="utf-8")

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content='{"score": 1, "reason": "Looks good."}'
                                )
                            )
                        ]
                    )
                )
            )

    monkeypatch.setattr(
        "eval_banana.runners.llm_judge.create_openai_compat_client",
        lambda config: FakeClient(),
    )
    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="readme",
        type="llm_judge",
        description="desc",
        target_paths=["README.md"],
        instructions="Judge it",
    )

    result = run_llm_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "readme.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "passed"
    assert result.reason == "Looks good."


def test_malformed_json_response_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_: SimpleNamespace(
                        choices=[
                            SimpleNamespace(message=SimpleNamespace(content="not json"))
                        ]
                    )
                )
            )

    monkeypatch.setattr(
        "eval_banana.runners.llm_judge.create_openai_compat_client",
        lambda config: FakeClient(),
    )
    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="bad_json",
        type="llm_judge",
        description="desc",
        target_paths=["README.md"],
        instructions="Judge it",
    )

    result = run_llm_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "readme.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"


def test_invalid_score_payload_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content='{"score": 2, "reason": "Nope"}'
                                )
                            )
                        ]
                    )
                )
            )

    monkeypatch.setattr(
        "eval_banana.runners.llm_judge.create_openai_compat_client",
        lambda config: FakeClient(),
    )
    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="bad_score",
        type="llm_judge",
        description="desc",
        target_paths=["README.md"],
        instructions="Judge it",
    )

    result = run_llm_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "readme.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"


def test_missing_credentials_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runners.llm_judge.create_openai_compat_client",
        lambda config: (_ for _ in ()).throw(ValueError("missing key")),
    )
    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="missing_key",
        type="llm_judge",
        description="desc",
        target_paths=["README.md"],
        instructions="Judge it",
    )

    result = run_llm_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "readme.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "error"
    assert "missing key" in (result.error_detail or "")


def test_codex_request_path_with_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            status_code=200, json={"output_text": '{"score": 1, "reason": "fine"}'}
        )

    transport = httpx.MockTransport(handler)

    def fake_client(*args: object, **kwargs: object) -> httpx.Client:
        return original_client(transport=transport)

    monkeypatch.setattr("eval_banana.auth.httpx.Client", fake_client)

    text = run_codex_judge_request(
        model="gpt-5.4",
        auth=CodexAuth(token="token", account_id="acct"),
        system_prompt="sys",
        user_prompt="user",
    )

    assert text == '{"score": 1, "reason": "fine"}'
    assert captured["headers"]["chatgpt-account-id"] == "acct"


def test_missing_target_file_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    source_path = tmp_path / "eval_checks" / "check.yaml"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.touch()

    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="missing_target",
        type="llm_judge",
        description="check missing file",
        target_paths=["nonexistent.txt"],
        instructions="Does it exist?",
    )
    result = run_llm_judge_check(
        check=check,
        source_path=source_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )
    assert result.status.value == "error"
    assert result.score == 0
    assert "FileNotFoundError" in (result.error_detail or "")


def test_codex_uses_httpx_client_with_timeout_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    real_client_cls = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200, json={"output_text": '{"score": 1, "reason": "ok"}'}
        )

    def fake_client(*args: object, **kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        return real_client_cls(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", fake_client)

    run_codex_judge_request(
        model="gpt-5.4",
        auth=CodexAuth(token="token", account_id="acct"),
        system_prompt="sys",
        user_prompt="user",
    )

    assert captured["timeout"] is None


def test_codex_post_does_not_pass_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post_kwargs: dict[str, object] = {}
    real_client_cls = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200, json={"output_text": '{"score": 1, "reason": "ok"}'}
        )

    def fake_client(*args: object, **kwargs: object) -> httpx.Client:
        client = real_client_cls(transport=httpx.MockTransport(handler))
        real_post = client.post

        def spying_post(url: str, **post_call_kwargs: object) -> httpx.Response:
            post_kwargs.update(post_call_kwargs)
            return real_post(url, **post_call_kwargs)  # type: ignore[arg-type]

        client.post = spying_post  # type: ignore[method-assign]
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)

    run_codex_judge_request(
        model="gpt-5.4",
        auth=CodexAuth(token="token", account_id="acct"),
        system_prompt="sys",
        user_prompt="user",
    )

    assert "timeout" not in post_kwargs


def test_openai_compat_client_has_timeout_none(
    monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("eval_banana.auth.OpenAI", FakeOpenAI)

    create_openai_compat_client(
        config=make_config(api_key="k", api_base="https://example.com/v1")
    )

    assert captured["timeout"] is None


def test_chat_completions_called_with_timeout_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    (tmp_path / "README.md").write_text("Install", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return _fake_openai_response('{"score": 1, "reason": "ok"}')

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "eval_banana.runners.llm_judge.create_openai_compat_client",
        lambda *, config: FakeClient(),
    )
    check = LlmJudgeCheckDefinition(
        schema_version=1,
        id="timeout_none",
        type="llm_judge",
        description="desc",
        target_paths=["README.md"],
        instructions="Judge it",
    )

    result = run_llm_judge_check(
        check=check,
        source_path=tmp_path / "eval_checks" / "readme.yaml",
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
    )

    assert result.status == "passed"
    assert captured["timeout"] is None
