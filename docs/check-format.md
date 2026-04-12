# Check definition format

Every check is a single YAML file in an `eval_checks/` directory. eval-banana auto-discovers these files by walking from the project root.

**Note:** The harness (AI coding agent) is configured in TOML config or CLI flags, not in YAML check files. There is no `type: harness` check type. See `docs/configuration.md` for harness setup.

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
5. Infrastructure errors (missing script, OS execution failure) = error

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
| `working_directory` | string | No | Working directory (relative to project root) |
| `env` | dict[string, string] | No | Extra environment variables |

### How it works

1. The command runs as a subprocess
2. `EVAL_BANANA_PROJECT_ROOT`, `EVAL_BANANA_OUTPUT_DIR`, `EVAL_BANANA_CHECK_ID` are injected
3. Exit code 0 = passed, non-zero = failed
4. Infrastructure errors (command not found, OS execution failure) = error

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
```

## Auto-discovery

eval-banana walks from the project root and finds all directories named `eval_checks/`. Every `*.yaml` and `*.yml` file inside is loaded.

Excluded directories (configurable): `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build`.

Check IDs must be unique across all discovered files.

## Result mapping summary

| Exit code | Status | Score |
|---|---|---|
| 0 | passed | 1 |
| Non-zero | failed | 0 |
| OS / execution error | error | 0 |
