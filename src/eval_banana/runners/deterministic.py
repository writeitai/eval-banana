from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from eval_banana.config import Config
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.models import DeterministicCheckDefinition
from eval_banana.reporter import safe_file_stem

logger = logging.getLogger(__name__)

_FROZEN_SCRIPT_LAUNCHER = """
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

logical_path = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])
context_path = sys.argv[3]
code = compile(snapshot_path.read_bytes(), str(logical_path), "exec")

sys.argv[:] = [str(logical_path), context_path]
sys.path[0] = str(logical_path.parent)
main_module = ModuleType("__main__")
main_module.__file__ = str(logical_path)
main_module.__loader__ = SourceFileLoader("__main__", str(logical_path))
main_module.__package__ = None
main_module.__spec__ = None
main_module.__cached__ = None
sys.modules["__main__"] = main_module
exec(code, main_module.__dict__)
""".strip()


@dataclass(frozen=True)
class FrozenDeterministicScript:
    """Immutable bytes or read error captured for a referenced check script."""

    logical_path: Path
    content: bytes | None
    error_detail: str | None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(*, started: datetime, completed: datetime) -> int:
    return int((completed - started).total_seconds() * 1000)


def _resolve_script_path(
    *,
    check: DeterministicCheckDefinition,
    source_path: Path,
    temp_dir: Path,
    script_snapshot: FrozenDeterministicScript | None,
) -> Path:
    """Materialize the exact inline or frozen referenced script to execute."""

    if check.script is not None:
        return _write_inline_script(script=check.script, temp_dir=temp_dir)

    if check.script_path is None:
        msg = "deterministic check is missing script source"
        raise FileNotFoundError(msg)

    if script_snapshot is not None:
        if script_snapshot.error_detail is not None:
            raise FileNotFoundError(script_snapshot.error_detail)
        if script_snapshot.content is None:
            msg = "frozen deterministic script has neither content nor an error"
            raise FileNotFoundError(msg)
        return _write_frozen_script(
            script_bytes=script_snapshot.content, temp_dir=temp_dir
        )

    script_path = (source_path.parent / check.script_path).resolve()
    if not script_path.is_file():
        msg = f"Deterministic script not found: {script_path}"
        raise FileNotFoundError(msg)
    return script_path


def freeze_referenced_script(
    *, check: DeterministicCheckDefinition, source_path: Path
) -> FrozenDeterministicScript | None:
    """Read a referenced script once so hashing and execution share its bytes."""

    if check.script_path is None:
        return None

    script_path = (source_path.parent / check.script_path).resolve()
    if not script_path.is_file():
        return FrozenDeterministicScript(
            logical_path=script_path,
            content=None,
            error_detail=f"Deterministic script not found: {script_path}",
        )
    try:
        return FrozenDeterministicScript(
            logical_path=script_path,
            content=script_path.read_bytes(),
            error_detail=None,
        )
    except OSError as exc:
        return FrozenDeterministicScript(
            logical_path=script_path, content=None, error_detail=str(exc)
        )


def _build_context_payload(
    *,
    check: DeterministicCheckDefinition,
    source_path: Path,
    project_root: Path,
    check_output_dir: Path,
) -> dict[str, Any]:
    """Build the immutable context supplied to one deterministic check."""

    return {
        "check_id": check.id,
        "description": check.description,
        "project_root": str(project_root),
        "source_path": str(source_path.resolve()),
        "output_dir": str(check_output_dir.resolve()),
    }


def _write_inline_script(*, script: str, temp_dir: Path) -> Path:
    """Write an inline script into the private execution directory."""

    script_path = temp_dir / "inline_check.py"
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _write_frozen_script(*, script_bytes: bytes, temp_dir: Path) -> Path:
    """Write the already-hashed referenced script bytes for execution."""

    script_path = temp_dir / "referenced_check.py"
    script_path.write_bytes(script_bytes)
    return script_path


def _build_script_command(
    *,
    script_path: Path,
    context_path: Path,
    script_snapshot: FrozenDeterministicScript | None,
) -> list[str]:
    """Build a command that preserves a frozen script's logical path semantics."""

    if script_snapshot is None:
        return [sys.executable, str(script_path), str(context_path)]
    return [
        sys.executable,
        "-c",
        _FROZEN_SCRIPT_LAUNCHER,
        str(script_snapshot.logical_path),
        str(script_path),
        str(context_path),
    ]


def run_deterministic_check(
    *,
    check: DeterministicCheckDefinition,
    check_definition_sha256: str,
    source_path: Path,
    project_root: Path,
    output_dir: Path,
    config: Config,
    script_snapshot: FrozenDeterministicScript | None = None,
) -> CheckResult:
    """Execute one deterministic check and bind its result to the definition hash.

    Inline or referenced Python is run with a structured context file. When
    orchestration supplies a referenced-script snapshot, the runner executes
    those exact already-hashed bytes while retaining the original ``__file__``,
    ``sys.argv[0]``, and import path. Exit zero passes, a non-zero exit fails,
    and launch/setup errors produce an ``error`` result while preserving
    captured process output when available.
    """

    started = datetime.now(timezone.utc)
    started_at = started.isoformat()
    artifact_stem = safe_file_stem(text=check.id)
    check_output_dir = output_dir / artifact_stem

    try:
        check_output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{artifact_stem}_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            script_path = _resolve_script_path(
                check=check,
                source_path=source_path,
                temp_dir=temp_dir,
                script_snapshot=script_snapshot,
            )
            context_payload = _build_context_payload(
                check=check,
                source_path=source_path,
                project_root=project_root,
                check_output_dir=check_output_dir,
            )
            context_path = temp_dir / "context.json"
            context_path.write_text(
                json.dumps(context_payload, indent=2), encoding="utf-8"
            )
            command = _build_script_command(
                script_path=script_path,
                context_path=context_path,
                script_snapshot=script_snapshot,
            )
            logger.debug("Running deterministic check %s via %s", check.id, command[1])
            completed_process = subprocess.run(
                args=command,
                capture_output=True,
                check=False,
                cwd=project_root,
                text=True,
            )
    except (FileNotFoundError, OSError, PermissionError) as exc:
        logger.error("Deterministic check %s failed to execute: %s", check.id, exc)
        completed = datetime.now(timezone.utc)
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            check_definition_sha256=check_definition_sha256,
            description=check.description,
            source_path=str(source_path.resolve()),
            tags=check.tags,
            status=CheckStatus.error,
            score=0,
            started_at=started_at,
            completed_at=completed.isoformat(),
            duration_ms=_duration_ms(started=started, completed=completed),
            error_detail=str(exc),
        )

    completed = datetime.now(timezone.utc)
    if completed_process.returncode == 0:
        status = CheckStatus.passed
        score = 1
    else:
        status = CheckStatus.failed
        score = 0

    return CheckResult(
        check_id=check.id,
        check_type=CheckType.deterministic,
        check_definition_sha256=check_definition_sha256,
        description=check.description,
        source_path=str(source_path.resolve()),
        tags=check.tags,
        status=status,
        score=score,
        started_at=started_at,
        completed_at=completed.isoformat(),
        duration_ms=_duration_ms(started=started, completed=completed),
        stdout=completed_process.stdout,
        stderr=completed_process.stderr,
        exit_code=completed_process.returncode,
    )
