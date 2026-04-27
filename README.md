# Eval Banana

[![CI](https://github.com/writeitai/eval-banana/actions/workflows/ci.yml/badge.svg)](https://github.com/writeitai/eval-banana/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Aspect-based evaluation framework - deterministic checks + harness judges. Score anything (agentic outputs, workflows, banana!) with simple YAML check definitions.

<p align="center">
  <img src="https://raw.githubusercontent.com/writeitai/eval-banana/main/docs/images/logo.png" alt="Eval Banana logo" width="400">
  <br>
  <sub>The name was inspired by <a href="https://open.spotify.com/track/2DW0Mowto3hrXkFBQt0nye?si=7c608b541ae849ca">this song</a> (my kids love it)</sub>
</p>

## What it does

Eval Banana discovers YAML check definitions from `eval_checks/` directories, runs them, and produces a report. Every check scores 0 or 1 with equal weight.

Two check types:

| Type | Purpose | How it works |
|---|---|---|
| `deterministic` | Objective assertions (file existence, content, structure) | Runs a Python script via subprocess; exit 0 = pass |
| `harness_judge` | LLM-as-a-judge (coherence, accuracy, tone) | Invokes the configured AI agent to score target files; expects `{"score": 0\|1}` |

The harness judge uses one of the following: `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`

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

### Harness judge check

```yaml
schema_version: 1
id: summary_is_accurate
type: harness_judge
description: The generated summary accurately reflects source data.
target_paths:
  - summary.txt
  - source_data.json
instructions: |
  Compare the summary against the source data.
  Score 1 if accurate, 0 if it contains fabricated claims.
```

Requires a configured harness agent. Set `[harness] agent` in config or pass `--harness-agent`.

## Inspiration

Eval Banana's binary 0/1 scoring philosophy draws directly on two earlier bodies of work:

- **Hamel Husain's [_Creating LLM-as-a-Judge that drives business results_](https://hamel.dev/blog/posts/llm-judge/)** — argues that binary pass/fail judgments produce more reliable, actionable evals than Likert-style 1-5 scales.
- **RAGAS's [Aspect Critic metric](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/general_purpose/#aspect-critic)** — evaluates outputs against a natural-language aspect definition and returns a binary verdict.

The `harness_judge` check type is essentially an Aspect Critic: you describe what "good" looks like in plain language, and the judge returns `{"score": 0|1}`.

## Skills

eval-banana ships agent skills in the `skills/` directory of the repository. Install them into your project with the [`npx skills` CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add https://github.com/writeitai/eval-banana
```

The CLI auto-detects installed agents and copies skills into their native directories (`.claude/skills/`, `.codex/skills/`, `.agents/skills/`, `.gemini/skills/`, etc.).

## Quick start

```bash
# Install
uv sync

# Initialize project config
eb init

# Run all discovered checks
eb run

# List discovered checks without running
eb list

# Validate YAML definitions without running
eb validate
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

After installation the CLI is available as `eb`.

## Harness configuration

`harness_judge` checks require a configured harness agent. Configure it via TOML or CLI flags.

### TOML

```toml
# .eval-banana/config.toml
[harness]
agent = "codex"
model = "gpt-5.4"
# reasoning_effort = "high"
```

### Running in CI / cloud

The harness subprocess inherits the parent shell environment, so provide API keys the same way you would when running the agent locally:

| Agent | Environment variable |
|---|---|
| `claude` | `ANTHROPIC_API_KEY` |
| `codex` | `OPENAI_API_KEY` |
| `gemini` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` (or Application Default Credentials) |
| `openhands` | depends on the configured LLM backend |

Example GitHub Actions step:

```yaml
- name: Run evals
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: eb run
```

You can also inject extra env vars via `[harness.env]` in your config:

```toml
[harness.env]
MY_CUSTOM_VAR = "value"
```

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

Eval Banana uses a single project-level TOML config at `.eval-banana/config.toml`.

Create it with `eb init`.

### Config precedence (highest to lowest)

1. CLI arguments (`--output-dir`, `--harness-model`, etc.)
2. Environment variables (`EVAL_BANANA_*`)
3. Project config (`.eval-banana/config.toml`)
4. Built-in defaults

### Key settings

| Setting | Default | Env var |
|---|---|---|
| `output_dir` | `.eval-banana/results` | `EVAL_BANANA_OUTPUT_DIR` |
| `pass_threshold` | `1.0` | `EVAL_BANANA_PASS_THRESHOLD` |
| `llm_max_input_chars` | `0` | `EVAL_BANANA_LLM_MAX_INPUT_CHARS` |
| `harness.agent` | unset | `EVAL_BANANA_HARNESS_AGENT` |
| `harness.model` | unset | `EVAL_BANANA_HARNESS_MODEL` |

## CLI reference

```
eb init [--force]                Create project config
eb run [OPTIONS]                  Run all discovered checks
eb list [OPTIONS]                 List discovered checks
eb validate [OPTIONS]             Validate YAML without running

Options for run/list/validate:
  --check-dir PATH              Scan only this directory
  --check-id TEXT               Run only this check ID
  --output-dir TEXT             Override output directory
  --pass-threshold FLOAT        Minimum pass ratio (0.0-1.0)
  --verbose                     Enable debug logging
  --cwd TEXT                    Working directory

Harness options (run only):
  --harness-agent TEXT          Agent CLI used by harness_judge checks
  --harness-model TEXT          Model override for the agent
  --harness-reasoning-effort TEXT  Reasoning effort level
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

## Contributing

Issues and pull requests are welcome. Please run `make all-check` before opening a PR.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

Copyright 2026 WriteIt.ai s.r.o.
