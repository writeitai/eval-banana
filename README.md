# eval-banana

Lightweight aspect-based evaluation framework for Python projects.

## What it does

eval-banana discovers YAML check definitions from `eval_checks/` directories, runs them, and produces a report. Every check scores 0 or 1 with equal weight.

Three check types:

| Type | Purpose | How it works |
|---|---|---|
| `deterministic` | File existence, content assertions, data validation | Runs a Python script via subprocess; exit 0 = pass |
| `llm_judge` | Qualitative evaluation (coherence, accuracy, tone) | Sends target files + instructions to an LLM; expects `{"score": 0\|1}` |
| `task_based` | End-to-end workflow validation (UI, CLI, API) | Runs an arbitrary command; exit 0 = pass |

## Quick start

```bash
# Install
uv sync

# Initialize project config and example check
eval-banana init

# Run all discovered checks
eval-banana run

# List discovered checks without running
eval-banana list

# Validate YAML definitions without running
eval-banana validate
```

## Installation

```bash
# From source (development)
uv sync --extra dev

# As a dependency in another project
uv add eval-banana
```

After installation, two CLI commands are available: `eval-banana` and `eb` (short alias).

## Writing checks

Create a directory called `eval_checks/` anywhere in your project. Add YAML files -- one per check.

### Deterministic check

```yaml
schema_version: 1
id: output_file_exists
type: deterministic
description: Verify that output.json was generated.
target_paths:
  - output.json
script: |
  import json, sys
  from pathlib import Path
  ctx = json.loads(Path(sys.argv[1]).read_text())
  target = ctx["targets"][0]
  assert target["exists"], f"{target['path']} not found"
```

The script receives a `context.json` path as `sys.argv[1]` with this shape:

```json
{
  "check_id": "output_file_exists",
  "description": "...",
  "project_root": "/abs/path",
  "targets": [
    {"path": "output.json", "resolved_path": "/abs/path/output.json", "exists": true, "is_dir": false}
  ]
}
```

### LLM judge check

```yaml
schema_version: 1
id: summary_is_accurate
type: llm_judge
description: The generated summary accurately reflects source data.
target_paths:
  - summary.txt
  - source_data.json
instructions: |
  Compare the summary against the source data.
  Score 1 if accurate, 0 if it contains fabricated claims.
```

Requires an API key. Set `OPENROUTER_API_KEY` or configure in `.eval-banana/config.toml`.

### Task-based check

```yaml
schema_version: 1
id: login_flow_works
type: task_based
description: The UI agent can complete the login flow.
command:
  - uv
  - run
  - python
  - ui_checks/login_test.py
timeout_seconds: 120
```

Task-based checks can also wrap a configured harness preset. In that mode, `command` is appended after the harness command and shared flags.

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
```

## Configuration

eval-banana uses TOML config with two tiers:

1. **Global**: `~/.eval-banana/config.toml` (user-wide defaults)
2. **Local**: `.eval-banana/config.toml` (project-level, overrides global)

Create config with `eval-banana init` (local) or `eval-banana init --global`.

### Config precedence (highest to lowest)

1. CLI arguments (`--model`, `--provider`, etc.)
2. Environment variables (`EVAL_BANANA_*`)
3. `OPENROUTER_API_KEY` / `OPENAI_API_KEY` (provider-aware)
4. Local project config
5. Global config
6. Built-in defaults

### Key settings

| Setting | Default | Env var |
|---|---|---|
| `output_dir` | `.eval-banana/results` | `EVAL_BANANA_OUTPUT_DIR` |
| `pass_threshold` | `1.0` | `EVAL_BANANA_PASS_THRESHOLD` |
| `provider` | `openai_compat` | `EVAL_BANANA_PROVIDER` |
| `model` | `openai/gpt-4.1-mini` | `EVAL_BANANA_MODEL` |
| `api_base` | `https://openrouter.ai/api/v1` | `EVAL_BANANA_API_BASE` |

### LLM provider setup

**OpenRouter** (default):
```bash
export OPENROUTER_API_KEY=your-key
```

**OpenAI direct**:
```bash
export EVAL_BANANA_API_BASE=https://api.openai.com/v1
export OPENAI_API_KEY=your-key
```

**Codex** (local ChatGPT subscription):
```bash
# Run `codex login` first, then:
eval-banana run --provider codex
```

### Task-based harness presets

`[harnesses.<name>]` adds reusable argv/env presets for `task_based` checks only. Global and local config merge by harness name; nested `provider_env` keys merge by key, while list fields such as `command`, `shared_flags`, and `model_env_vars` replace on local override.

Example:

```toml
[harnesses.claude_openrouter]
command = ["claude"]
shared_flags = ["--dangerously-skip-permissions"]
default_model = "anthropic/claude-sonnet-4.6"
model_flag = "--model"
model_env_vars = ["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"]

[harnesses.claude_openrouter.provider_env]
ANTHROPIC_BASE_URL = "https://openrouter.ai/api"
ANTHROPIC_AUTH_TOKEN = "{env:OPENROUTER_API_KEY}"
ANTHROPIC_API_KEY = ""
```

`task_based.model` is only valid when `task_based.harness` is also set. `{env:VAR}` placeholders are resolved only inside `harnesses.*.provider_env`, not inside `task_based.env`.

## CLI reference

```
eval-banana init [--global] [--force]     Create config files
eval-banana run [OPTIONS]                  Run all discovered checks
eval-banana list [OPTIONS]                 List discovered checks
eval-banana validate [OPTIONS]             Validate YAML without running

Options for run/list/validate:
  --check-dir PATH       Scan only this directory
  --check-id TEXT        Run only this check ID
  --output-dir TEXT      Override output directory
  --provider TEXT        LLM provider (openai_compat or codex)
  --model TEXT           LLM model name
  --pass-threshold FLOAT Minimum pass ratio (0.0-1.0)
  --verbose              Enable debug logging
  --cwd TEXT             Working directory
```

## Output

Each run creates a timestamped directory under the configured `output_dir`:

```
.eval-banana/results/<run_id>/
  report.json       # Machine-readable full report
  report.md         # Human-readable Markdown report
  checks/
    <check_id>.json       # Per-check result
    <check_id>.stdout.txt # Captured stdout (if any)
    <check_id>.stderr.txt # Captured stderr (if any)
```

## Development

```bash
uv sync --extra dev
make test         # Run tests
make fix          # Auto-fix lint + format
make pyright      # Type check
make all-check    # Lint + format + types + tests (matches CI)
```

## License

MIT
