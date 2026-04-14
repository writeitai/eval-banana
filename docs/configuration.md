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

## Harness configuration

The harness drives an AI coding agent before checks run. Configure it in TOML or via CLI flags.

### `[harness]` section

| Key | Default | Env var | Description |
|---|---|---|---|
| `agent` | (none) | `EVAL_BANANA_HARNESS_AGENT` | Agent template name (e.g. `codex`, `claude`, `gemini`) |
| `prompt` | (none) | `EVAL_BANANA_HARNESS_PROMPT` | Inline task prompt |
| `prompt_file` | (none) | `EVAL_BANANA_HARNESS_PROMPT_FILE` | Path to prompt file (relative to project root) |
| `model` | (none) | `EVAL_BANANA_HARNESS_MODEL` | Override agent's default model |
| `reasoning_effort` | (none) | `EVAL_BANANA_HARNESS_REASONING_EFFORT` | Reasoning effort level |
| `skills_dir` | `skills` | (none) | Repo-local skill source directory (relative to project root unless absolute) |

Either `prompt` or `prompt_file` must be set when a harness agent is configured. They are mutually exclusive.

Relative `prompt_file` and `skills_dir` paths resolve from the project root.

### `[harness.env]` section

Extra environment variables injected into the harness subprocess:

```toml
[harness.env]
CI = "1"
PYTHONUNBUFFERED = "1"
```

### Skill distribution

`eval-banana distribute-skills` copies repo-local skills from `skills/` into agent-specific generated directories before a supported harness runs.

- Supported target agents are currently `claude` and `codex`.
- Unsupported agents are safe no-ops.
- Missing `skills/` directories are also a no-op.
- Generated directories such as `.claude/skills/` and `.codex/skills/` should usually be gitignored.

```bash
eval-banana distribute-skills
eval-banana distribute-skills --target-agents codex
eval-banana distribute-skills --dry-run
```

### `[agents.*]` sections

Override built-in agent templates or define custom ones. Built-in templates exist for: `codex`, `gemini`, `claude`, `openhands`, `opencode`, `pi`.

```toml
[agents.codex]
default_model = "gpt-5.4"
reasoning_effort = "high"
```

Omitted fields inherit from the built-in template. Custom agents must provide `command`:

```toml
[agents.myagent]
command = ["my-cli", "run"]
shared_flags = ["--headless"]
prompt_flag = "--prompt"
model_flag = "--model"
```

### `[agents.<name>.provider_env]`

Provider-wide env vars for the agent subprocess. Values may contain `{env:VARNAME}` placeholders resolved from the parent shell:

```toml
[agents.claude.provider_env]
ANTHROPIC_BASE_URL = "https://openrouter.ai/api"
ANTHROPIC_AUTH_TOKEN = "{env:OPENROUTER_API_KEY}"
ANTHROPIC_API_KEY = ""
```

### Harness failure behavior

If the harness fails (non-zero exit code or spawn error), checks are **not** run and the eval run is marked as failed. Use `--skip-harness` to suppress a configured harness and score the current workspace state.

### Missing credentials

If an `llm_judge` check runs but credentials are missing, it returns an `error` result with a remediation message. It does **not** skip silently. Other check types continue running normally.

## Provider normalization

When `provider = "codex"` is set, defaults change automatically:

| Setting | `openai_compat` default | `codex` default |
|---|---|---|
| `model` | `openai/gpt-4.1-mini` | `gpt-4.1-mini` |
| `api_base` | `https://openrouter.ai/api/v1` | (not used) |

Codex always uses the hardcoded ChatGPT backend URL. The `api_base` config has no effect for Codex.
