# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] - 2026-07-16

### Added

- `eb validate --harness-agent NAME` can now validate `harness_judge` checks
  without relying on a project or ancestor `.eval-banana/config.toml`. The
  command verifies configuration only and does not execute the selected agent.
- `eb run` and `eb validate` now accept `--no-project-config` for hermetic
  callers that must disable upward `.eval-banana/config.toml` discovery and
  treat `--cwd` as the project root.
- `eb run --flat-output --output-dir PATH` writes artifacts directly into an
  attempt-unique output directory while preserving the generated run-id child
  directory as the default layout. Flat output refuses symlinks and existing
  contents.
- Every check result now carries `check_definition_sha256`, the canonical
  `sha256:<64 lowercase hex>` digest of the exact definition bytes read before
  execution.

### Changed

- The built-in `codex` harness template now defaults `reasoning_effort` to
  `high` (previously unset, which fell back to codex's own default). Override
  per project with `[harness] reasoning_effort`, per run with
  `--harness-reasoning-effort`, or via `EVAL_BANANA_HARNESS_REASONING_EFFORT`.
- Harness-judge result details now record the resolved `agent_type`, `model`,
  and nullable `reasoning_effort`, so orchestration callers can bind a verdict
  to the judge configuration that produced it. A harness process must also exit
  zero: any non-zero exit is an `error` with score `0`, even if stdout contains
  an otherwise valid passing JSON verdict.
- A selected model or reasoning effort now fails the check before launch when
  its agent template has no matching model flag/environment variable or
  `{effort}` flag placeholder. The error result records both effective fields
  as `null` instead of claiming an override that never reached the judge.

## [0.3.1] - 2026-07-12

### Added

- Voxtral transcription skill (`skills/voxtral-transcribe`) for transcribing
  image, audio, and video content.

### Changed

- Default codex model upgraded from `gpt-5.5` to `gpt-5.6-sol`, the flagship
  tier of OpenAI's GPT-5.6 family. The `gpt-5.6-terra` (balanced) and
  `gpt-5.6-luna` (fastest/cheapest) tiers remain selectable via `[harness]`
  `model`, `[agents.codex]` `default_model`, the `--harness-model` flag, the
  `EVAL_BANANA_HARNESS_MODEL` env var, or a per-check `model:` override.

## [0.3.0] - 2026-05-06

### Removed

- `target_paths` field from check definitions. Harness judges invoke real
  agents (CC, Codex, Gemini CLI) that read files on their own — tell them
  which files to check in the `instructions` field. Deterministic scripts
  receive `project_root` in context.json and locate files independently.
  Existing YAML files with `target_paths` will fail validation.

### Changed

- Default codex model upgraded from `gpt-5.4` to `gpt-5.5`.

## [0.2.0] - 2026-04-27

### Removed

- `eb install` command and `eb distribute-skills` deprecated alias.
  Skills are now installed via [`npx skills add https://github.com/writeitai/eval-banana`](https://github.com/vercel-labs/skills).
- `src/eval_banana/harness/skills.py` — bundled skill installer module.
- `src/eval_banana/skills/` — skills are no longer bundled in the wheel.
  The canonical source is now `skills/` at the repository root.

### Changed

- Skills section in README and docs updated to point at `npx skills add`.

## [0.1.0] - 2026-04-20

### Fixed

- Dropped `--json` from codex default flags. `codex --json` wraps the
  verdict in streaming event objects so `{"score": 0|1}` cannot be
  extracted. Without it the verdict appears as raw text on stdout.

## [0.0.9] - 2026-04-20

### Changed

- Generated config template now shows the built-in agent bypass flags
  as commented-out `[agents.*]` sections (codex: `--dangerously-bypass-
  approvals-and-sandbox`; gemini: `--approval-mode=yolo`; claude:
  `--dangerously-skip-permissions`). Transparency over magic.

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

[Unreleased]: https://github.com/writeitai/eval-banana/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/writeitai/eval-banana/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/writeitai/eval-banana/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/writeitai/eval-banana/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/writeitai/eval-banana/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/writeitai/eval-banana/compare/v0.0.9...v0.1.0
[0.0.9]: https://github.com/writeitai/eval-banana/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/writeitai/eval-banana/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/writeitai/eval-banana/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/writeitai/eval-banana/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/writeitai/eval-banana/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/writeitai/eval-banana/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/writeitai/eval-banana/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/writeitai/eval-banana/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/writeitai/eval-banana/releases/tag/v0.0.1
