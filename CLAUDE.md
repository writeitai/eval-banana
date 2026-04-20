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
  config.py          # Project-level TOML config loading
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
    skills.py        # Bundled skill installer + agent target mapping
  skills/            # Bundled agent skills shipped inside the wheel
  runners/
    deterministic.py # Script-based checks
    harness_judge.py # Harness-subprocess judge checks
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
- Tests use `tmp_path`, mock `subprocess.run`, run offline

## Check types

| Type | Score | Mechanism |
|---|---|---|
| `deterministic` | Exit code 0 = 1, non-zero = 0 | Python script via subprocess |
| `harness_judge` | Harness returns `{"score": 0\|1}` | Harness agent subprocess |

## Harness support

eval-banana can optionally drive an AI coding agent (harness) before running checks.

- Configured via `[harness]` and `[agents.*]` TOML sections or `--harness-*` CLI flags
- Built-in templates: `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`
- Harness runs synchronously via `subprocess.run()` before the check loop
- Bundled skills are installed explicitly with `eb install` before harness-driven work
- Harness failure aborts checks.
- `harness_judge` checks require a configured harness; `run` and `validate` fail fast otherwise.
- Harness metadata stored on `EvalReport.harness` (separate from check scoring)
- AgentTemplate is a frozen dataclass (internal, not serialized)
- `HarnessResult` is a Pydantic model with `extra="forbid"`

## Key design decisions

- One YAML file per check (not per suite)
- Auto-discovery from `eval_checks/` directories
- Equal weight for all checks (no weighting system)
- All LLM calls go through the harness subprocess -- eval-banana does not talk to model APIs directly
- `--check-id` uses relaxed validation (broken YAML in other files does not block)
- Harness is a run-level phase, not a check type -- no `type: harness` in YAML
- Single harness per run -- no multi-agent orchestration
- No async -- harness uses synchronous subprocess.run()
