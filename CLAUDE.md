# CLAUDE.md

## Overview

eval-banana is a lightweight aspect-based evaluation framework. It discovers YAML check definitions from `eval_checks/` directories, runs them, and produces scored reports.

## Development commands

```bash
uv sync --extra dev    # Install all dependencies
make test              # Run pytest
make fix               # Auto-fix lint + format
make pyright           # Type check
make all-check         # Full CI check (lint + format + types + tests)
make run               # Run eval-banana against this project
```

## Project structure

```
src/eval_banana/
  models.py          # Pydantic models (check definitions, results, reports)
  config.py          # Two-tier TOML config loading
  auth.py            # OpenRouter + Codex authentication
  discovery.py       # Auto-discover eval_checks/ directories
  loader.py          # YAML loading + validation
  runner.py          # Top-level orchestration (harness + checks)
  scorer.py          # Pure scoring function
  reporter.py        # Console + JSON + Markdown output
  cli.py             # Click CLI (init, run, list, validate)
  harness/
    __init__.py      # Empty package marker
    template.py      # AgentTemplate dataclass + built-in templates
    registry.py      # Template resolution + command building
    runner.py        # Synchronous harness subprocess execution
  runners/
    deterministic.py # Script-based checks
    llm_judge.py     # LLM-as-judge checks
    task_based.py    # Command-based checks
tests/               # One test file per source module
```

## Conventions

- Python 3.12+, UV for deps, ruff for linting, pyright for types
- Modern type hints: `list[str]`, `str | None` (not `Optional`)
- Named arguments everywhere (keyword-only with `*`)
- Empty `__init__.py` files
- `logging.getLogger(__name__)` in every module
- Pydantic models with `extra="forbid"` for strict validation
- Discriminated union for check types via `Field(discriminator="type")`
- Runners never raise on expected errors -- always return `CheckResult`
- Fail fast on setup errors (bad YAML, duplicate IDs), continue on execution errors
- No async -- all execution is synchronous
- Tests use `tmp_path`, mock `subprocess.run` and OpenAI SDK, run offline

## Check types

| Type | Score | Mechanism |
|---|---|---|
| `deterministic` | Exit code 0 = 1, non-zero = 0 | Python script via subprocess |
| `llm_judge` | LLM returns `{"score": 0\|1}` | OpenAI-compatible API call |
| `task_based` | Exit code 0 = 1, non-zero = 0 | Arbitrary command via subprocess |

## Harness support

eval-banana can optionally drive an AI coding agent (harness) before running checks.

- Configured via `[harness]` and `[agents.*]` TOML sections or `--harness-*` CLI flags
- Built-in templates: `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`
- Harness runs synchronously via `subprocess.run()` before the check loop
- Harness failure aborts checks (use `--skip-harness` to override)
- Harness metadata stored on `EvalReport.harness` (separate from check scoring)
- AgentTemplate is a frozen dataclass (internal, not serialized)
- `HarnessResult` is a Pydantic model with `extra="forbid"`

## Key design decisions

- One YAML file per check (not per suite)
- Auto-discovery from `eval_checks/` directories
- Equal weight for all checks (no weighting system)
- Provider-aware credential isolation (OpenRouter keys never sent to OpenAI, vice versa)
- Codex backend URL is hardcoded -- `api_base` config does not affect Codex
- `--check-id` uses relaxed validation (broken YAML in other files does not block)
- Harness is a run-level phase, not a check type -- no `type: harness` in YAML
- Single harness per run -- no multi-agent orchestration
- No async -- harness uses synchronous subprocess.run() like task_based checks
