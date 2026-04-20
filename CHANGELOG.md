# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.8] - 2026-04-20

### Changed

- `eb init` generates an active `[harness]` section (uncommented) so it
  is applied by default.
- `CI=1` and `PYTHONUNBUFFERED=1` are now always set in the harness
  subprocess environment instead of being example config values.

## [0.0.7] - 2026-04-20

### Fixed

- `eb init` no longer generates `eval_checks/example_check.yaml`. It
  only creates `.eval-banana/config.toml`. Users write their own checks.

## [0.0.6] - 2026-04-20

### Removed

- Worker harness step. eval-banana no longer runs an agent to produce
  artifacts before scoring. The harness config now only tells
  `harness_judge` checks which agent to invoke for judging.
- `HarnessResult` model, `HarnessStatus` enum, `EvalReport.harness` field.
- `--harness-prompt`, `--harness-prompt-file` CLI flags.
- `Config.harness_prompt`, `Config.harness_prompt_file` fields.
- `EVAL_BANANA_HARNESS_PROMPT`, `EVAL_BANANA_HARNESS_PROMPT_FILE` env vars.
- `run_harness()`, `build_harness_result()` functions.
- Scorer harness-failure gating logic.
- Reporter harness output sections.
- Harness artifact directory in output structure.

### Changed

- README: use `eb` as the canonical CLI name (not `eval-banana`).
- README: removed redundant sections, tightened structure.

## [0.0.5] - 2026-04-20

### Changed

- Check type `llm_judge` renamed to `harness_judge`. Judge checks now
  invoke the configured harness agent as a subprocess instead of making
  direct LLM API calls. One execution model (subprocess) for everything.
- `LlmJudgeCheckDefinition` renamed to `HarnessJudgeCheckDefinition`.
- JSON verdict extraction uses last-match brace-depth scanning
  (handles chatty agents, streaming output, multi-line JSON).
- `build_harness_env()` extracted as a shared helper — both the worker
  harness step and the judge runner use the same env-building logic.

### Added

- `src/eval_banana/runners/harness_judge.py` — new runner with 300 s
  subprocess timeout, per-check model override, and robust stdout parsing.
- Migration error for `type: llm_judge` in YAML (points to `harness_judge`).
- Migration error for `[llm]` section in TOML config.

### Removed

- `src/eval_banana/auth.py` — OpenRouter / OpenAI / Codex auth module
  (226 lines).
- `src/eval_banana/runners/llm_judge.py` — direct LLM API runner
  (188 lines).
- `openai` and `httpx` dependencies from `pyproject.toml`.
- `[llm]` config section: `provider`, `model`, `api_base`, `api_key`,
  `codex_auth_path` fields + 5 CLI flags + 5 env vars.

### Migration

- Rename `type: llm_judge` to `type: harness_judge` in YAML check files.
- Delete the `[llm]` section from `.eval-banana/config.toml`.
- A configured harness (`[harness] agent`) is required for
  `harness_judge` checks. LLM credentials (API keys) are no longer
  needed — the harness agent handles authentication.

## [0.0.4] - 2026-04-19

### Changed

- Default LLM model: `openai/gpt-4.1-mini` → `openai/gpt-5.4`
  (codex provider: `gpt-5.4`).
- `llm_max_input_chars` default: `12000` → `0` (disabled). Set to a
  positive value to re-enable per-file truncation.
- Codex backend: switched to `/codex/responses` endpoint with SSE
  streaming and aligned payload shape.

### Removed

- Global config tier (`~/.eval-banana/config.toml`). Only
  project-level `.eval-banana/config.toml` is loaded now. API keys
  should be set via environment variables.
- `--global` flag on `eval-banana init`.
- `Config.global_config_path` field and `get_global_config_template()`.

### Fixed

- `require_harness_for_llm_judge` enforcement restored after a brief
  regression where it was relaxed to a no-op. `llm_judge` checks once
  again require a configured harness; `eval-banana run` and
  `eval-banana validate` abort with an actionable error otherwise.

## [0.0.3] - 2026-04-17

### Added

- Repeatable `--tag` filtering for `eb run` and `eb list` with OR semantics,
  plus `CheckResult.tags` in emitted reports so selected check metadata is
  preserved end-to-end.
- Pre-flight validation: if any selected check has `type: llm_judge` and no
  `[harness] agent` is configured, `eval-banana run` and `eval-banana validate`
  abort with a `SystemExit` that names the offending YAML file and points at
  both the `[harness]` TOML section and the `--harness-agent` flag.
  `eval-banana list` is unchanged (stays read-only).

### Removed

- `--skip-harness` CLI flag, `EVAL_BANANA_SKIP_HARNESS` environment variable,
  `[harness] skip` TOML key, `Config.skip_harness` field, and
  `HarnessStatus.skipped` enum value. The escape-hatch mode for scoring a
  workspace with a configured-but-not-executed harness is gone — unset
  `[harness] agent` if you want to run checks without a harness.

### Changed

- Legacy `[harness] skip = true` in TOML now raises a dedicated, actionable
  error pointing users at `[harness] agent`. The legacy env var
  `EVAL_BANANA_SKIP_HARNESS` is silently unread (shell/CI-friendly).
- Scorer: `harness_allows_pass` now accepts only `HarnessStatus.succeeded`
  (previously also accepted `HarnessStatus.skipped`).

### Migration

- Remove `--skip-harness` from any scripts or CI jobs. To score a workspace
  without running a harness, simply don't configure one (`[harness] agent`
  unset).
- Delete `[harness] skip` from `.eval-banana/config.toml`.
- Old `report.json` artifacts containing `"status": "skipped"` can no longer
  be parsed back into `EvalReport`. Reports are per-run artifacts; no
  migration tooling is provided.

## [0.0.2] - 2026-04-16

### Removed

- `task_based` check type and its runner. The harness covers arbitrary-command
  execution needs; keeping `task_based` around added a third overlapping way to
  run subprocesses. Existing YAML files with `type: task_based` will now fail
  validation — convert them to a `deterministic` check (invoking the same
  command from a short Python script) or run the command as part of a harness.

### Changed

- README: credit Hamel Husain's LLM-as-judge post and RAGAS's Aspect Critic
  as the inspirations for the binary 0/1 scoring model.
- README: reframe the harness → judge relationship so it no longer reads as
  a standalone optional extra (it is the typical end-to-end flow for
  `llm_judge` evaluations).

## [0.0.1] - 2026-04-16

Initial public release.

### Added

- Auto-discovery of YAML check definitions from `eval_checks/` directories.
- Three check types: `deterministic` (script exit code), `llm_judge` (model-graded),
  and `task_based` (arbitrary command).
- Two-tier TOML configuration with credential isolation between OpenRouter, OpenAI,
  and Codex providers.
- Optional harness phase that can drive an AI coding agent (built-in templates for
  `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`) before checks run.
- Repo-local skill distribution step for harness subprocesses.
- Console, JSON, and Markdown reporters.
- `eb` / `eval-banana` CLI with `init`, `run`, `list`, and `validate` commands.
- Explanatory comments in generated TOML config templates.

[Unreleased]: https://github.com/writeitai/eval-banana/compare/v0.0.7...HEAD
[0.0.7]: https://github.com/writeitai/eval-banana/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/writeitai/eval-banana/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/writeitai/eval-banana/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/writeitai/eval-banana/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/writeitai/eval-banana/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/writeitai/eval-banana/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/writeitai/eval-banana/releases/tag/v0.0.1
