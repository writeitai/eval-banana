---
name: eval-banana
description: Guide for using eval-banana, a lightweight aspect-based evaluation framework with YAML check definitions. Use when the user is working in a project with `eval_checks/` directories, wants to write or debug YAML eval definitions, needs to score LLM outputs or workflow behavior with pass/fail checks, is running `eval-banana` / `eb` CLI commands, is setting up eval-banana in a new project, or needs to configure OpenRouter/OpenAI/Codex credentials for LLM judge checks. Covers deterministic checks (subprocess scripts), LLM judge checks (model-graded), auto-discovery rules, context.json contract, config precedence, and report interpretation.
---

# eval-banana

## Overview

eval-banana is a lightweight evaluation framework. Check definitions live in YAML files under `eval_checks/` directories and are auto-discovered. Each check scores 0 or 1 (pass/fail) with equal weight. Two check types cover most needs. One YAML file per check — there is no suite wrapper.

## The two check types

| Type | Use when | Mechanism |
|---|---|---|
| `deterministic` | Asserting file content, structure, or values objectively | Python script via subprocess; exit 0 = pass, non-zero = fail |
| `llm_judge` | Evaluating qualitative properties (coherence, tone, factuality) | LLM returns `{"score": 0\|1, "reason": "..."}` |

**Default to `deterministic`** when the condition can be checked with code — it's the cheapest, most reliable, and requires no credentials.

## Core workflow

1. **Install** (once per machine): `uv tool install git+https://github.com/writeitai/eval-banana.git`
2. **Initialize in project**: `eval-banana init` — creates `.eval-banana/config.toml` and an example check under `eval_checks/`
3. **Write checks**: add `*.yaml` files to any `eval_checks/` directory (they are auto-discovered from the project root)
4. **Run**: `eval-banana run`
5. **Read the report**: look under `.eval-banana/results/<run_id>/`

## Common YAML fields

Every check file starts with these fields regardless of type:

```yaml
schema_version: 1            # Always 1. Required. No default.
id: my_check_id              # Unique across the project. Pattern: [a-zA-Z0-9_-]+
type: deterministic          # One of: deterministic, llm_judge
description: Human-readable  # Required. Non-empty.
target_paths:                # Files/dirs the check operates on. Resolved from project_root.
  - path/to/file.json        # Optional for deterministic; required (non-empty) for llm_judge.
tags: [fast, critical]       # Optional list of free-form tags.
```

Plus type-specific fields below.

## Writing a `deterministic` check

Runs a Python script via subprocess. Exit code 0 = pass, non-zero = fail. Infrastructure problems (missing script file, OS execution failure) = error.

```yaml
schema_version: 1
id: output_has_result_key
type: deterministic
description: output.json exists and contains a 'result' key.
target_paths:
  - output.json
script: |
  import json, sys
  from pathlib import Path

  ctx = json.loads(Path(sys.argv[1]).read_text())
  target = ctx["targets"][0]
  if not target["exists"]:
      sys.exit(1)
  data = json.loads(Path(target["resolved_path"]).read_text())
  if "result" not in data:
      sys.exit(1)
```

Use `script: |` for inline Python, or `script_path: my_script.py` for an external script. The path is resolved **relative to the YAML file's directory**. Exactly one of `script` or `script_path` must be set.

### The `context.json` contract (critical!)

The script is invoked as `python <script> <context.json>`. Read `sys.argv[1]` to get the context path. It always has this exact shape:

```json
{
  "check_id": "output_has_result_key",
  "description": "output.json exists and contains a 'result' key.",
  "project_root": "/abs/path/to/project",
  "source_path": "/abs/path/to/project/eval_checks/my_check.yaml",
  "output_dir": "/abs/path/.../.eval-banana/results/<run_id>/checks/output_has_result_key",
  "targets": [
    {
      "path": "output.json",
      "resolved_path": "/abs/path/to/project/output.json",
      "exists": true,
      "is_dir": false
    }
  ]
}
```

Key points:
- `targets` entries align 1:1 with `target_paths` in the YAML, in order.
- `resolved_path` is absolute — use it directly, don't re-resolve from `path`.
- `exists` and `is_dir` are pre-checked for convenience.
- The subprocess runs with `cwd = project_root`, so relative paths in the script also resolve from there.

### Deterministic failure mapping

- `sys.exit(0)` or falling off the end → passed
- `sys.exit(1)` or any non-zero exit → failed
- `AssertionError` or any uncaught exception → failed (non-zero exit)
- `FileNotFoundError` on the script itself → error

## Writing an `llm_judge` check

Sends target file content + instructions to an LLM. The LLM must respond with JSON: `{"score": 0|1, "reason": "one sentence"}`.

```yaml
schema_version: 1
id: readme_explains_install
type: llm_judge
description: README gives a new user enough info to install the package.
target_paths:
  - README.md
instructions: |
  Does the README give a new user enough information to install
  and run the package locally (environment setup, install command,
  and how to invoke it)? Score 1 if yes, 0 if anything critical
  is missing.
```

Guidelines for good instructions:
- State the exact condition for score 1 and score 0.
- Be binary — avoid "mostly", "partially", etc.
- Reference concrete things to look for.
- Keep it short. Long instructions confuse the judge.
- Do not ask for scores outside {0, 1} — the parser rejects anything else as `error`.

Optional fields:
- `model: openai/gpt-4.1` — override the default LLM model for this one check.
- Multiple `target_paths` — all files are concatenated with separators in the prompt.

### Credentials (provider-aware, safe)

- **OpenRouter (default)**: set `OPENROUTER_API_KEY`. Never sends this key to OpenAI.
- **OpenAI direct**: set `api_base = "https://api.openai.com/v1"` in config, then `OPENAI_API_KEY`. Never sends this key to OpenRouter.
- **Codex** (local ChatGPT subscription): run `codex login`, then `eval-banana run --provider codex`. Backend URL is hardcoded; `api_base` has no effect for Codex.
- **Missing credentials** → per-check `error` result (not silent skip). Other check types continue running.

## Auto-discovery rules

- eval-banana walks from the project root (the directory containing `.eval-banana/`).
- It finds every directory named exactly `eval_checks/`.
- Inside each, it loads every `*.yaml` and `*.yml` file.
- Check IDs must be unique across all discovered files. Duplicates are a **fatal load error**.
- These directories are skipped by default: `.git`, `.hg`, `.svn`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`.
- Symlinked directories are not followed.

Co-locate checks with the code they verify:

```
project/
├── eval_checks/                     # Top-level checks
│   └── overall_quality.yaml
├── src/api/
│   └── eval_checks/                 # API-specific checks
│       └── response_schema.yaml
└── frontend/
    └── eval_checks/                 # Frontend E2E checks
        └── login_flow.yaml
```

## Running checks

```bash
eval-banana run                        # Run everything
eval-banana run --check-id my_check    # Run one check; relaxed validation of siblings
eval-banana run --check-dir path/      # Only scan this directory
eval-banana run --verbose              # Debug logging
eval-banana run --pass-threshold 0.8   # Override pass ratio
eval-banana run --provider codex       # Force provider for LLM checks
eval-banana list                       # Discover + print checks without running
eval-banana validate                   # Validate YAML without executing anything
eval-banana init [--global] [--force]  # Create config (+ example check locally)
```

**`--check-id` is the debug escape hatch.** It uses relaxed validation — broken YAML in other files does NOT block a single targeted check. Use it when iterating on one check in a repo with incomplete checks elsewhere.

## Reading results

Each run writes to `.eval-banana/results/<run_id>/`:

```
<run_id>/
├── report.json                # Machine-readable, full EvalReport
├── report.md                  # Human-readable summary
└── checks/
    ├── <check_id>.json        # Per-check CheckResult
    ├── <check_id>.stdout.txt  # Captured stdout (only if non-empty)
    └── <check_id>.stderr.txt  # Captured stderr (only if non-empty)
```

The console output shows:
- Run ID
- `points_earned/total_points` and percentage
- PASS or FAIL verdict
- Per-check list with reason (for failed) or error (for errored)

**Pass criteria**: `run_passed = (points_earned / total_points) >= pass_threshold AND errored_checks == 0`. A single erroring check means the whole run fails, even if every other check passed.

Exit code: 0 on `run_passed`, 1 otherwise. Usable directly in CI.

## When to use which check type

- **`deterministic`** — the condition is objective and testable with code:
  - "file X exists and is non-empty"
  - "the JSON has field Y"
  - "no TODO comments in src/"
  - "the CSV has N rows with these columns"

- **`llm_judge`** — the condition is subjective or needs language understanding:
  - "the error message is helpful to end users"
  - "the generated summary captures the key points"
  - "the tone is professional and friendly"
  - "the docs explain the concept clearly"

**If in doubt, prefer `deterministic`** — cheapest, most reliable, no credentials needed.

## Common gotchas

- **Forgetting `schema_version: 1`** — it has no default and omitting it is a validation error.
- **Using `script:` AND `script_path:`** — exactly one must be set, never both.
- **Putting a shell string in `command:`** — must be a list, e.g. `["pytest", "-q"]`, never `"pytest -q"`.
- **Duplicate IDs across files** — fatal. Grep for the ID before adding a new check.
- **Expecting silent skip on missing LLM credentials** — eval-banana always returns an `error` result, never skips.
- **Assuming `cwd` is where you invoked `eval-banana`** — deterministic scripts run with `cwd = project_root`.
- **LLM judge returns prose instead of JSON** — the runner requires strict `{"score": 0|1, "reason": "..."}`. Tell the LLM to respond with JSON only.

## References

For deeper detail, read these as needed:

- **`references/yaml-schema.md`** — Every field for every check type, validation rules, and edge cases. Read when writing a check with unusual requirements or debugging a validation error.
- **`references/examples.md`** — Gallery of real-world check patterns (JSON validation, test runners, linters, LLM tone checks, UI flows). Read when looking for a template matching the current use case.
- **`references/config.md`** — Full TOML config reference, precedence rules, provider-specific auth setup, and environment variable list. Read when configuring eval-banana for a new project or switching providers.
