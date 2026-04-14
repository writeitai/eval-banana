---
name: gemini_media_use
description: Use Gemini media APIs to upload and analyze image, audio, and video files when a task depends on understanding media content.
---

# gemini_media_use

Use this skill when a task depends on understanding media content from local image, audio, or video files and Gemini is the right tool for that job.

Prefer the Gemini File API for larger media files instead of trying to inline them directly in prompts. The bundled helper scripts are standalone utilities and are safe to call directly from this skill.

Authentication (tried in this order):

1. `GEMINI_API_KEY` env var (AI Studio mode).
2. `GOOGLE_API_KEY` env var (AI Studio mode).
3. Application Default Credentials (ADC) via Vertex AI mode -- requires `GOOGLE_CLOUD_PROJECT` to be set and ADC to be configured (`gcloud auth application-default login`). `GOOGLE_CLOUD_LOCATION` overrides the default `us-central1`.

The bundled scripts depend on the `google-genai` package, not `google-generativeai`.

File API caveat: `upload_media.py` requires an API key. The Gemini File API is only available in AI Studio mode, not in Vertex AI mode. If you only have ADC, upload media to a Google Cloud Storage bucket and pass the `gs://` URI directly to `analyze_media.py`.

Bundled tools:

- `scripts/upload_media.py`: Uploads a local file to the Gemini File API, waits until it is ready, and prints the uploaded file URI.
- `scripts/analyze_media.py`: Sends an uploaded Gemini file URI plus a prompt to a fast multimodal Gemini model and prints the response text.
- `references/supported_formats.md`: Quick reference for supported formats, practical limits, and when to upload versus inline.

Recommended workflow:

1. Upload the file with `scripts/upload_media.py`.
2. Capture the returned file URI.
3. Analyze the uploaded file with `scripts/analyze_media.py --file-uri ... --mime-type ... --prompt ...`.

Examples:

```bash
python scripts/upload_media.py ./assets/photo.jpg
python scripts/analyze_media.py --file-uri "..." --mime-type image/jpeg --prompt "Describe the scene and extract any visible text."
python scripts/analyze_media.py --file-uri "..." --mime-type audio/mpeg --prompt "Summarize the speaker's main points."
python scripts/analyze_media.py --file-uri "..." --mime-type video/mp4 --prompt "Provide a timestamped summary of the important events."
```

Windows note:

- On Windows, invoke the scripts as `python scripts/upload_media.py` and `python scripts/analyze_media.py` instead of relying on shebang execution.

Generated agent skill directories such as `.claude/skills/`, `.codex/skills/`, `.agents/skills/`, and `.gemini/skills/` are build artifacts created by eval-banana's distribution step. They should usually be gitignored.
