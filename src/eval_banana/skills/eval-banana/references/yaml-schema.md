# YAML schema reference

Complete field reference for eval-banana check definitions. Each check file defines a single check — there is no suite wrapper.

## Table of contents

- Common fields (all check types)
- `deterministic` fields
- `llm_judge` fields
- Validation rules
- Error messages and what they mean

## Common fields

| Field | Type | Required | Constraints | Notes |
|---|---|---|---|---|
| `schema_version` | int | **Yes** | Must equal `1` | No default. Omitting → validation error. |
| `id` | string | **Yes** | Pattern `^[a-zA-Z0-9_-]+$`, non-empty after stripping | Must be unique across ALL discovered check files |
| `type` | string | **Yes** | One of `deterministic`, `llm_judge` | Discriminator for the Pydantic union |
| `description` | string | **Yes** | Non-empty after stripping | Human-readable, shown in reports |
| `target_paths` | list[string] | No | Each entry non-empty | Resolved relative to `project_root`. Required non-empty for `llm_judge`. |
| `tags` | list[string] | No | — | Free-form metadata. Not yet used for filtering but allowed. |

`extra="forbid"` is enabled — any unknown field fails validation.

## `deterministic` check

Type-specific fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `script` | string | **One of** | Inline Python source code (use `script: \|` block scalar) |
| `script_path` | string | **One of** | Path to external Python file, **relative to the YAML file's directory** |

**Exactly one** of `script` or `script_path` must be set. Setting both is a validation error. Setting neither is a validation error.

### Subprocess contract

- Command: `python <script> <context_path>`
- `cwd`: `project_root`
- Environment: full parent env (no additional injection)

### `context.json` shape

Passed as `sys.argv[1]`. Always this exact shape:

```json
{
  "check_id": "string",
  "description": "string",
  "project_root": "/abs/path",
  "source_path": "/abs/path/to/check.yaml",
  "output_dir": "/abs/path/to/per-check-output-dir",
  "targets": [
    {
      "path": "relative/or/absolute/as/written",
      "resolved_path": "/abs/path/resolved/from/project_root",
      "exists": true,
      "is_dir": false
    }
  ]
}
```

`targets` length matches `target_paths` length. Entry order is preserved.

### Result mapping

| Outcome | Status | Score |
|---|---|---|
| Exit 0 | `passed` | 1 |
| Exit non-zero (includes `AssertionError`, uncaught exceptions, `sys.exit(1)`) | `failed` | 0 |
| `FileNotFoundError` on script itself, `OSError` | `error` | 0 |

`stdout` and `stderr` are captured on the `CheckResult` and written to `<output_dir>/checks/<check_id>.stdout.txt` / `.stderr.txt` (only if non-empty).

## `llm_judge` check

Type-specific fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `instructions` | string | **Yes** | Non-empty. The evaluation prompt sent to the LLM. |
| `model` | string | No | Override `llm.model` for this check only |

**Constraint**: `target_paths` must be non-empty for LLM judge checks (otherwise the LLM has nothing to evaluate).

### Prompt shape

The runner builds a prompt with:
1. A fixed system message asking for `{"score": 0|1, "reason": "..."}` JSON output
2. The `description` as context
3. The `instructions` as the evaluation criterion
4. Each target file's content, separated by `--- BEGIN FILE: <path> ---` / `--- END FILE: <path> ---`
5. Truncation marker `[TRUNCATED]` if a file exceeds `llm_max_input_chars` (default 12000)

### Required LLM response format

```json
{"score": 0, "reason": "one sentence explanation"}
```

- `score` MUST be exactly `0` or `1`. Any other value → `error` result.
- `reason` is optional but recommended. If present, must be a string.
- Response must be valid JSON. Prose or malformed JSON → `error` result.

### Result mapping

| Outcome | Status | Score |
|---|---|---|
| Valid JSON, `score == 1` | `passed` | 1 |
| Valid JSON, `score == 0` | `failed` | 0 |
| Malformed JSON or score outside {0,1} | `error` | 0 |
| Missing credentials | `error` | 0 |
| API error (any kind) | `error` | 0 |
| Missing / unreadable target file | `error` | 0 |

### Provider routing

- `provider = "openai_compat"` (default): uses OpenAI SDK with `api_base` URL
- `provider = "codex"`: uses hardcoded ChatGPT backend URL (`https://chatgpt.com/backend-api`), ignores `api_base`

## Validation rules summary

The loader raises a `ValueError` naming the file path for any of these:

- YAML parse error
- Top-level YAML is not a dict
- Any required field missing
- `id` doesn't match `^[a-zA-Z0-9_-]+$`
- `description` empty or whitespace-only
- Unknown top-level field (blocked by `extra="forbid"`)
- `type` not one of the allowed values
- `script` AND `script_path` both set, or neither set (deterministic)
- `instructions` empty, or `target_paths` empty (llm_judge)

The runner raises `SystemExit` for:
- Duplicate check IDs across files (shows both file paths)
- No checks found after discovery + filtering
- `--check-id` matches multiple files (also shows paths)

## Common validation errors

| Error text | Cause | Fix |
|---|---|---|
| `Field required [type=missing]` on `schema_version` | Forgot the field | Add `schema_version: 1` |
| `Extra inputs are not permitted` | Unknown field | Remove or check spelling |
| `script and script_path are mutually exclusive` | Both set | Remove one |
| `deterministic check must have script or script_path` | Neither set | Add one |
| `instructions must be non-empty` | Empty or missing on llm_judge | Add instructions |
| `target_paths must be non-empty` | Empty list on llm_judge | Add at least one target |
| `command must be a non-empty list` | Empty list or not a list | Use list syntax, non-empty |
| `id does not match pattern` | Invalid chars (dots, spaces, etc.) | Use only `[a-zA-Z0-9_-]` |
| `Duplicate check id 'X' found in: ...` | Same id in 2+ files | Rename one |
