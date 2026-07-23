from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
import importlib.metadata
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict

from eval_banana.models import EvalReport
from eval_banana.reporter import build_markdown_report

logger = logging.getLogger(__name__)

# Named digest scheme so a consumer never assumes cross-tool digest equality.
# v2 folds staged content (git diff --cached) into the input alongside porcelain
# status and unstaged diff, so a staged-only change is reflected in the digest.
DIRTY_TREE_ALGORITHM = "eb-git-status-v2-sha256"
_RESULT_FENCE_INFO = "eval-banana-result v1"


class ResultStatus:
    """Formal status envelope values for a stamped result document."""

    completed = "completed"
    no_checks = "no_checks"
    config_error = "config_error"
    harness_error = "harness_error"


class HarnessInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str | None
    effort: str | None


class ObservedGit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_before: str | None
    commit_after: str | None
    dirty_tree_digest: str | None
    dirty_tree_algorithm: str | None


class CheckSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    reason: str | None
    model: str | None


class ResultDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    tool_version: str
    status: str
    run_passed: bool
    pass_threshold: float
    harness: HarnessInfo
    observed: ObservedGit
    produced_at: str
    provenance: dict[str, str | None]
    checks: list[CheckSummary]
    error: str | None = None


def _tool_version() -> str:
    """Return eval-banana's installed distribution version."""

    try:
        return importlib.metadata.version("eval-banana")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _run_git(*, args: list[str], cwd: str) -> str | None:
    """Run one git command and return its stdout, or ``None`` on any failure.

    A non-zero exit (for example when *cwd* is not inside a git work tree) and a
    missing git binary both yield ``None`` so callers record ``null`` rather than
    a guessed value.
    """

    try:
        completed = subprocess.run(
            args=["git", *args],
            capture_output=True,
            check=False,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
            text=True,
        )
    except (FileNotFoundError, OSError, PermissionError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def read_head_commit(*, cwd: str) -> str | None:
    """Observe the current ``HEAD`` commit of the work tree at *cwd*.

    Returns ``None`` when *cwd* is not a git work tree or has no commit yet.
    """

    output = _run_git(args=["rev-parse", "HEAD"], cwd=cwd)
    if output is None:
        return None
    commit = output.strip()
    return commit or None


@dataclass(frozen=True)
class ObservedDirtyTree:
    """A work tree's dirty-tree digest and the algorithm that produced it."""

    digest: str | None
    algorithm: str | None


def observe_dirty_tree(*, cwd: str) -> ObservedDirtyTree:
    """Observe the work-tree dirty digest at *cwd* under a named algorithm.

    Hashes ``git status --porcelain`` framed with unstaged (``git diff``) and
    staged (``git diff --cached``) content so a staged-only change is reflected.
    Returns null digest and algorithm when *cwd* is not a git work tree; a clean
    tree yields a stable non-null digest of empty status. Must be observed at run
    start so a harness that dirties the tree mid-run cannot backdate the subject.
    """

    status_output = _run_git(args=["status", "--porcelain"], cwd=cwd)
    if status_output is None:
        return ObservedDirtyTree(digest=None, algorithm=None)
    unstaged_diff = _run_git(args=["diff"], cwd=cwd) or ""
    staged_diff = _run_git(args=["diff", "--cached"], cwd=cwd) or ""
    hasher = hashlib.sha256()
    hasher.update(status_output.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(unstaged_diff.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(staged_diff.encode("utf-8"))
    return ObservedDirtyTree(
        digest=f"sha256:{hasher.hexdigest()}", algorithm=DIRTY_TREE_ALGORITHM
    )


def _extract_reasoning_effort(*, report: EvalReport) -> str | None:
    """Return the run-level effective reasoning effort recorded on any check."""

    for check in report.checks:
        effort = check.details.get("reasoning_effort")
        if isinstance(effort, str):
            return effort
    return None


def _summarize_checks(*, report: EvalReport) -> list[CheckSummary]:
    """Summarize each check with its per-check judge model."""

    summaries: list[CheckSummary] = []
    for check in report.checks:
        model = check.details.get("model")
        summaries.append(
            CheckSummary(
                id=check.check_id,
                status=check.status.value,
                reason=check.reason,
                model=model if isinstance(model, str) else None,
            )
        )
    return summaries


def build_result_document(
    *,
    status: str,
    report: EvalReport | None,
    pass_threshold: float,
    harness_family: str | None,
    observed: ObservedGit,
    provenance: dict[str, str | None],
    error: str | None,
) -> ResultDocument:
    """Build the self-describing result document for one run.

    ``produced_at`` is the single wall-clock stamp in the body. When *report* is
    ``None`` (a pre-report failure), ``run_passed`` is false, ``checks`` is
    empty, and *error* describes the failure.
    """

    effort = _extract_reasoning_effort(report=report) if report is not None else None
    return ResultDocument(
        tool_version=_tool_version(),
        status=status,
        run_passed=report.run_passed if report is not None else False,
        pass_threshold=pass_threshold,
        harness=HarnessInfo(family=harness_family, effort=effort),
        observed=observed,
        produced_at=datetime.now(timezone.utc).isoformat(),
        provenance=provenance,
        checks=_summarize_checks(report=report) if report is not None else [],
        error=error,
    )


def render_result_document(
    *, document: ResultDocument, result_format: str, report: EvalReport | None
) -> str:
    """Render *document* as the ``md`` or ``json`` result artifact text.

    ``md`` emits a fenced, machine-parseable block followed by the same compact
    report body ``report.md`` uses. ``json`` emits the structured object alone.
    """

    payload = document.model_dump_json(indent=2)
    if result_format == "json":
        return f"{payload}\n"

    lines = [f"```{_RESULT_FENCE_INFO}", payload, "```", ""]
    if report is not None:
        lines.append(build_markdown_report(report=report))
    return "\n".join(lines)


def _atomic_write_text(*, target: Path, content: str) -> None:
    """Write *content* to *target* atomically via a temp sibling and replace."""

    fd, temp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f"{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            logger.debug("Could not remove temp result artifact %s", temp_name)
        raise


def write_result_document(
    *,
    document: ResultDocument,
    result_out: Path,
    result_format: str,
    report: EvalReport | None,
) -> None:
    """Write *document* to *result_out* atomically, refusing a symlink target.

    Parent directories are created. A symlink at *result_out* is refused,
    mirroring the ``--flat-output`` symlink refusal in ``runner.py``.
    """

    if result_out.is_symlink():
        msg = f"Refusing --result-out because the path is a symlink: {result_out}"
        raise SystemExit(msg)
    result_out.parent.mkdir(parents=True, exist_ok=True)
    content = render_result_document(
        document=document, result_format=result_format, report=report
    )
    _atomic_write_text(target=result_out, content=content)
    logger.info("Wrote result document to %s", result_out)
