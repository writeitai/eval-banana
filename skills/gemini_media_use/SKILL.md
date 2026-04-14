---
name: gemini_media_use
description: Use Gemini media APIs to upload and analyze image, audio, and video files when a task depends on understanding media content.
---

# gemini_media_use

Use this skill when a task depends on understanding media content from local image, audio, or video files and Gemini is the right tool for that job.

Prefer the Gemini File API for larger media files instead of trying to inline them directly in prompts. The bundled helper scripts are standalone utilities and are safe to call directly from this skill.

Authentication:

- Set `GEMINI_API_KEY`, or let the scripts fall back to `GOOGLE_API_KEY`.
- The bundled scripts depend on the `google-genai` package, not `google-generativeai`.

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

Generated agent skill directories such as `.claude/skills/` and `.codex/skills/` are build artifacts created by eval-banana's distribution step. They should usually be gitignored.
