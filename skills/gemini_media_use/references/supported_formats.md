# Supported Formats

The Gemini media workflow in this skill is intended for image, audio, and video files that are easier to upload once and reference by URI during analysis.

## Image formats

- PNG
- JPEG
- WebP
- HEIC
- HEIF

## Audio formats

- WAV
- MP3
- AIFF
- AAC
- FLAC
- OGG

## Video formats

- MP4
- MPEG
- MOV
- AVI
- FLV
- MPG
- WEBM
- WMV
- 3GPP

## Practical limits

- File API uploads are the preferred path for larger media files.
- Uploaded files are commonly documented with a size limit up to 2 GB.
- Video guidance is roughly up to 1 hour without audio, or around 45 minutes with audio.
- Very long audio and video inputs are best handled as uploads instead of inline content.
- Keep prompts concise and task-specific so the model spends context on the media, not instructions.

## Storage and auth notes

- Uploaded Gemini File API assets are temporary and are commonly retained for about 48 hours.
- Auth precedence: `GEMINI_API_KEY` -> `GOOGLE_API_KEY` -> Application Default Credentials (Vertex AI mode, requires `GOOGLE_CLOUD_PROJECT` and `gcloud auth application-default login`).
- The Gemini File API only works in AI Studio mode, so `upload_media.py` requires an API key. With ADC only, upload media to GCS and pass the `gs://` URI directly to `analyze_media.py`.
- These scripts expect the modern `google-genai` SDK, not `google-generativeai`.

## Upload vs inline

- Inline is fine for a single small image.
- Upload first for audio, video, or larger image batches.
- Reuse the returned file URI for repeated analysis prompts instead of uploading the same file again.
