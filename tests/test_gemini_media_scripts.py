from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "gemini_media_use" / "scripts"
)


def _load_script_module(*, script_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_test_skill_{script_name}", _SCRIPTS_DIR / f"{script_name}.py"
    )
    if spec is None or spec.loader is None:
        msg = f"Could not load script: {script_name}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def upload_media_module() -> ModuleType:
    return _load_script_module(script_name="upload_media")


@pytest.fixture
def analyze_media_module() -> ModuleType:
    return _load_script_module(script_name="analyze_media")


class _FakeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeGenai:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def Client(self, **kwargs: object) -> _FakeClient:  # noqa: N802
        self.calls.append(kwargs)
        return _FakeClient(**kwargs)


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ]:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("script_name", ["upload_media", "analyze_media"])
def test_create_client_prefers_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch, script_name: str
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-project")

    module = _load_script_module(script_name=script_name)
    fake_genai = _FakeGenai()

    client = module._create_client(genai=fake_genai)

    assert isinstance(client, _FakeClient)
    assert fake_genai.calls == [{"api_key": "gemini-key"}]


@pytest.mark.parametrize("script_name", ["upload_media", "analyze_media"])
def test_create_client_falls_back_to_google_api_key(
    monkeypatch: pytest.MonkeyPatch, script_name: str
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-project")

    module = _load_script_module(script_name=script_name)
    fake_genai = _FakeGenai()

    module._create_client(genai=fake_genai)

    assert fake_genai.calls == [{"api_key": "google-key"}]


@pytest.mark.parametrize("script_name", ["upload_media", "analyze_media"])
def test_create_client_falls_back_to_vertex_adc(
    monkeypatch: pytest.MonkeyPatch, script_name: str
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")

    module = _load_script_module(script_name=script_name)
    fake_genai = _FakeGenai()

    module._create_client(genai=fake_genai)

    assert fake_genai.calls == [
        {"vertexai": True, "project": "my-project", "location": "us-central1"}
    ]


@pytest.mark.parametrize("script_name", ["upload_media", "analyze_media"])
def test_create_client_honors_google_cloud_location(
    monkeypatch: pytest.MonkeyPatch, script_name: str
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")

    module = _load_script_module(script_name=script_name)
    fake_genai = _FakeGenai()

    module._create_client(genai=fake_genai)

    assert fake_genai.calls == [
        {"vertexai": True, "project": "my-project", "location": "europe-west4"}
    ]


@pytest.mark.parametrize("script_name", ["upload_media", "analyze_media"])
def test_create_client_raises_systemexit_without_any_auth(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    script_name: str,
) -> None:
    _clear_auth_env(monkeypatch)

    module = _load_script_module(script_name=script_name)
    fake_genai = _FakeGenai()

    with pytest.raises(SystemExit):
        module._create_client(genai=fake_genai)

    captured = capsys.readouterr()
    assert "GEMINI_API_KEY" in captured.err
    assert "GOOGLE_API_KEY" in captured.err
    assert "GOOGLE_CLOUD_PROJECT" in captured.err


def test_upload_media_rejects_adc_only_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    upload_media_module: ModuleType,
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    sample_file = tmp_path / "sample.png"
    sample_file.write_bytes(b"fake-content")

    monkeypatch.setattr(sys, "argv", ["upload_media.py", str(sample_file)])

    def _fail_import() -> Any:
        msg = "_import_genai must not be called when ADC-only is rejected early"
        raise AssertionError(msg)

    monkeypatch.setattr(upload_media_module, "_import_genai", _fail_import)

    exit_code = upload_media_module.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Gemini File API" in captured.err
    assert "AI Studio" in captured.err
    assert "gs://" in captured.err


def test_upload_media_accepts_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, upload_media_module: ModuleType
) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    sample_file = tmp_path / "sample.png"
    sample_file.write_bytes(b"fake-content")

    monkeypatch.setattr(sys, "argv", ["upload_media.py", str(sample_file)])

    class _FakeFiles:
        def upload(self, *, path: str) -> object:
            return type(
                "Uploaded",
                (),
                {"state": "ACTIVE", "uri": "files/123", "name": "files/123"},
            )()

    class _FakeUploadClient:
        files = _FakeFiles()

    fake_genai_with_upload = type(
        "FakeGenai", (), {"Client": staticmethod(lambda **kwargs: _FakeUploadClient())}
    )()

    monkeypatch.setattr(
        upload_media_module, "_import_genai", lambda: fake_genai_with_upload
    )

    exit_code = upload_media_module.main()

    assert exit_code == 0
