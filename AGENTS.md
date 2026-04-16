# Agent Setup

This project ships bundled agent skills inside the `eval-banana` package.

Before harness-driven work in a target project, run:

```bash
eb install
```

That command installs bundled skills into the agent-native directories used by
supported tools:

- `.claude/skills/`
- `.codex/skills/`
- `.agents/skills/`
- `.gemini/skills/`

Those installed directories are generated artifacts. Do not edit them in place.

The source of truth lives in `src/eval_banana/skills/` in this repository.

When bundled skills change, rerun `eb install` in the target project.

`eval-banana run` no longer performs skill installation automatically.

If a target project has custom skills, place them directly in the appropriate
agent-native directory. Do not expect eval-banana to copy them from a repo-root
`skills/` directory.
