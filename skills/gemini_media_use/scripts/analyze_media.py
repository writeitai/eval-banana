#!/usr/bin/env python3
"""Analyze an uploaded media file using Gemini multimodal generation."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"


def _get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _create_client(*, genai: Any) -> Any:
    """Create a Gemini client trying API keys, then ADC via Vertex AI.

    Auth precedence:
      1. GEMINI_API_KEY env var (AI Studio mode)
      2. GOOGLE_API_KEY env var (AI Studio mode)
      3. ADC via Vertex AI when GOOGLE_CLOUD_PROJECT is set; ADC must be
         configured (e.g. via `gcloud auth application-default login`).

    For Vertex AI, GOOGLE_CLOUD_LOCATION can override the default
    location of `us-central1`. analyze_media.py works in either mode,
    but Vertex AI mode requires a `gs://` URI rather than the file URI
    returned by the AI Studio File API.
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


def _build_file_part(*, genai: Any, file_uri: str, mime_type: str) -> object:
    types_module = getattr(genai, "types", None)
    part_class = getattr(types_module, "Part", None)
    from_uri = getattr(part_class, "from_uri", None)
    if callable(from_uri):
        return from_uri(file_uri=file_uri, mime_type=mime_type)
    return {"file_data": {"file_uri": file_uri, "mime_type": mime_type}}


def _extract_response_text(*, response: object) -> str | None:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text != "":
        return text
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze an uploaded media file using Gemini."
    )
    parser.add_argument(
        "--file-uri", required=True, help="Uploaded file URI from upload_media.py."
    )
    parser.add_argument(
        "--mime-type", required=True, help="MIME type of the uploaded file."
    )
    parser.add_argument(
        "--prompt", required=True, help="Analysis prompt for the model."
    )
    parser.add_argument(
        "--model", default=None, help="Gemini model name (default: auto-select)."
    )
    args = parser.parse_args()

    genai = _import_genai()
    model_name = args.model or _DEFAULT_MODEL

    try:
        client = _create_client(genai=genai)
        response = client.models.generate_content(
            model=model_name,
            contents=[
                _build_file_part(
                    genai=genai, file_uri=args.file_uri, mime_type=args.mime_type
                ),
                args.prompt,
            ],
        )
    except Exception as exc:  # pragma: no cover - depends on optional SDK/runtime
        logger.exception("Gemini media analysis failed")
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1

    result_text = _extract_response_text(response=response)
    if result_text is None:
        print("Analysis returned no text response.", file=sys.stderr)
        return 1
    print(result_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
