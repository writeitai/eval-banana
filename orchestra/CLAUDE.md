# Orchestration Setup

Inner-loop and outer-loop orchestration agents must assume bundled skills are
installed explicitly, not at runtime.

Before running harness-driven work in a target project, run:

```bash
eb install
```

That installs eval-banana-owned skills into the agent-native directories used by
the supported tools:

- `.claude/skills/`
- `.codex/skills/`
- `.agents/skills/`
- `.gemini/skills/`

Treat those installed directories as generated artifacts. Do not edit them.

The editable source of truth is `src/eval_banana/skills/` in this repository.

If the orchestration flow depends on updated bundled skills, rerun `eb install`
in the target project before starting the harness step.

`eval-banana run` does not install skills as a side effect.

Custom project-specific skills must be managed directly in the agent-native
directories by the operator or orchestration layer.
