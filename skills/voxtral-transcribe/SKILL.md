---
name: voxtral-transcribe
description: Use Mistral Voxtral transcription for generated audio, write safe transcript artifacts, and evaluate them with eval-banana checks.
---

# Voxtral Transcribe

Use this skill when generated podcast or audio output needs transcription evidence for eval-banana checks. The usual goal is to compare the intended spoken text against a Voxtral transcript and prove that labels, headings, stage directions, markdown, SSML, or other production annotations were not spoken.

## Setup

- Install `mistralai` in the consuming project environment, not in eval-banana core.
- Provide `MISTRAL_API_KEY` at runtime through the shell, CI secret store, or harness environment. Never print, prompt for, commit, or persist the key.
- Default to `MISTRAL_TRANSCRIPTION_MODEL=voxtral-mini-latest` when unset. For pinned eval baselines, use `voxtral-mini-2602` after confirming current official Mistral docs.
- Do not make live transcription calls during documentation or unit-test validation. Use live calls only in an explicit consumer eval run.

## Current Mistral Pattern

Re-check official Mistral docs and the installed SDK before coding a consumer transcription snippet. As of 2026-05-15, the official docs show `client.audio.transcriptions.complete(...)` on `/v1/audio/transcriptions`, and SDK import examples vary between `from mistralai import Mistral` and `from mistralai.client import Mistral`.

Use the bare import first, then fall back if that is what the installed package exposes:

```python
try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral
```

Local-file transcription pattern:

```python
import json
import os
from pathlib import Path

try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral


def dump_response(response: object) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    return dict(response)


audio_path = Path("outputs/podcast.mp3")
artifact_dir = Path("eval_artifacts/transcripts")
artifact_dir.mkdir(parents=True, exist_ok=True)
json_path = artifact_dir / f"{audio_path.stem}.json"
txt_path = artifact_dir / f"{audio_path.stem}.txt"

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
model = os.getenv("MISTRAL_TRANSCRIPTION_MODEL", "voxtral-mini-latest")

with audio_path.open("rb") as f:
    response = client.audio.transcriptions.complete(
        model=model,
        file={"content": f, "file_name": audio_path.name},
        temperature=0,
    )

raw = dump_response(response)
json_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
text = raw.get("text") or getattr(response, "text", "")
txt_path.write_text(str(text).strip() + "\n", encoding="utf-8")
```

## Artifact Contract

There are two artifact classes:

- Per-check evidence: `${EVAL_BANANA_OUTPUT_DIR}/transcripts/<audio-stem>.json` and `${EVAL_BANANA_OUTPUT_DIR}/transcripts/<audio-stem>.txt`
- Stable handoff artifacts: `eval_artifacts/transcripts/<audio-stem>.json` and `eval_artifacts/transcripts/<audio-stem>.txt`

`EVAL_BANANA_OUTPUT_DIR` is scoped to the currently running check. It is useful for debug evidence, but it is not a stable cross-check handoff location. If a later check needs a transcript, write it to a concrete project-relative path such as `eval_artifacts/transcripts/podcast.txt` and have that check read that path.

Valid patterns:

- Same-check validation: one `deterministic` check transcribes, validates, and writes debug evidence under its own `EVAL_BANANA_OUTPUT_DIR`.
- Stable handoff: a harness step or consumer workflow writes `eval_artifacts/transcripts/<audio-stem>.{json,txt}`, then later checks read those project-relative files.
- Dual write: a project command writes stable artifacts for later checks and copies the same JSON/TXT files under `EVAL_BANANA_OUTPUT_DIR` for run evidence.

If `EVAL_BANANA_OUTPUT_DIR` is unavailable in a harness-only phase, write to `eval_artifacts/transcripts/<audio-stem>.{json,txt}` and report the absolute paths in the harness summary.

## Constraints

- Voxtral Mini Transcribe 2 is optimized for transcription, not chat over audio.
- Send exactly one audio source per transcription request: `file`, `file_url`, or `file_id`.
- Use `timestamp_granularities=["segment"]` or `["word"]` only when timing evidence is needed.
- Do not combine `timestamp_granularities` with `language` unless current official docs and the installed SDK prove compatibility.
- Avoid `context_bias` unless needed. If used, verify the current schema; API reference currently shows an array of strings, while some guide examples have drifted.
- Keep CI fixtures short. Current Mistral overview docs mention long-audio support up to 3 hours, but long podcast behavior, upload size, timeout, and cost should be live-verified before relying on it in CI.
- Budget for external transcription. Current Mistral model-card pricing is about USD 0.003 per minute for Voxtral Mini Transcribe 2.

## Evaluation Guidance

Compare transcripts against intended spoken text, not raw production scripts. Normalize conservatively for comparison: lowercase, collapse whitespace, and remove only punctuation that is not semantically meaningful. Keep raw transcript artifacts unchanged.

Fail when the transcript contains unspoken production markers, including:

- Speaker labels such as `Speaker 1:`, `Host:`, or `Guest:`
- Stage directions such as `[pause]`, `[laughs]`, or `(music fades)`
- Markdown headings, bullets, emphasis markers, or fenced-code markers
- SSML/XML tags such as `<speak>` or `<break>`
- Structural labels such as `Abstract`, `Methods`, or `Key takeaways` when they were not intended spoken words

Use deterministic checks for hard forbidden markers and artifact shape. Use a harness judge when semantic equivalence matters, such as whether technical claims from the intended spoken script survived transcription.

See `references/eval_patterns.md` for reusable eval-banana check patterns.
