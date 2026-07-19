from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import re

from eval_banana.models import EvalReport

logger = logging.getLogger(__name__)

_SAFE_STEM_LABEL_LENGTH = 40
_STDOUT_TAIL_CHARS = 2000


def emit_console_report(*, report: EvalReport) -> None:
    print(f"Run ID: {report.run_id}")
    print(f"Score: {report.points_earned}/{report.total_points}")
    print(f"Percentage: {report.percentage:.1f}%")
    print(f"Passed: {'yes' if report.run_passed else 'no'}")
    for check in report.checks:
        summary = check.reason or check.error_detail or ""
        print(
            f"- {check.check_id}: {check.status.value}"
            f"{f' - {summary}' if summary else ''}"
        )


def safe_file_stem(*, text: str) -> str:
    """Return a bounded label plus the full SHA-256 of one exact check ID.

    The digest preserves practical uniqueness across case-insensitive
    filesystems and arbitrarily long valid IDs. The short normalized prefix is
    only a human-readable label; every artifact for a check uses this one stem.
    """

    collapsed = re.sub(pattern=r"[^a-zA-Z0-9._-]+", repl="_", string=text).strip("._")
    label = collapsed[:_SAFE_STEM_LABEL_LENGTH] or "check"
    digest = hashlib.sha256(string=text.encode(encoding="utf-8")).hexdigest()
    return f"{label}-{digest}"


def persist_check_stdout(*, output_dir: Path, check_id: str, stdout: str) -> str | None:
    """Persist one check's full stdout stream and return its run-relative path.

    ``output_dir`` is the run's ``checks`` directory. The file always holds the
    untruncated stream so report consumers can open it when the report's bounded
    ``stdout`` tail is not enough. Runners own this artifact -- the report only
    keeps a pointer to it. Returns ``None`` when there is no output to persist.
    The stem is unique per check ID, so concurrent checks never collide.
    """

    if not stdout:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_file_stem(text=check_id)
    (output_dir / f"{stem}.stdout.txt").write_text(stdout, encoding="utf-8")
    return f"{output_dir.name}/{stem}.stdout.txt"


def bound_stdout_tail(*, stdout: str, raw_response_path: str | None) -> str:
    """Return ``stdout`` bounded to its final characters for in-report display.

    Short output is returned unchanged. Longer output is replaced by a banner
    naming the persisted full-output file followed by the last
    ``_STDOUT_TAIL_CHARS`` characters, keeping enough tail for error display
    while dropping the multi-megabyte judge streams from ``report.json``.
    """

    if len(stdout) <= _STDOUT_TAIL_CHARS:
        return stdout
    location = raw_response_path or "the persisted stdout artifact"
    banner = (
        f"[eval-banana: stdout truncated to the last {_STDOUT_TAIL_CHARS} "
        f"characters; full output at {location}]\n"
    )
    return banner + stdout[-_STDOUT_TAIL_CHARS:]


def _build_markdown_report(*, report: EvalReport) -> str:
    lines = [
        "# eval-banana report",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Run ID | `{report.run_id}` |",
        f"| Score | `{report.points_earned}/{report.total_points}` |",
        f"| Percentage | `{report.percentage:.1f}%` |",
        f"| Pass Threshold | `{report.pass_threshold}` |",
        f"| Run Passed | `{report.run_passed}` |",
        "",
    ]
    lines.extend(
        [
            "| Check ID | Type | Status | Score | Duration (ms) |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for check in report.checks:
        lines.append(
            f"| `{check.check_id}` | `{check.check_type.value}` | "
            f"`{check.status.value}` | `{check.score}` | `{check.duration_ms}` |"
        )

    details_blocks: list[str] = []
    for check in report.checks:
        if not check.reason and not check.error_detail:
            continue
        details_blocks.extend(
            ["", f"## {check.check_id}", "", f"- Status: `{check.status.value}`"]
        )
        if check.reason:
            details_blocks.append(f"- Reason: {check.reason}")
        if check.error_detail:
            details_blocks.append(f"- Error: {check.error_detail}")

    return "\n".join(lines + details_blocks).strip() + "\n"


def write_report_files(*, report: EvalReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks_dir = output_dir / "checks"
    checks_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(
        _build_markdown_report(report=report), encoding="utf-8"
    )

    for check in report.checks:
        stem = safe_file_stem(text=check.check_id)
        (checks_dir / f"{stem}.json").write_text(
            check.model_dump_json(indent=2), encoding="utf-8"
        )
        # The full stdout stream is persisted by the runner (see
        # persist_check_stdout); report.json keeps only the bounded tail plus a
        # pointer, so the reporter never rewrites the truncated stdout here.
        if check.stderr:
            (checks_dir / f"{stem}.stderr.txt").write_text(
                check.stderr, encoding="utf-8"
            )
    logger.info("Wrote report files to %s", output_dir)
