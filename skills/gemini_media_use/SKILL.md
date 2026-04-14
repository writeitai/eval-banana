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
3. Application Default Credentials via Vertex AI mode -- requires both `GOOGLE_CLOUD_PROJECT` **and** an ADC file. `GOOGLE_CLOUD_LOCATION` overrides the default `us-central1`.

### Setup options

**Option A: AI Studio API key** (simplest, works everywhere including File API upload):

```bash
export GEMINI_API_KEY=<key-from-https://aistudio.google.com/apikey>
```

**Option B: Vertex AI via your Google account** (useful on a developer machine where you are signed in to Google Cloud):

```bash
gcloud auth application-default login   # NOT just `gcloud auth login`
export GOOGLE_CLOUD_PROJECT=<gcp-project-id>
# optional:
# export GOOGLE_CLOUD_LOCATION=europe-west4  # default us-central1
```

`gcloud auth login` authenticates the gcloud CLI only; the google-genai SDK reads the separate ADC file written by `application-default login` (typically `~/.config/gcloud/application_default_credentials.json`).

**Option C: service account key** (CI, servers):

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=<gcp-project-id>
```

If auth is misconfigured, the scripts print a targeted message naming exactly what is missing (e.g. "project set but ADC missing" vs "ADC present but project missing").

The bundled scripts depend on the `google-genai` package, not `google-generativeai`.

File API caveat: `upload_media.py` requires an API key (Option A). The Gemini File API is only available in AI Studio mode, not in Vertex AI mode. With Option B or C, upload media to a Google Cloud Storage bucket and pass the `gs://` URI directly to `analyze_media.py`.

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
