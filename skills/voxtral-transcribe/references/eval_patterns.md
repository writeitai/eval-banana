# Voxtral Eval Patterns

These examples target the current eval-banana check surface: `deterministic` and `harness_judge`. Older docs or plans may mention `task_based` or `llm_judge`; for this repo version, those are not valid check types.

## Pattern Selection

| Pattern | Use when | Artifact rule |
|---|---|---|
| Same-check transcription and validation | One check can call Voxtral and make hard assertions immediately | Write debug copies under that check's `EVAL_BANANA_OUTPUT_DIR` |
| Stable handoff | A harness step or project workflow transcribes before checks run | Write `eval_artifacts/transcripts/<audio-stem>.{json,txt}` |
| Dual write | You need later checks and per-run evidence | Write stable artifacts, then copy them under `EVAL_BANANA_OUTPUT_DIR` |

`EVAL_BANANA_OUTPUT_DIR` is per-check evidence. Do not expect a later check to discover a previous check's dynamic output directory. For cross-check handoff, use stable project-relative paths.

## Same-Check Deterministic Transcription

Use this only for explicit live eval runs. Do not run it in normal unit tests or docs validation because it needs network and `MISTRAL_API_KEY`.

```yaml
schema_version: 1
id: podcast_transcribes_without_labels
type: deterministic
description: Transcribe podcast audio and fail if obvious production labels were voiced.
script: |
  import json
  import os
  import re
  import shutil
  import sys
  from pathlib import Path

  try:
      from mistralai import Mistral
  except ImportError:
      from mistralai.client import Mistral

  def dump_response(response):
      if hasattr(response, "model_dump"):
          return response.model_dump()
      if hasattr(response, "dict"):
          return response.dict()
      return dict(response)

  ctx = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
  project_root = Path(ctx["project_root"])
  audio_path = project_root / "outputs/podcast.mp3"
  evidence_dir = Path(ctx["output_dir"]) / "transcripts"
  evidence_dir.mkdir(parents=True, exist_ok=True)

  client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
  model = os.getenv("MISTRAL_TRANSCRIPTION_MODEL", "voxtral-mini-latest")
  with audio_path.open("rb") as f:
      response = client.audio.transcriptions.complete(
          model=model,
          file={"content": f, "file_name": audio_path.name},
          temperature=0,
      )

  raw = dump_response(response)
  text = str(raw.get("text") or getattr(response, "text", "")).strip()
  json_path = evidence_dir / f"{audio_path.stem}.json"
  txt_path = evidence_dir / f"{audio_path.stem}.txt"
  json_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
  txt_path.write_text(text + "\n", encoding="utf-8")

  normalized = re.sub(r"\s+", " ", text).lower()
  forbidden = [
      r"\bspeaker\s+\d+\s*:",
      r"\bhost\s*:",
      r"\bguest\s*:",
      r"\[[^\]]*(pause|laugh|music)[^\]]*\]",
      r"<\s*/?\s*(speak|break|prosody)\b",
      r"\bkey takeaways\s*:",
  ]
  for pattern in forbidden:
      if re.search(pattern, normalized):
          print(f"forbidden spoken marker matched: {pattern}", file=sys.stderr)
          sys.exit(1)

  stable_dir = project_root / "eval_artifacts/transcripts"
  stable_dir.mkdir(parents=True, exist_ok=True)
  shutil.copy2(json_path, stable_dir / json_path.name)
  shutil.copy2(txt_path, stable_dir / txt_path.name)
```

## Stable Handoff Writer

If transcription happens in a harness step or project command before `eval-banana run`, write stable project-relative artifacts:

```python
from pathlib import Path

audio_path = Path("outputs/podcast.mp3")
artifact_dir = Path("eval_artifacts/transcripts")
artifact_dir.mkdir(parents=True, exist_ok=True)
json_path = artifact_dir / f"{audio_path.stem}.json"
txt_path = artifact_dir / f"{audio_path.stem}.txt"
```

Later checks should read those concrete paths from `project_root`, not from another check's `EVAL_BANANA_OUTPUT_DIR`.

## Dual-Write Copy

When a check already wrote stable artifacts, copy them into its per-check evidence directory:

```python
import json
import shutil
from pathlib import Path

ctx = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
project_root = Path(ctx["project_root"])
stable_dir = project_root / "eval_artifacts/transcripts"
evidence_dir = Path(ctx["output_dir"]) / "transcripts"
evidence_dir.mkdir(parents=True, exist_ok=True)

for path in stable_dir.glob("podcast.*"):
    shutil.copy2(path, evidence_dir / path.name)
```

## Deterministic Marker Check

Use deterministic checks for exact forbidden markers and transcript presence.

```yaml
schema_version: 1
id: transcript_has_no_production_markers
type: deterministic
description: Stable podcast transcript does not contain obvious unspoken labels or markup.
script: |
  import json
  import re
  import sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
  transcript_path = Path(ctx["project_root"]) / "eval_artifacts/transcripts/podcast.txt"
  if not transcript_path.is_file():
      print(f"missing transcript: {transcript_path}", file=sys.stderr)
      sys.exit(1)

  raw_text = transcript_path.read_text(encoding="utf-8")
  normalized = re.sub(r"\s+", " ", raw_text).lower()
  forbidden = {
      "speaker label": r"\b(speaker\s+\d+|host|guest)\s*:",
      "stage direction": r"(\[[^\]]+\]|\((music|pause|laugh)[^)]+\))",
      "markdown heading": r"(^|\s)#{1,6}\s+\w",
      "markdown bullet": r"(^|\s)[*-]\s+\w",
      "ssml/xml": r"<\s*/?\s*(speak|break|prosody|voice)\b",
      "structural label": r"\b(abstract|methods|key takeaways|references)\s*:",
  }
  for label, pattern in forbidden.items():
      if re.search(pattern, normalized):
          print(f"forbidden {label} marker found", file=sys.stderr)
          sys.exit(1)
```

## Deterministic JSON Shape Check

```yaml
schema_version: 1
id: transcript_json_has_text
type: deterministic
description: Stable transcript JSON contains a non-empty text field.
script: |
  import json
  import sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
  json_path = Path(ctx["project_root"]) / "eval_artifacts/transcripts/podcast.json"
  if not json_path.is_file():
      print(f"missing transcript JSON: {json_path}", file=sys.stderr)
      sys.exit(1)

  payload = json.loads(json_path.read_text(encoding="utf-8"))
  text = payload.get("text")
  if not isinstance(text, str) or not text.strip():
      print("transcript JSON has no non-empty text field", file=sys.stderr)
      sys.exit(1)
```

## Harness Judge Semantic Check

Use a harness judge when semantic equivalence matters more than exact wording.

```yaml
schema_version: 1
id: transcript_preserves_spoken_script
type: harness_judge
description: The transcript preserves the intended spoken script without production annotations.
instructions: |
  Read scripts/intended_spoken_script.txt and eval_artifacts/transcripts/podcast.txt.
  Score 1 only if the transcript preserves the same technical claims and narrative meaning.
  Score 0 if important claims are missing, hallucinated, or contradicted.
  Score 0 if the transcript includes production-only labels, headings, markdown, SSML/XML,
  bracketed stage directions, or structural annotations that were not meant to be spoken.
```

## Normalization Guidance

For deterministic text comparison, normalize a copy of the transcript:

- Lowercase
- Collapse whitespace
- Clean conservative punctuation such as repeated commas or periods only when it cannot change meaning
- Keep the raw `.txt` transcript unchanged for debugging and judge checks

Forbidden marker categories usually worth checking:

- Speaker labels: `Speaker 1:`, `Host:`, `Guest:`
- Stage directions: `[pause]`, `[laughs]`, `(music fades)`
- Markdown: headings, bullets, emphasis, fenced code
- SSML/XML: `<speak>`, `<break>`, `<voice>`
- Structural labels: `Abstract`, `Methods`, `Key takeaways`, `References` when they were not intended spoken words
