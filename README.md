# eval-banana

[![CI](https://github.com/writeitai/eval-banana/actions/workflows/ci.yml/badge.svg)](https://github.com/writeitai/eval-banana/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Lightweight aspect-based evaluation framework for Python projects. Score LLM outputs and agent workflows with simple YAML check definitions.

## What it does

eval-banana discovers YAML check definitions from `eval_checks/` directories, runs them, and produces a report. Every check scores 0 or 1 with equal weight.

Optionally, eval-banana can drive an AI coding agent (Claude Code, Codex CLI, Gemini CLI, etc.) as a **harness** before running checks. The harness executes a task prompt, then eval-banana scores the resulting workspace.

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
# Using uv (recommended)
uv add eval-banana

# Using pip
pip install eval-banana

# From source (development)
git clone https://github.com/writeitai/eval-banana.git
cd eval-banana
uv sync --extra dev
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
```

## Harness support

eval-banana can drive an AI coding agent before running checks. The agent receives a task prompt, works on the project, and then eval-banana scores the result.

Built-in agent templates: `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`.

### Inline prompt

```bash
eval-banana run --harness-agent codex --harness-prompt "Fix all failing tests"
```

### Prompt from file

```bash
eval-banana run --harness-agent claude --harness-prompt-file prompts/task.md --harness-model claude-sonnet-4-6
```

### TOML configuration

```toml
# .eval-banana/config.toml
[harness]
agent = "codex"
prompt_file = "prompts/task.md"
model = "gpt-5.4"
# reasoning_effort = "high"
```

### Harness behavior

- The harness runs once before any checks execute.
- Install bundled skills explicitly with `eb install` before harness-driven work in a target project.
- If the harness fails (non-zero exit, missing binary), checks are **not** run and the eval run is marked as failed.
- Use `--skip-harness` to suppress a configured harness and score the current workspace state.
- Harness artifacts (stdout, stderr, prompt, result) are written to `<run_id>/harness/`.

### Skills

eval-banana ships two bundled skills inside the wheel package:

```text
src/eval_banana/skills/
  eval-banana/
  gemini_media_use/
```

Install them into a target project's native agent directories with:

```bash
eb install
eb install --target-agents codex
eb install --skills gemini_media_use --dry-run
```

`eb install` is the only supported way to move bundled skills out of the wheel
and into a project. `eval-banana run` does not install them automatically.

Supported target agents and their destination directories:

| Agent | Destination |
|---|---|
| `claude` | `.claude/skills/` |
| `codex` | `.codex/skills/` |
| `openhands` | `.agents/skills/` |
| `opencode` | `.agents/skills/` |
| `gemini` | `.gemini/skills/` |

The legacy `eval-banana distribute-skills` command was deprecated in 0.2.x and
will be removed no earlier than 0.3.0. Use `eb install` instead.

If a project has custom skills, place them directly in the agent-native
directories above. eval-banana no longer copies custom repo-local `skills/`
directories at runtime.

The bundled `gemini_media_use` helper scripts depend on the optional `google-genai` package. They authenticate via `GEMINI_API_KEY`, then `GOOGLE_API_KEY`, then Application Default Credentials with `GOOGLE_CLOUD_PROJECT` (Vertex AI mode -- requires `gcloud auth application-default login`, not just `gcloud auth login`). The scripts print targeted setup instructions when auth is misconfigured, distinguishing between missing ADC, missing project, and nothing configured at all.

Generated skill directories such as `.claude/skills/`, `.codex/skills/`, `.agents/skills/`, and `.gemini/skills/` should usually be added to `.gitignore` and treated as install artifacts.

### Custom agent templates

Add `[agents.<name>]` sections to override built-in templates or define new ones:

```toml
[agents.myagent]
command = ["my-cli", "run"]
shared_flags = ["--headless"]
prompt_flag = "--prompt"
model_flag = "--model"
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

## CLI reference

```
eval-banana init [--global] [--force]     Create config files
eval-banana run [OPTIONS]                  Run all discovered checks
eval-banana list [OPTIONS]                 List discovered checks
eval-banana validate [OPTIONS]             Validate YAML without running
eval-banana install [OPTIONS]              Install bundled skills into agent dirs
eval-banana distribute-skills [OPTIONS]    Deprecated alias for install

Options for run/list/validate:
  --check-dir PATH              Scan only this directory
  --check-id TEXT               Run only this check ID
  --output-dir TEXT             Override output directory
  --provider TEXT               LLM provider (openai_compat or codex)
  --model TEXT                  LLM model name
  --pass-threshold FLOAT        Minimum pass ratio (0.0-1.0)
  --verbose                     Enable debug logging
  --cwd TEXT                    Working directory

Harness options (run only):
  --harness-agent TEXT          Agent CLI to run before checks
  --harness-prompt TEXT         Task prompt for the agent
  --harness-prompt-file PATH    File containing the task prompt
  --harness-model TEXT          Model override for the agent
  --harness-reasoning-effort TEXT  Reasoning effort level
  --skip-harness                Suppress configured harness
```

## Output

Each run creates a timestamped directory under the configured `output_dir`:

```
.eval-banana/results/<run_id>/
  report.json       # Machine-readable full report
  report.md         # Human-readable Markdown report
  harness/          # Only when a harness was executed
    prompt.txt      # Resolved prompt sent to the agent
    stdout.txt      # Agent stdout
    stderr.txt      # Agent stderr
    result.json     # Harness result metadata
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
make install-skills  # Install bundled skills into the current project
```

## Inspiration

eval-banana's binary 0/1 scoring philosophy draws directly on two earlier bodies of work:

- **Hamel Husain's [_Creating LLM-as-a-Judge that drives business results_](https://hamel.dev/blog/posts/llm-judge/)** — argues that binary pass/fail judgments produce more reliable, actionable evals than Likert-style 1-5 scales.
- **RAGAS's [Aspect Critic metric](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/general_purpose/#aspect-critic)** — evaluates outputs against a natural-language aspect definition and returns a binary verdict.

The `llm_judge` check type is essentially an Aspect Critic: you describe what "good" looks like in plain language, and the judge returns `{"score": 0|1}`.

## Contributing

Issues and pull requests are welcome. Please run `make all-check` before opening a PR.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

Copyright 2026 WriteIt.ai s.r.o.
