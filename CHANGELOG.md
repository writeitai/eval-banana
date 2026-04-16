# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- `task_based` check type and its runner. The harness covers arbitrary-command
  execution needs; keeping `task_based` around added a third overlapping way to
  run subprocesses. Existing YAML files with `type: task_based` will now fail
  validation — convert them to a `deterministic` check (invoking the same
  command from a short Python script) or run the command as part of a harness.

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

[Unreleased]: https://github.com/writeitai/eval-banana/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/writeitai/eval-banana/releases/tag/v0.0.1
