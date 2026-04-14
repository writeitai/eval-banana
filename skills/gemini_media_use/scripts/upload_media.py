#!/usr/bin/env python3
"""Upload a local file to the Gemini File API and print the file URI."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _create_client(*, genai: Any) -> Any:
    """Create a Gemini client trying API keys, then ADC via Vertex AI.

    Auth precedence:
      1. GEMINI_API_KEY env var (AI Studio mode)
      2. GOOGLE_API_KEY env var (AI Studio mode)
      3. ADC via Vertex AI when GOOGLE_CLOUD_PROJECT is set; ADC must be
         configured (e.g. via `gcloud auth application-default login`).

    Note: the File API only works in AI Studio mode. Vertex AI mode does
    not support `client.files.upload()`. Callers that need uploads must
    set an API key.
    """
    api_key = _get_api_key()
    if api_key:
        return genai.Client(api_key=api_key)

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        return genai.Client(vertexai=True, project=project, location=location)

    print(
        "No Gemini auth configured. Set one of:\n"
        "  - GEMINI_API_KEY (AI Studio)\n"
        "  - GOOGLE_API_KEY (AI Studio)\n"
        "  - GOOGLE_CLOUD_PROJECT (Vertex AI via Application Default Credentials;\n"
        "    run `gcloud auth application-default login` first).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _import_genai() -> Any:
    try:
        google_module = importlib.import_module("google")
        genai_module = getattr(google_module, "genai", None)
        if genai_module is not None:
            return genai_module
    except ImportError:
        pass

    try:
        return importlib.import_module("google.genai")
    except ImportError as exc:
        print(
            "Missing dependency 'google-genai'. Install it with: pip install google-genai",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _normalize_state(*, state: object) -> str | None:
    if state is None:
        return None
    if isinstance(state, str):
        return state.upper()
    state_name = getattr(state, "name", None)
    if isinstance(state_name, str):
        return state_name.upper()
    return str(state).rsplit(".", maxsplit=1)[-1].upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload a local file to the Gemini File API."
    )
    parser.add_argument("file_path", help="Path to the local file to upload.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between status polls (default: 5.0).",
    )
    parser.add_argument(
        "--max-wait-seconds",
        type=float,
        default=300.0,
        help="Maximum seconds to wait for upload processing (default: 300).",
    )
    args = parser.parse_args()

    file_path = Path(args.file_path).expanduser().resolve()
    if not file_path.is_file():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1

    if not _get_api_key():
        print(
            "upload_media.py requires an API key (GEMINI_API_KEY or GOOGLE_API_KEY).\n"
            "The Gemini File API only works in AI Studio mode, not Vertex AI/ADC.\n"
            "If you only have ADC, upload your media to GCS and pass the gs:// URI\n"
            "directly to analyze_media.py instead.",
            file=sys.stderr,
        )
        return 1

    genai = _import_genai()

    try:
        client = _create_client(genai=genai)
        uploaded_file = client.files.upload(path=str(file_path))
    except Exception as exc:  # pragma: no cover - depends on optional SDK/runtime
        logger.exception("Gemini file upload failed")
        print(f"Upload failed: {exc}", file=sys.stderr)
        return 1

    deadline = time.monotonic() + args.max_wait_seconds
    while True:
        state = _normalize_state(state=getattr(uploaded_file, "state", None))
        if state in {None, "ACTIVE", "READY", "SUCCEEDED"}:
            break
        if state in {"FAILED", "ERROR"}:
            print(f"Uploaded file entered terminal state: {state}", file=sys.stderr)
            return 1
        if time.monotonic() >= deadline:
            print(
                f"Timed out waiting for uploaded file to become ready: {file_path}",
                file=sys.stderr,
            )
            return 1

        file_name = getattr(uploaded_file, "name", None)
        if not isinstance(file_name, str) or file_name == "":
            print(
                "Upload succeeded but returned no file name for polling.",
                file=sys.stderr,
            )
            return 1

        time.sleep(args.poll_interval)
        try:
            uploaded_file = client.files.get(name=file_name)
        except Exception as exc:  # pragma: no cover - depends on optional SDK/runtime
            logger.exception("Gemini file polling failed")
            print(f"Polling failed: {exc}", file=sys.stderr)
            return 1

    file_uri = getattr(uploaded_file, "uri", None)
    if not isinstance(file_uri, str) or file_uri == "":
        print("Upload completed but no file URI was returned.", file=sys.stderr)
        return 1

    print(file_uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
