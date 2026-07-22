# Design — output-destination capability (caller-named, provenance-stamped result)

*Status: proposed (2026-07-22). Counterpart to loopy-loop's binding design
`design/designs/deterministic-handoff-and-eval-provenance.md` and its **D14**. This is the
eval-banana half; eval-banana knows nothing about loopy-loop and gains a general capability any
orchestrator can use.*

## Problem

Today `eval-banana run` writes its artifacts (`report.json` full/machine-readable, `report.md`
compact/human, per-check output) into an orchestrator-owned directory (`--output-dir` +
`--flat-output`). To surface a verdict to a *consumer contract* that expects a single canonical
file at a fixed path, the consuming agent must **read `report.md` and hand-transcribe** the
verdict into that file. That hand-copy step is fragile: it can land in the wrong path, drift
from the actual run, and carries no machine-readable freshness marker. (In a real loopy-loop
run this exact step put a decisive approval in the wrong file and stalled the loop.)

eval-banana already owns the verdict and all its provenance. It should be able to **write the
result directly to a caller-named destination, stamped with provenance**, so the consumer never
hand-copies.

## What eval-banana owns vs. what it must not

- **Owns / observes:** the run verdict (`run_passed`, `pass_threshold`, per-check status +
  reasons), the judge settings actually used — the **`model` per check** (only `model` is a
  per-check override; `family` and `effort` are run-level harness config) — the **observed
  subject** (the git `commit_before`/`commit_after` bracketing the run **and** the working-tree
  dirty digest, recorded with the algorithm name — eval-banana reads these itself), the tool
  version, and the run timestamp. `EvalReport` carries no git identity today; this capability adds
  it.
- **Must not own / must not invent:** the *consumer's* semantics — which attempt requested the
  run, what the destination path means, or any loop/session identity. Those are **passed in** by
  the caller and echoed verbatim. eval-banana stays a general tool. It **observes** git rather than
  trusting a caller-supplied commit (a caller echo is not an observation).

## The capability

Add to `eval-banana run` (additive, backward-compatible — minor version bump):

```
eval-banana run … \
  --output-dir <artifact-dir> --flat-output        # unchanged: working artifacts
  --result-out <abs-path>                           # NEW: canonical result destination (full path)
  --result-format md|json                           # NEW: default md (see below)
  --provenance-attempt <opaque-id>                  # NEW: the ONE opaque caller-echoed field
  [--provenance-field k=v]…                         # NEW: optional extra caller-echoed pairs
```

There is no `--result-name` (an earlier draft referenced it; `--result-out` is the full path) and
no `--provenance-commit`: **eval-banana observes the commit and dirty-tree digest itself.**

Behavior:

- After scoring, in addition to the existing `--output-dir` artifacts, write a **single
  self-describing result document** to `--result-out`, atomically (temp sibling + `os.replace`),
  creating parent dirs, refusing a symlink target (mirroring the existing `--flat-output` symlink
  refusal in `runner.py`). This is the file the consumer contract points at.
- **`--result-format md` (default): a provenance-headed markdown that doubles as machine-readable.**
  A fenced, parseable header block, then the human report body:

  ````markdown
  ```eval-banana-result v1
  {"schema_version": 1, "tool_version": "0.5.0", "status": "completed",
   "run_passed": true, "pass_threshold": 1.0,
   "harness": {"family": "codex", "effort": "xhigh"},
   "observed": {"commit_before": "4cc2221", "commit_after": "4cc2221",
                "dirty_tree_digest": "…", "dirty_tree_algorithm": "eb-git-status-v2-sha256"},
   "produced_at": "2026-07-22T09:41:00Z",
   "provenance": {"attempt": "<opaque-id>", "…": "…echoed caller fields…"},
   "checks": [{"id": "goal_outcome", "status": "passed", "reason": "…", "model": "gpt-5.6-sol"}]}
  ```
  # Eval result — PASS
  …the same compact body as report.md…
  ````

  A human reads the prose; a consumer parses the fenced block. `family`/`effort` are the run-level
  `harness` config; only `model` varies **per check**. `dirty_tree_algorithm` names the digest
  scheme so a consumer never assumes cross-tool digest equality (it compares commits, and treats a
  dirty tree as needs-fresh-run). This lets the consumer's canonical file be **both** the agent-read
  markdown **and** a provenance-stamped, machine-checkable artifact — no second hand-rendered file.
- **`--result-format json`:** write the same structured object as a standalone `.json`.
- **`status` envelope (formal):** `status ∈ {completed, no_checks, config_error, harness_error}`.
  No-checks and config/harness failures occur **before** a normal report exists (`runner.py`), so
  the document must still be written with the appropriate `status`, `run_passed: false`, the
  observed subject, and an `error` string — so the destination is always present and freshly
  stamped whenever the tool ran, never left stale or absent.
- The document is **deterministic** given a run: the only wall-clock is the single `produced_at`;
  ordering stable; suitable for hashing.
- **Provenance echo:** `--provenance-attempt` and any `--provenance-field k=v` are copied verbatim
  into `provenance`; eval-banana does not interpret them.
- **No `--result-out`:** behavior is exactly as today (pure backward compatibility).

## Why a document that is both human- and machine-readable

The consumer (loopy-loop's `inner_outer_eval`) declares one canonical file, `eval_results.md`, that
**agents read and judge for freshness** (comparing the observed commit to live `HEAD`); the
loopy-loop engine does at most an optional non-gating diagnostic and never parses the block —
evaluation stays advisory. A markdown file with a fenced machine block satisfies both the human and
the machine reader from one artifact, eliminating the transcription step entirely rather than moving
it. Consumers wanting strict JSON use `--result-format json`. eval-banana itself takes no position on
how the consumer uses the provenance — it only writes it truthfully.

## Failure, edge cases, compatibility

- **Atomic + confined:** temp-sibling + `os.replace`; refuse a symlink target at `--result-out`
  (mirrors the existing `--flat-output` symlink refusal in `runner.py`). Parent dirs created.
- **`status` envelope covers pre-report failures:** `no_checks`, `config_error`, `harness_error`
  occur before a normal report exists — the result document is still written with that `status`,
  `run_passed: false`, the observed subject, and an `error` string, so the destination is always
  present and freshly stamped whenever the tool ran. The consumer never special-cases empties, and
  because the consumer only emits a diagnostic (never fails) on a missing/degraded result, a
  degraded status is information, not an error for the loop.
- **Observed, not echoed, git:** eval-banana reads `commit_before`/`commit_after` + dirty-tree
  digest itself; when it cannot (not a git tree) it records `null`, never a guess. This is what
  makes "subject ≠ current HEAD/tree ⇒ stale" decidable downstream.
- **SemVer:** additive flags, new artifact only when requested → **minor** bump (target 0.5.0). The
  flag is additive *within eval-banana* (absent `--result-out` ⇒ today's behavior), but the
  loopy-loop consumer **requires** this version (it has waived backward compatibility and dropped
  the old hand-write fallback); it pins the minimum eval-banana version rather than degrading.
- **Docs/tests:** document under `docs/` (alongside `configuration.md`), add `CHANGELOG.md`
  `[Unreleased] → Added`, and cover: destination written + atomic; observed commit+dirty digest
  (and `null` when non-git); per-check judge settings; each `status` value still writes a stamped
  document; provenance echoed verbatim; symlink refusal; `md` vs `json`; pure backward-compat when
  `--result-out` is absent.

## Out of scope

No loop/session awareness, no knowledge of `eval_results.md` as a name, no enforcement (the
consumer decides what to do with the provenance — loopy-loop's engine only checks presence and keeps
evaluation advisory; its agents judge freshness). eval-banana only writes a truthfully stamped
result where told.
