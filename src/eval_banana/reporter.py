from __future__ import annotations

import logging
from pathlib import Path
import re

from eval_banana.models import EvalReport

logger = logging.getLogger(__name__)


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


def _safe_file_stem(text: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("._")
    if collapsed:
        return collapsed
    return "check"


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
        "| Check ID | Type | Status | Score | Duration (ms) |",
        "| --- | --- | --- | --- | --- |",
    ]
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
        stem = _safe_file_stem(check.check_id)
        (checks_dir / f"{stem}.json").write_text(
            check.model_dump_json(indent=2), encoding="utf-8"
        )
        if check.stdout:
            (checks_dir / f"{stem}.stdout.txt").write_text(
                check.stdout, encoding="utf-8"
            )
        if check.stderr:
            (checks_dir / f"{stem}.stderr.txt").write_text(
                check.stderr, encoding="utf-8"
            )
    logger.info("Wrote report files to %s", output_dir)
