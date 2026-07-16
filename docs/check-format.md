# Check definition format

Every check is a single YAML file in an `eval_checks/` directory. eval-banana auto-discovers these files by walking from the project root.

**Note:** The harness (AI coding agent) is configured in TOML config or CLI flags, not in YAML check files. There is no `type: harness` check type. See `docs/configuration.md` for harness setup.

## Common fields

All check types share these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `1` | Yes | Schema version (must be `1`) |
| `id` | string | Yes | Unique identifier (`[a-zA-Z0-9_-]` only) |
| `type` | string | Yes | One of: `deterministic`, `harness_judge` |
| `description` | string | Yes | Human-readable description |
| `tags` | list[string] | No | Tags for filtering (future use) |

## Deterministic checks

Run a Python script that asserts conditions about project files.

| Field | Type | Required | Description |
|---|---|---|---|
| `script` | string | One of | Inline Python script |
| `script_path` | string | One of | Path to external script (relative to YAML file) |

Exactly one of `script` or `script_path` must be set.

### How it works

1. A `context.json` file is written with check metadata and project root
2. An inline script is materialized privately; a `script_path` file is read once,
   included in `check_definition_sha256`, and materialized from those frozen bytes
3. The materialized script runs as `python <script> <context.json>`
4. Exit code 0 = passed, non-zero = failed
5. Infrastructure errors (missing script, OS execution failure) = error

Freezing a referenced script makes the result auditable: the runner executes the
same bytes that its definition digest covers, even if the original file changes
after the run snapshots it. The private launcher retains the referenced script's
original resolved path as `__file__` and `sys.argv[0]`, and retains its parent as
the first import path, so existing relative-asset and sibling-import behavior does
not change.

### context.json shape

```json
{
  "check_id": "my_check",
  "description": "Check description",
  "project_root": "/absolute/project/root",
  "source_path": "/absolute/path/to/check.yaml",
  "output_dir": "/absolute/path/to/output/checks/my_check"
}
```

### Example

```yaml
schema_version: 1
id: no_todo_comments
type: deterministic
description: No TODO markers in Python source files.
script: |
  import json, sys
  from pathlib import Path
  ctx = json.loads(Path(sys.argv[1]).read_text())
  src = Path(ctx["project_root"]) / "src"
  for f in src.rglob("*.py"):
      if "TODO" in f.read_text():
          sys.exit(1)
```

## Harness judge checks

Invoke the configured harness agent with evaluation instructions. The agent can read project files on its own.

| Field | Type | Required | Description |
|---|---|---|---|
| `instructions` | string | Yes | Evaluation criteria for the judge |
| `model` | string | No | Override the harness model for this check |

### How it works

1. A judging prompt is built from the check description and instructions
2. The configured harness agent subprocess receives that prompt
3. The final verdict must include `{"score": 0|1, "reason": "..."}`
4. Score 1 = passed, 0 = failed, parse error = error
5. Harness spawn failures or timeouts = error

### Example

```yaml
schema_version: 1
id: readme_has_install_steps
type: harness_judge
description: README clearly explains how to install the package.
instructions: |
  Read README.md. Does it give a new user enough information to
  install and run the package locally? Score 1 if yes, 0 if no.
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
