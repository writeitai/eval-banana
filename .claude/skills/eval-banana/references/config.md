# Configuration reference

Complete reference for eval-banana configuration: TOML layout, precedence rules, environment variables, and provider-specific auth setup.

## Table of contents

- File locations
- Config sections
- Precedence rules
- Environment variables
- OpenRouter setup
- OpenAI setup
- Codex setup
- Provider normalization
- Common config mistakes

## File locations

| Tier | Path | Purpose |
|---|---|---|
| Global | `~/.eval-banana/config.toml` | User-wide defaults across all projects |
| Local | `.eval-banana/config.toml` | Project-specific settings |

Local config is found by walking upward from the current directory. Running `eval-banana` from any subdirectory finds the nearest project config.

Create config files with:

```bash
eval-banana init          # Local (also creates eval_checks/example_check.yaml)
eval-banana init --global # Global
eval-banana init --force  # Overwrite existing
```

## Config sections

### `[core]` section

| Key | Default | Description |
|---|---|---|
| `output_dir` | `.eval-banana/results` | Where run artifacts are written (relative to project root) |
| `pass_threshold` | `1.0` | Minimum `points/total` ratio for the run to pass (0.0-1.0) |
| `deterministic_timeout_seconds` | `30` | Default timeout for deterministic checks |
| `llm_timeout_seconds` | `90` | Default timeout for LLM judge checks |
| `task_timeout_seconds` | `300` | Default timeout for task-based checks |
| `llm_max_input_chars` | `12000` | Max characters sent to LLM **per target file** (not cumulative) |

### `[llm]` section

| Key | Default | Description |
|---|---|---|
| `provider` | `openai_compat` | Either `openai_compat` or `codex` |
| `model` | `openai/gpt-4.1-mini` | Model name (OpenRouter-style for default) |
| `api_base` | `https://openrouter.ai/api/v1` | API base URL |
| `api_key` | `""` | Explicit API key (prefer env vars instead) |
| `codex_auth_path` | `""` | Path to Codex auth JSON (empty = use defaults) |

### `[discovery]` section

| Key | Default | Description |
|---|---|---|
| `exclude_dirs` | `[".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]` | Directories to skip when walking for `eval_checks/` |

Lists replace entirely — a local `exclude_dirs` replaces the global list, it does not append.

## Precedence rules

Config values are resolved in this order (highest priority first):

1. **CLI arguments** (`--model`, `--provider`, `--api-base`, etc.)
2. **`EVAL_BANANA_*` environment variables**
3. **Provider-aware API key fallback** (`OPENROUTER_API_KEY` / `OPENAI_API_KEY` based on `api_base`)
4. **Local project config** (`.eval-banana/config.toml`)
5. **Global config** (`~/.eval-banana/config.toml`)
6. **Built-in defaults**

Dict sections merge recursively. A local `[core]` override changes only the keys it sets; other `[core]` keys inherit from global.

## Environment variables

| Variable | Maps to |
|---|---|
| `EVAL_BANANA_OUTPUT_DIR` | `core.output_dir` |
| `EVAL_BANANA_PASS_THRESHOLD` | `core.pass_threshold` |
| `EVAL_BANANA_DETERMINISTIC_TIMEOUT_SECONDS` | `core.deterministic_timeout_seconds` |
| `EVAL_BANANA_LLM_TIMEOUT_SECONDS` | `core.llm_timeout_seconds` |
| `EVAL_BANANA_TASK_TIMEOUT_SECONDS` | `core.task_timeout_seconds` |
| `EVAL_BANANA_LLM_MAX_INPUT_CHARS` | `core.llm_max_input_chars` |
| `EVAL_BANANA_PROVIDER` | `llm.provider` |
| `EVAL_BANANA_MODEL` | `llm.model` |
| `EVAL_BANANA_API_BASE` | `llm.api_base` |
| `EVAL_BANANA_API_KEY` | `llm.api_key` (generic fallback) |
| `EVAL_BANANA_CODEX_AUTH_PATH` | `llm.codex_auth_path` |
| `OPENROUTER_API_KEY` | `llm.api_key` if `api_base` contains `openrouter.ai` |
| `OPENAI_API_KEY` | `llm.api_key` if `api_base` contains `api.openai.com` |

## OpenRouter setup (default)

OpenRouter is the default provider and model namespace.

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
eval-banana run
```

That's all. Defaults already point at `https://openrouter.ai/api/v1` with model `openai/gpt-4.1-mini`.

To use a different OpenRouter model:

```toml
# .eval-banana/config.toml
[llm]
model = "anthropic/claude-sonnet-4.5"
```

Or:

```bash
eval-banana run --model anthropic/claude-sonnet-4.5
```

## OpenAI setup (direct)

Use OpenAI directly instead of through OpenRouter:

```toml
# .eval-banana/config.toml
[llm]
provider = "openai_compat"
model = "gpt-4.1-mini"
api_base = "https://api.openai.com/v1"
```

```bash
export OPENAI_API_KEY=sk-...
eval-banana run
```

The provider-aware key resolution automatically picks `OPENAI_API_KEY` when `api_base` contains `api.openai.com`. It will never send `OPENROUTER_API_KEY` to OpenAI or vice versa.

## Codex setup (local ChatGPT subscription)

Uses your local ChatGPT Codex credentials. The backend URL is **hardcoded** — `api_base` has no effect.

```bash
codex login  # One-time setup; creates ~/.codex/auth.json
eval-banana run --provider codex
```

Or pin the provider in config:

```toml
# .eval-banana/config.toml
[llm]
provider = "codex"
model = "gpt-4.1-mini"
```

Auth file resolution order:
1. `llm.codex_auth_path` in config
2. `EVAL_BANANA_CODEX_AUTH_PATH` env var
3. `$CODEX_HOME/auth.json`
4. `~/.codex/auth.json`

If the token is missing or expired, LLM judge checks return `error` with a "run `codex login`" remediation message.

## Provider normalization

When `provider = "codex"` is set and `model` / `api_base` aren't explicitly set, eval-banana auto-switches defaults:

| Setting | `openai_compat` default | `codex` default |
|---|---|---|
| `model` | `openai/gpt-4.1-mini` | `gpt-4.1-mini` (no namespace prefix) |
| `api_base` | `https://openrouter.ai/api/v1` | (unused — Codex has a hardcoded backend) |

If your local config was created by `eval-banana init` (which writes explicit `model` and `api_base` values), those take priority over the codex defaults. Delete them from your local config if you want codex normalization to kick in, or set them to codex-appropriate values manually.

## Generated config templates

### Global (`~/.eval-banana/config.toml`) template

```toml
# Global eval-banana configuration.
# Project-level .eval-banana/config.toml overrides these values.


[core]
output_dir = ".eval-banana/results"
pass_threshold = 1.0
deterministic_timeout_seconds = 30
llm_timeout_seconds = 90
task_timeout_seconds = 300
llm_max_input_chars = 12000


[llm]
provider = "openai_compat"
model = "openai/gpt-4.1-mini"
api_base = "https://openrouter.ai/api/v1"
api_key = ""
codex_auth_path = ""


[discovery]
exclude_dirs = [".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]
```

### Local (`.eval-banana/config.toml`) template

Same as global, minus `api_key` and `codex_auth_path` (committed configs should never contain keys).

## Common config mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Setting `OPENAI_API_KEY` while `api_base` points at OpenRouter | LLM checks return `error: Missing API key` | Set `OPENROUTER_API_KEY`, or change `api_base` to OpenAI |
| `pass_threshold: 80` (integer) | All runs fail | Use `pass_threshold = 0.8` (float, 0.0-1.0) |
| Committing `api_key` in `.eval-banana/config.toml` | Credential leak | Use env vars, add file to `.gitignore` if needed |
| Relative `output_dir` resolved from wrong cwd | Results appear in unexpected locations | eval-banana always resolves from `project_root`, not `pwd` |
| Expecting `api_base` to work with `provider = "codex"` | Codex still hits ChatGPT backend | Codex backend URL is hardcoded — `api_base` is ignored |
| Replacing `exclude_dirs` with an incomplete list | `.git`, `.venv` get scanned | Lists replace, not merge — include all default entries |
