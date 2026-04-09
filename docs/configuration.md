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
