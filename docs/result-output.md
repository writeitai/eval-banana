# Result output (provenance-stamped destination)

`eval-banana run` normally writes its artifacts (`report.json`, `report.md`,
per-check output) into an orchestrator-owned directory (`--output-dir` /
`--flat-output`). When a consumer contract instead expects a single canonical
file at a fixed path, use `--result-out` to have eval-banana write that file
directly, stamped with provenance, so nothing has to be hand-copied.

This capability is additive. Without `--result-out`, behavior is exactly as
before.

## Flags

```
eval-banana run … \
  --result-out <path>              # canonical result destination (full path)
  --result-format md|json          # default: md
  --provenance-attempt <opaque-id> # opaque caller id, echoed verbatim
  [--provenance-field k=v]…         # extra caller pairs, echoed verbatim (repeatable)
```

- `--result-out <path>` writes the result document to this exact path. Parent
  directories are created. The write is atomic (a temp sibling is written and
  `os.replace`d into place). A symlink at the destination is refused, mirroring
  the `--flat-output` symlink refusal.
- `--result-format` selects `md` (default) or `json` (see below).
- `--provenance-attempt` and `--provenance-field k=v` are copied verbatim into
  the document's `provenance` object. eval-banana never interprets them. A
  `--provenance-field` without a `=` is a usage error.

There is no `--result-name` (the destination is the full `--result-out` path)
and no `--provenance-commit`: eval-banana observes the git subject itself.

## Formats

### `md` (default)

A fenced, machine-parseable block followed by the same compact body as
`report.md`:

````markdown
```eval-banana-result v1
{
  "schema_version": 1,
  "tool_version": "0.5.0",
  "status": "completed",
  "run_passed": true,
  "pass_threshold": 1.0,
  "harness": {"family": "codex", "effort": "xhigh"},
  "observed": {
    "commit_before": "4cc2221…",
    "commit_after": "4cc2221…",
    "dirty_tree_digest": "sha256:…",
    "dirty_tree_algorithm": "eb-git-status-v2-sha256"
  },
  "produced_at": "2026-07-22T09:41:00+00:00",
  "provenance": {"attempt": "attempt-7", "session": "s1"},
  "checks": [
    {"id": "goal_outcome", "status": "passed", "reason": "…", "model": "gpt-5.6-sol"}
  ],
  "error": null
}
```
# eval-banana report
…the same compact body as report.md…
````

A human reads the prose; a consumer parses the fenced block. One file satisfies
both readers, so there is no second hand-rendered artifact.

### `json`

The same structured object written as a standalone `.json` file.

## The stamped object

| Field | Meaning |
|---|---|
| `schema_version` | Always `1`. |
| `tool_version` | Installed eval-banana version. |
| `status` | `completed`, `no_checks`, `config_error`, or `harness_error`. |
| `run_passed` | Run verdict; `false` for any failure status. |
| `pass_threshold` | The effective pass threshold. |
| `harness.family` | Configured harness agent (run-level). |
| `harness.effort` | Effective reasoning effort (run-level). |
| `observed.commit_before` / `commit_after` | `HEAD` before and after the run. |
| `observed.dirty_tree_digest` | Working-tree dirty digest, or `null`. |
| `observed.dirty_tree_algorithm` | `eb-git-status-v2-sha256`, or `null`. |
| `produced_at` | Single ISO timestamp — the only wall-clock in the body. |
| `provenance` | `attempt` plus any echoed `--provenance-field` pairs. |
| `checks[]` | `{id, status, reason, model}` per check (`model` is per-check). |
| `error` | Failure description, or `null` on success. |

Only `model` varies per check; `family` and `effort` are run-level harness
config.

## Observed git subject

eval-banana reads git itself rather than trusting a caller-supplied commit:

- `commit_before` and the dirty-tree digest are read at run start (before the
  run), and `commit_after` after it. Observing the digest at run start means a
  harness/judge that writes into the tree mid-run cannot make a clean-at-start
  tree look dirty.
- The dirty-tree digest is computed from `git status --porcelain` framed with
  the unstaged (`git diff`) and staged (`git diff --cached`) content, hashed
  with SHA-256. `dirty_tree_algorithm` names the scheme
  (`eb-git-status-v2-sha256`) so a consumer never assumes cross-tool digest
  equality — it compares commits and treats a dirty tree as needs-fresh-run.
- When the working directory is not a git tree, every observed field is `null`,
  never a guess.

## Status envelope

`status ∈ {completed, no_checks, config_error, harness_error}`.

No-checks and config/harness failures happen before a normal report exists. The
result document is still written, with the appropriate `status`,
`run_passed: false`, the observed git block, an `error` string, and empty
`checks`. The destination is therefore always present and freshly stamped
whenever the tool ran, never left stale or absent — and the tool still exits
non-zero on failure.
