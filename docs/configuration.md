# Configuration

eval-banana uses TOML configuration with two tiers: global (user-wide) and local (project-level).

## Config file locations

| Tier | Path | Purpose |
|---|---|---|
| Global | `~/.eval-banana/config.toml` | User-wide defaults |
| Local | `.eval-banana/config.toml` | Project-specific settings |

Local config is found by walking upward from the current directory. This means you can run `eval-banana` from any subdirectory and it will find the project config.

## Creating config

```bash
eval-banana init          # Create local project config
eval-banana init --global  # Create global config
eval-banana init --force   # Overwrite existing config
```

Local init also creates an example check in `eval_checks/`.

## Config sections

### `[core]` section

| Key | Default | Env var | Description |
|---|---|---|---|
| `output_dir` | `.eval-banana/results` | `EVAL_BANANA_OUTPUT_DIR` | Where output files go |
| `pass_threshold` | `1.0` | `EVAL_BANANA_PASS_THRESHOLD` | Minimum pass ratio (0.0-1.0) |
| `deterministic_timeout_seconds` | `30` | `EVAL_BANANA_DETERMINISTIC_TIMEOUT_SECONDS` | Default timeout for deterministic checks |
| `llm_timeout_seconds` | `90` | `EVAL_BANANA_LLM_TIMEOUT_SECONDS` | Default timeout for LLM judge checks |
| `task_timeout_seconds` | `300` | `EVAL_BANANA_TASK_TIMEOUT_SECONDS` | Default timeout for task-based checks |
| `llm_max_input_chars` | `12000` | `EVAL_BANANA_LLM_MAX_INPUT_CHARS` | Max characters sent to LLM per target file |

### `[llm]` section

| Key | Default | Env var | Description |
|---|---|---|---|
| `provider` | `openai_compat` | `EVAL_BANANA_PROVIDER` | LLM provider (`openai_compat` or `codex`) |
| `model` | `openai/gpt-4.1-mini` | `EVAL_BANANA_MODEL` | Model name |
| `api_base` | `https://openrouter.ai/api/v1` | `EVAL_BANANA_API_BASE` | API base URL |
| `api_key` | (empty) | `EVAL_BANANA_API_KEY` | API key (prefer env vars) |
| `codex_auth_path` | (empty) | `EVAL_BANANA_CODEX_AUTH_PATH` | Path to Codex auth file |

### `[discovery]` section

| Key | Default | Description |
|---|---|---|
| `exclude_dirs` | see below | Directories to skip during discovery |

Default excluded directories: `.git`, `.hg`, `.svn`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`.

### `[harnesses.<name>]` sections

Harnesses are optional presets for `task_based` checks only.

| Key | Type | Required | Description |
|---|---|---|---|
| `command` | `list[str]` | Yes | Base argv to execute. Must be non-empty. |
| `shared_flags` | `list[str]` | No | Extra argv entries inserted after `command`. |
| `default_model` | `str` | No | Model used when the check omits `task_based.model`. |
| `model_flag` | `str` | No | CLI flag paired with the selected model. |
| `model_env_vars` | `list[str]` | No | Env vars set to the selected model when one is selected. |
| `provider_env` | `table` | No | String env vars resolved at execution time. |

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

## Precedence rules

Config values are resolved in this order (highest priority first):

1. **CLI arguments** (`--model`, `--provider`, etc.)
2. **Environment variables** (`EVAL_BANANA_*`)
3. **Provider-aware API key fallback** (see below)
4. **Local project config** (`.eval-banana/config.toml`)
5. **Global config** (`~/.eval-banana/config.toml`)
6. **Built-in defaults**

### Merge behavior

- Dict sections merge recursively (local overrides only the keys it sets)
- Lists replace entirely (local `exclude_dirs` replaces global)
- Relative `output_dir` resolves from the project root
- `harnesses` merge by harness name across global and local config
- Nested harness tables such as `provider_env` deep-merge by key
- Harness list fields (`command`, `shared_flags`, `model_env_vars`) replace on local override

## Task-based harness behavior

When a check sets `harness: <name>`, eval-banana builds the subprocess argv as:

```text
harness.command
+ harness.shared_flags
+ optional (harness.model_flag, selected_model)
+ check.command
```

`check.command` is appended arguments only. Do not repeat the harness binary there.

The subprocess environment is assembled in this order:

```text
os.environ
< resolved harness.provider_env
< model_env_vars (only when a model was selected)
< task_based.env
< injected EVAL_BANANA_* variables
```

`task_based.model` is valid only when `task_based.harness` is also set.

Unknown harness names are runtime per-check errors, not config-load failures, so other checks still run.

## Placeholder resolution

`{env:VAR}` placeholders are supported only inside `harnesses.*.provider_env` values.

- Missing env vars emit one warning per variable name per process
- Missing placeholders substitute `""`
- If the whole value is exactly one placeholder and that env var is unset, the env key is omitted entirely
- `task_based.env` values are passed through verbatim; placeholder syntax is not interpreted there

## Commented harness recipes

`eval-banana init` includes these recipes as comments only. They do not create hidden runtime defaults.

```toml
# Native Codex
# [harnesses.codex]
# command = ["codex", "exec"]
# shared_flags = ["--skip-git-repo-check"]
# default_model = "gpt-5.4"
# model_flag = "--model"

# Codex via OpenRouter (export OPENROUTER_API_KEY in your shell)
# [harnesses.codex_openrouter]
# command = ["codex", "exec"]
# shared_flags = [
#   "--skip-git-repo-check",
#   "-c", "model_provider=openrouter",
#   "-c", "model_providers.openrouter.base_url=\"https://openrouter.ai/api/v1\"",
#   "-c", "model_providers.openrouter.env_key=\"OPENROUTER_API_KEY\"",
# ]
# default_model = "openai/gpt-4.1-mini"
# model_flag = "--model"
```

```toml
# Native Claude
# [harnesses.claude]
# command = ["claude"]
# shared_flags = ["--dangerously-skip-permissions"]
# model_flag = "--model"

# Claude via OpenRouter (export OPENROUTER_API_KEY in your shell)
# [harnesses.claude_openrouter]
# command = ["claude"]
# shared_flags = ["--dangerously-skip-permissions"]
# default_model = "anthropic/claude-sonnet-4.6"
# model_flag = "--model"
# model_env_vars = ["ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"]
# [harnesses.claude_openrouter.provider_env]
# ANTHROPIC_BASE_URL = "https://openrouter.ai/api"
# ANTHROPIC_AUTH_TOKEN = "{env:OPENROUTER_API_KEY}"
# ANTHROPIC_API_KEY = ""
```

```toml
# Native Gemini
# [harnesses.gemini]
# command = ["gemini", "--approval-mode=yolo"]
# default_model = "gemini-2.5-pro"
# model_flag = "--model"

# Gemini via OpenRouter (export OPENROUTER_API_KEY in your shell)
# [harnesses.gemini_openrouter]
# command = ["gemini", "--approval-mode=yolo"]
# default_model = "google/gemini-2.5-pro"
# model_flag = "--model"
# [harnesses.gemini_openrouter.provider_env]
# GEMINI_API_KEY = "{env:OPENROUTER_API_KEY}"
```

## Authentication

### Provider-aware API key resolution

eval-banana is careful never to send credentials to the wrong endpoint:

| API base contains | Keys checked (in order) |
|---|---|
| `openrouter.ai` | `OPENROUTER_API_KEY`, `EVAL_BANANA_API_KEY`, config `api_key` |
| `api.openai.com` | `OPENAI_API_KEY`, `EVAL_BANANA_API_KEY`, config `api_key` |
| Other | `EVAL_BANANA_API_KEY`, config `api_key` |

### OpenRouter setup

```bash
export OPENROUTER_API_KEY=your-key
eval-banana run
```

### OpenAI direct setup

```toml
# .eval-banana/config.toml
[llm]
api_base = "https://api.openai.com/v1"
```

```bash
export OPENAI_API_KEY=your-key
eval-banana run
```

### Codex setup

Codex uses local ChatGPT credentials. The auth file is found in this order:

1. Config `codex_auth_path` or `EVAL_BANANA_CODEX_AUTH_PATH`
2. `$CODEX_HOME/auth.json`
3. `~/.codex/auth.json`

```bash
codex login  # Create auth credentials
eval-banana run --provider codex
```

### Missing credentials

If an `llm_judge` check runs but credentials are missing, it returns an `error` result with a remediation message. It does **not** skip silently. Other check types continue running normally.

## Provider normalization

When `provider = "codex"` is set, defaults change automatically:

| Setting | `openai_compat` default | `codex` default |
|---|---|---|
| `model` | `openai/gpt-4.1-mini` | `gpt-4.1-mini` |
| `api_base` | `https://openrouter.ai/api/v1` | (not used) |

Codex always uses the hardcoded ChatGPT backend URL. The `api_base` config has no effect for Codex.
