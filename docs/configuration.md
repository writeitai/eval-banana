# Configuration

eval-banana uses a single project-level TOML config at `.eval-banana/config.toml`.

## Config file location

The config file is discovered by walking upward from the current directory. This means you can run `eval-banana` from any subdirectory and it will find the project config.

## Creating config

```bash
eval-banana init          # Create project config
eval-banana init --force   # Overwrite existing config
```

## Config sections

### `[core]` section

| Key | Default | Env var | Description |
|---|---|---|---|
| `output_dir` | `.eval-banana/results` | `EVAL_BANANA_OUTPUT_DIR` | Where output files go |
| `pass_threshold` | `1.0` | `EVAL_BANANA_PASS_THRESHOLD` | Minimum pass ratio (0.0-1.0) |
| `llm_max_input_chars` | `0` (disabled) | `EVAL_BANANA_LLM_MAX_INPUT_CHARS` | Max characters sent to `harness_judge` per target file; 0 = no limit |

### `[discovery]` section

| Key | Default | Description |
|---|---|---|
| `exclude_dirs` | see below | Directories to skip during discovery |

Default excluded directories: `.git`, `.hg`, `.svn`, `.venv`, `venv`, `node_modules`, `__pycache__`, `dist`, `build`.

## Precedence rules

Config values are resolved in this order (highest priority first):

1. **CLI arguments** (`--output-dir`, `--harness-model`, etc.)
2. **Environment variables** (`EVAL_BANANA_*`)
3. **Project config** (`.eval-banana/config.toml`)
4. **Built-in defaults**

### Notes

- Relative `output_dir` resolves from the project root

## Harness configuration

The harness config selects the agent used by `harness_judge` checks.

### `[harness]` section

| Key | Default | Env var | Description |
|---|---|---|---|
| `agent` | (none) | `EVAL_BANANA_HARNESS_AGENT` | Agent template name (e.g. `codex`, `claude`, `gemini`) |
| `model` | (none) | `EVAL_BANANA_HARNESS_MODEL` | Override agent's default model |
| `reasoning_effort` | (none) | `EVAL_BANANA_HARNESS_REASONING_EFFORT` | Reasoning effort level |

### `[harness.env]` section

Extra environment variables injected into the harness subprocess:

```toml
[harness.env]
CI = "1"
PYTHONUNBUFFERED = "1"
```

### Installing skills

eval-banana publishes agent skills in the `skills/` directory of the
[repository](https://github.com/writeitai/eval-banana). Install them into your
project with the [`npx skills` CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add writeitai/eval-banana
```

The CLI auto-detects installed agents and copies skills into their native
directories (`.claude/skills/`, `.codex/skills/`, `.agents/skills/`,
`.gemini/skills/`, etc.). Installed skill directories should usually be
gitignored and treated as installation artifacts.

Legacy config files may still contain `[harness].skills_dir`. eval-banana
ignores that stale key so old configs keep loading, but the key has no
runtime effect.

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

### `harness_judge` requires a harness

If any loaded `harness_judge` check is discovered, eval-banana aborts before running any check when no harness is configured. Fix by setting `[harness] agent` in config or passing `--harness-agent` on the command line.

## Migration note

The legacy `[llm]` section was removed. If it is present in `.eval-banana/config.toml`, eval-banana exits with a migration error telling you to delete that section and use `[harness]` / `[agents.*]` instead.
