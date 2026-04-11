# Check definition format

Every check is a single YAML file in an `eval_checks/` directory. eval-banana auto-discovers these files by walking from the project root.

## Common fields

All check types share these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `1` | Yes | Schema version (must be `1`) |
| `id` | string | Yes | Unique identifier (`[a-zA-Z0-9_-]` only) |
| `type` | string | Yes | One of: `deterministic`, `llm_judge`, `task_based` |
| `description` | string | Yes | Human-readable description |
| `target_paths` | list[string] | No | Files/directories the check operates on |
| `tags` | list[string] | No | Tags for filtering (future use) |
| `timeout_seconds` | int | No | Override default timeout for this check |

## Deterministic checks

Run a Python script that asserts conditions about target files.

| Field | Type | Required | Description |
|---|---|---|---|
| `script` | string | One of | Inline Python script |
| `script_path` | string | One of | Path to external script (relative to YAML file) |

Exactly one of `script` or `script_path` must be set.

### How it works

1. Target paths are resolved relative to the project root
2. A `context.json` file is written with check metadata and resolved targets
3. The script runs as `python <script> <context.json>`
4. Exit code 0 = passed, non-zero = failed
5. Infrastructure errors (timeout, missing script) = error

### context.json shape

```json
{
  "check_id": "my_check",
  "description": "Check description",
  "project_root": "/absolute/project/root",
  "source_path": "/absolute/path/to/check.yaml",
  "output_dir": "/absolute/path/to/output/checks/my_check",
  "targets": [
    {
      "path": "relative/path.txt",
      "resolved_path": "/absolute/resolved/path.txt",
      "exists": true,
      "is_dir": false
    }
  ]
}
```

### Example

```yaml
schema_version: 1
id: no_todo_comments
type: deterministic
description: No TODO markers in Python source files.
target_paths:
  - src
script: |
  import json, sys
  from pathlib import Path
  ctx = json.loads(Path(sys.argv[1]).read_text())
  for t in ctx["targets"]:
      p = Path(t["resolved_path"])
      if p.is_dir():
          for f in p.rglob("*.py"):
              text = f.read_text()
              if "TODO" in text:
                  sys.exit(1)
```

## LLM judge checks

Send target file content to an LLM with evaluation instructions.

| Field | Type | Required | Description |
|---|---|---|---|
| `instructions` | string | Yes | Evaluation criteria for the LLM |
| `model` | string | No | Override the default LLM model for this check |
| `target_paths` | list[string] | Yes | Must be non-empty |

### How it works

1. Target files are read and included in the prompt
2. The LLM receives instructions + file content
3. It must respond with `{"score": 0|1, "reason": "..."}`
4. Score 1 = passed, 0 = failed, parse error = error
5. Missing credentials = error (not skipped)

### Example

```yaml
schema_version: 1
id: readme_has_install_steps
type: llm_judge
description: README clearly explains how to install the package.
target_paths:
  - README.md
instructions: |
  Does the README give a new user enough information to install
  and run the package locally? Score 1 if yes, 0 if no.
```

## Task-based checks

Run an arbitrary command and check its exit code.

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | list[string] | Yes | Command and arguments to run |
| `harness` | string | No | Name of a configured `[harnesses.<name>]` preset |
| `model` | string | No | Harness-specific model override; requires `harness` |
| `working_directory` | string | No | Working directory (relative to project root) |
| `env` | dict[string, string] | No | Extra environment variables |

### How it works

1. The command runs as a subprocess
2. If `harness` is set, eval-banana prepends the configured harness argv and env
3. `EVAL_BANANA_PROJECT_ROOT`, `EVAL_BANANA_OUTPUT_DIR`, `EVAL_BANANA_CHECK_ID` are injected
4. Exit code 0 = passed, non-zero = failed
5. Infrastructure errors (timeout, command not found) = error

### Example

```yaml
schema_version: 1
id: unit_tests_pass
type: task_based
description: The unit test suite passes.
command:
  - uv
  - run
  - pytest
  - tests
  - -q
timeout_seconds: 300
```

Harnessed example:

```yaml
schema_version: 1
id: claude_login_flow
type: task_based
description: Claude can complete the login flow.
harness: claude_openrouter
model: anthropic/claude-sonnet-4.6
command:
  - --print
  - Complete the login flow and write notes to $EVAL_BANANA_OUTPUT_DIR/result.txt
env:
  TRACE_ID: run-123
```

Notes:

- `model` without `harness` is a schema error
- With a harness, `command` is appended after the harness command and shared flags
- `{env:VAR}` placeholder substitution applies only inside `harnesses.*.provider_env`, not in `task_based.env`
- Unknown harness names return a per-check `error` result and do not stop other checks

### Built-in harness recipes

`eval-banana init` drops commented native + OpenRouter recipes for `codex`, `claude`, and `gemini` into the generated config file. Short form:

```toml
# Native Codex
# [harnesses.codex]
# command = ["codex", "exec"]
# default_model = "gpt-5.4"
# model_flag = "--model"

# Native Claude
# [harnesses.claude]
# command = ["claude"]
# shared_flags = ["--dangerously-skip-permissions"]
# model_flag = "--model"

# Native Gemini
# [harnesses.gemini]
# command = ["gemini", "--approval-mode=yolo"]
# default_model = "gemini-2.5-pro"
# model_flag = "--model"
```

Uncomment the block you need and, for OpenRouter routing, use the corresponding `*_openrouter` variant shown in [docs/configuration.md](configuration.md#task-based-harness-behavior).

## Auto-discovery

eval-banana walks from the project root and finds all directories named `eval_checks/`. Every `*.yaml` and `*.yml` file inside is loaded.

Excluded directories (configurable): `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build`.

Check IDs must be unique across all discovered files.

## Result mapping summary

| Exit code | Status | Score |
|---|---|---|
| 0 | passed | 1 |
| Non-zero | failed | 0 |
| Timeout/OS error | error | 0 |
