from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import subprocess
from typing import cast

import pytest
import yaml

from eval_banana.config import Config
from eval_banana.config import load_config
from eval_banana.loader import load_check_definition
from eval_banana.models import CheckDefinition
from eval_banana.models import CheckResult
from eval_banana.models import CheckStatus
from eval_banana.models import CheckType
from eval_banana.reporter import safe_file_stem
from eval_banana.runner import _snapshot_check_definition
from eval_banana.runner import compute_check_definition_sha256
from eval_banana.runner import run_checks
from eval_banana.runners.deterministic import run_deterministic_check

_CHECK_DIGEST_DOMAIN = b"eval-banana/check-definition-sha256/v1\0"


def _expected_definition_digest(
    *,
    definition_bytes: bytes,
    script_bytes: bytes | None = None,
    script_unavailable: bool = False,
) -> str:
    """Reproduce the documented v1 digest framing independently of production."""

    components = [(b"definition.yaml", definition_bytes)]
    if script_bytes is not None:
        components.append((b"referenced-script", script_bytes))
    elif script_unavailable:
        components.append((b"referenced-script-unavailable", b""))
    framed_components = [
        b"".join(
            (
                len(name).to_bytes(length=8, byteorder="big"),
                name,
                len(content).to_bytes(length=8, byteorder="big"),
                content,
            )
        )
        for name, content in components
    ]
    digest_input = b"".join((_CHECK_DIGEST_DOMAIN, *framed_components))
    return f"sha256:{hashlib.sha256(string=digest_input).hexdigest()}"


def test_full_orchestration_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.total_checks == 1
    assert (Path(report.output_dir) / "report.json").is_file()
    assert report.checks[0].check_definition_sha256 == _expected_definition_digest(
        definition_bytes=check_path.read_bytes()
    )
    assert compute_check_definition_sha256(source_path=check_path) == (
        report.checks[0].check_definition_sha256
    )


def test_flat_output_writes_directly_into_exact_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_bytes(
        b"schema_version: 1\r\nid: one\r\ntype: deterministic\r\n"
        b"description: desc\r\nscript: print('ok')\r\n"
    )
    output_dir = tmp_path / "attempt-eval"
    output_dir.mkdir()
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(
        config=make_config(project_root=tmp_path, output_dir=str(output_dir)),
        flat_output=True,
    )

    assert Path(report.output_dir) == output_dir.resolve()
    assert (output_dir / "report.json").is_file()
    assert not (output_dir / report.run_id).exists()
    assert report.checks[0].check_definition_sha256 == _expected_definition_digest(
        definition_bytes=check_path.read_bytes()
    )


def test_flat_output_keeps_all_distinct_check_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Keep colliding labels, case-only IDs, and long-ID artifacts distinct."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_specs = [
        ("plain.yaml", "judge", "plain-marker"),
        ("underscored.yaml", "_judge_", "underscore-marker"),
        ("case.yaml", "Judge", "case-marker"),
        ("long.yaml", "x" * 600, "long-marker"),
    ]
    for filename, check_id, marker in check_specs:
        checks_dir.joinpath(filename).write_text(
            data="\n".join(
                [
                    "schema_version: 1",
                    f"id: {check_id}",
                    "type: harness_judge",
                    f"description: Judge {marker}.",
                    f"instructions: Inspect {marker}.",
                ]
            ),
            encoding="utf-8",
        )
    output_dir = tmp_path / "attempt-eval"
    captured: dict[str, tuple[str, str]] = {}
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_run(
        *, args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Capture the exact prompt argument supplied to the harness process."""

        prompt = args[-1]
        sequence = len(captured)
        stdout = f'{{"score": 1, "reason": "complete-{sequence}"}}'
        stderr = f"diagnostic-{sequence}"
        captured[prompt] = (stdout, stderr)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr("eval_banana.runners.harness_judge.subprocess.run", fake_run)

    report = run_checks(
        config=make_config(
            project_root=tmp_path,
            cwd=str(tmp_path),
            output_dir=str(output_dir),
            harness_agent="codex",
        ),
        flat_output=True,
    )

    output_checks = output_dir / "checks"
    stems = {
        check_id: safe_file_stem(text=check_id)
        for _filename, check_id, _marker in check_specs
    }
    assert len({stem.casefold() for stem in stems.values()}) == len(check_specs)
    for check_id, stem in stems.items():
        digest = hashlib.sha256(string=check_id.encode(encoding="utf-8")).hexdigest()
        assert stem.endswith(f"-{digest}")
        assert len(stem) <= 105

    for _filename, check_id, marker in check_specs:
        stem = stems[check_id]
        matching_prompts = [
            prompt for prompt in captured if f"Inspect {marker}." in prompt
        ]
        assert len(matching_prompts) == 1
        prompt = matching_prompts[0]
        stdout, stderr = captured[prompt]
        assert (
            output_checks.joinpath(f"{stem}.prompt.txt").read_text(encoding="utf-8")
            == prompt
        )
        payload = json.loads(
            s=output_checks.joinpath(f"{stem}.json").read_text(encoding="utf-8")
        )
        assert payload["check_id"] == check_id
        assert payload["stdout"] == stdout
        assert payload["stderr"] == stderr
        assert (
            output_checks.joinpath(f"{stem}.stdout.txt").read_text(encoding="utf-8")
            == stdout
        )
        assert (
            output_checks.joinpath(f"{stem}.stderr.txt").read_text(encoding="utf-8")
            == stderr
        )

    expected_stems = set(stems.values())
    for suffix in (".json", ".prompt.txt", ".stdout.txt", ".stderr.txt"):
        assert {
            path.name.removesuffix(suffix) for path in output_checks.glob(f"*{suffix}")
        } == expected_stems
    assert report.total_checks == len(check_specs)
    assert report.run_passed is True


def test_deterministic_context_output_dirs_are_safe_and_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Give real deterministic checks distinct evidence dirs for tricky IDs."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_ids = ["probe", "Probe", "_probe_", "probe_", "x" * 600]
    evidence_script = """\
import json
import sys
from pathlib import Path

context = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
output_dir = Path(context["output_dir"])
output_dir.mkdir(parents=True, exist_ok=True)
output_dir.joinpath("context-evidence.json").write_text(
    data=json.dumps(
        {
            "check_id": context["check_id"],
            "output_dir": context["output_dir"],
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
"""
    for index, check_id in enumerate(check_ids):
        definition = {
            "schema_version": 1,
            "id": check_id,
            "type": "deterministic",
            "description": f"Record context evidence for check {index}.",
            "script": evidence_script,
        }
        checks_dir.joinpath(f"check-{index}.yaml").write_text(
            data=yaml.safe_dump(data=definition, sort_keys=False), encoding="utf-8"
        )

    output_dir = tmp_path / "attempt-eval"
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(
        config=make_config(
            project_root=tmp_path, cwd=str(tmp_path), output_dir=str(output_dir)
        ),
        flat_output=True,
    )

    output_checks = output_dir / "checks"
    stems = {check_id: safe_file_stem(text=check_id) for check_id in check_ids}
    assert len({stem.casefold() for stem in stems.values()}) == len(check_ids)
    assert report.total_checks == len(check_ids)
    assert all(result.status == CheckStatus.passed for result in report.checks)

    expected_context_dirs: set[Path] = set()
    for check_id, stem in stems.items():
        expected_context_dir = (output_checks / stem).resolve()
        expected_context_dirs.add(expected_context_dir)
        evidence = json.loads(
            s=expected_context_dir.joinpath("context-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        assert evidence == {
            "check_id": check_id,
            "output_dir": str(expected_context_dir),
        }
        result_payload = json.loads(
            s=output_checks.joinpath(f"{stem}.json").read_text(encoding="utf-8")
        )
        assert result_payload["check_id"] == check_id

    assert {path.resolve() for path in output_checks.iterdir() if path.is_dir()} == (
        expected_context_dirs
    )


def test_public_definition_digest_matches_harness_judge_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Expose the producer's canonical harness-check digest to orchestrators."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "judge.yaml"
    check_path.write_bytes(
        b"schema_version: 1\r\nid: judge\r\ntype: harness_judge\r\n"
        b"description: Judge output.\r\ninstructions: Inspect the result.\r\n"
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        """Return a passing harness result with the supplied canonical digest."""

        return CheckResult(
            check_id="judge",
            check_type=CheckType.harness_judge,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="Judge output.",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path, cwd=str(tmp_path), harness_agent="codex"
        )
    )

    expected = _expected_definition_digest(definition_bytes=check_path.read_bytes())
    assert compute_check_definition_sha256(source_path=check_path) == expected
    assert report.checks[0].check_definition_sha256 == expected


def test_public_definition_digest_preserves_exact_yaml_bytes(tmp_path: Path) -> None:
    """Treat line endings as definition bytes rather than normalized YAML."""

    check_path = tmp_path / "one.yaml"
    crlf_bytes = (
        b"schema_version: 1\r\nid: one\r\ntype: deterministic\r\n"
        b"description: desc\r\nscript: print('ok')\r\n"
    )
    check_path.write_bytes(crlf_bytes)
    crlf_digest = compute_check_definition_sha256(source_path=check_path)
    check_path.write_bytes(crlf_bytes.replace(b"\r\n", b"\n"))

    assert compute_check_definition_sha256(source_path=check_path) != crlf_digest


def test_public_definition_digest_resolves_yaml_symlink_before_adjacent_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Match discovery/runtime when a YAML symlink references an adjacent script."""

    definitions_dir = tmp_path / "definitions"
    definitions_dir.mkdir()
    definition_path = definitions_dir / "one.yaml"
    definition_path.write_text(
        data="\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script_path: adjacent.py",
            ]
        ),
        encoding="utf-8",
    )
    real_script = b"raise SystemExit(0)\n"
    definitions_dir.joinpath("adjacent.py").write_bytes(real_script)

    project_root = tmp_path / "project"
    checks_dir = project_root / "eval_checks"
    checks_dir.mkdir(parents=True)
    check_link = checks_dir / "linked.yaml"
    check_link.symlink_to(definition_path)
    checks_dir.joinpath("adjacent.py").write_bytes(b"raise SystemExit(9)\n")
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(
        config=make_config(project_root=project_root, cwd=str(project_root))
    )

    expected = _expected_definition_digest(
        definition_bytes=definition_path.read_bytes(), script_bytes=real_script
    )
    assert report.checks[0].status == CheckStatus.passed
    assert report.checks[0].check_definition_sha256 == expected
    assert compute_check_definition_sha256(source_path=check_link) == expected


def test_referenced_script_bytes_change_digest_and_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Bind each verdict to the referenced script snapshot that produced it."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script_path: check.py",
            ]
        ),
        encoding="utf-8",
    )
    script_path = checks_dir / "check.py"
    passing_script = b"raise SystemExit(0)\n"
    failing_script = b"raise SystemExit(9)\n"
    script_path.write_bytes(passing_script)
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    config = make_config(project_root=tmp_path, cwd=str(tmp_path))

    passing_report = run_checks(config=config)
    script_path.write_bytes(failing_script)
    failing_report = run_checks(config=config)

    passing_result = passing_report.checks[0]
    failing_result = failing_report.checks[0]
    assert passing_result.status == CheckStatus.passed
    assert failing_result.status == CheckStatus.failed
    assert passing_result.check_definition_sha256 == _expected_definition_digest(
        definition_bytes=check_path.read_bytes(), script_bytes=passing_script
    )
    assert failing_result.check_definition_sha256 == _expected_definition_digest(
        definition_bytes=check_path.read_bytes(), script_bytes=failing_script
    )
    assert compute_check_definition_sha256(source_path=check_path) == (
        failing_result.check_definition_sha256
    )
    assert (
        passing_result.check_definition_sha256 != failing_result.check_definition_sha256
    )


def test_public_definition_digest_matches_unavailable_script_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Keep the public digest in parity with an unavailable-script error run."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script_path: missing.py",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    expected = _expected_definition_digest(
        definition_bytes=check_path.read_bytes(), script_unavailable=True
    )
    assert report.checks[0].status == CheckStatus.error
    assert report.checks[0].check_definition_sha256 == expected
    assert compute_check_definition_sha256(source_path=check_path) == expected


def test_referenced_script_executes_frozen_bytes_after_live_file_changes(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    """Prevent a post-snapshot file mutation from racing hash and execution."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script_path: check.py",
            ]
        ),
        encoding="utf-8",
    )
    script_path = checks_dir / "check.py"
    passing_script = b"raise SystemExit(0)\n"
    script_path.write_bytes(passing_script)
    discovered_definition = load_check_definition(path=check_path)

    execution_definition, definition_sha256, script_snapshot = (
        _snapshot_check_definition(
            source_path=check_path, expected_definition=discovered_definition
        )
    )
    script_path.write_bytes(b"raise SystemExit(11)\n")
    assert execution_definition.type == "deterministic"
    result = run_deterministic_check(
        check=execution_definition,
        check_definition_sha256=definition_sha256,
        source_path=check_path,
        project_root=tmp_path,
        output_dir=tmp_path / "out" / "checks",
        config=make_config(project_root=tmp_path),
        script_snapshot=script_snapshot,
    )

    assert result.status == CheckStatus.passed
    assert result.check_definition_sha256 == _expected_definition_digest(
        definition_bytes=check_path.read_bytes(), script_bytes=passing_script
    )


def test_frozen_referenced_script_preserves_logical_file_for_adjacent_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    """Keep ``__file__``-relative assets working from a frozen script snapshot."""

    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script_path: scripts/check.py",
            ]
        ),
        encoding="utf-8",
    )
    scripts_dir = checks_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "asset.txt").write_text("expected", encoding="utf-8")
    (scripts_dir / "helper.py").write_text("VALUE = 7\n", encoding="utf-8")
    script_path = scripts_dir / "check.py"
    script_path.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "from helper import VALUE",
                'asset = (Path(__file__).parent / "asset.txt").read_text()',
                "logical_argv = Path(sys.argv[0]) == Path(__file__)",
                'passed = asset == "expected" and logical_argv and VALUE == 7',
                "raise SystemExit(0 if passed else 1)",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.checks[0].status == CheckStatus.passed


def test_flat_output_rejects_nonempty_directory_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "attempt-eval"
    output_dir.mkdir()
    (output_dir / "foreign.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit, match="output directory is not empty"):
        run_checks(
            config=make_config(project_root=tmp_path, output_dir=str(output_dir)),
            flat_output=True,
        )

    assert (output_dir / "foreign.txt").read_text(encoding="utf-8") == "keep"


def test_flat_output_rejects_symlink_directory(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    actual_output = tmp_path / "actual-output"
    actual_output.mkdir()
    output_link = tmp_path / "attempt-eval"
    output_link.symlink_to(actual_output, target_is_directory=True)

    with pytest.raises(SystemExit, match="exact output path is a symlink"):
        run_checks(
            config=make_config(project_root=tmp_path, output_dir=str(output_link)),
            flat_output=True,
        )


def test_flat_output_rejects_relative_output_dir_symlink(tmp_path: Path) -> None:
    """Reject a relative CLI output path whose exact target is a symlink."""
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    actual_output = tmp_path / "actual-output"
    actual_output.mkdir()
    output_link = tmp_path / "attempt-eval"
    output_link.symlink_to(actual_output, target_is_directory=True)
    config = load_config(
        cwd=str(tmp_path), output_dir="attempt-eval", use_project_config=False
    )

    with pytest.raises(SystemExit, match="exact output path is a symlink"):
        run_checks(config=config, flat_output=True)


def test_definition_snapshot_rejects_semantic_change_after_discovery(
    tmp_path: Path,
) -> None:
    check_path = tmp_path / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: first",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    discovered_definition = load_check_definition(path=check_path)
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: changed",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="changed after discovery"):
        _snapshot_check_definition(
            source_path=check_path, expected_definition=discovered_definition
        )


def test_no_checks_found(tmp_path: Path, make_config: Callable[..., Config]) -> None:
    with pytest.raises(SystemExit, match="No checks found"):
        run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))


def test_check_id_filtering_with_relaxed_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    good = checks_dir / "good.yaml"
    bad = checks_dir / "bad.yaml"
    good.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: good",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    bad.write_text(":\n-", encoding="utf-8")
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="good",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(good),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="good"
    )

    assert report.total_checks == 1
    assert report.checks[0].check_id == "good"


def test_check_id_succeeds_with_broken_yaml_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "target.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: target",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "broken.yaml").write_text("not: [valid", encoding="utf-8")
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="target",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(checks_dir / "target.yaml"),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="target"
    )

    assert report.run_passed is True


def test_check_id_detects_duplicates(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for name in ("a.yaml", "b.yaml"):
        (checks_dir / name).write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    "id: dup",
                    "type: deterministic",
                    "description: desc",
                    "script: print('ok')",
                ]
            ),
            encoding="utf-8",
        )

    with pytest.raises(SystemExit, match="Duplicate check id"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="dup"
        )


def test_tag_filter_runs_only_matching_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    alpha = checks_dir / "alpha.yaml"
    beta = checks_dir / "beta.yaml"
    alpha.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: alpha",
                "type: deterministic",
                "description: alpha",
                "tags: [migration, smoke]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    beta.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: beta",
                "type: deterministic",
                "description: beta",
                "tags: [docs]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        check = cast(CheckDefinition, kwargs["check"])
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description=check.description,
            source_path=str(kwargs["source_path"]),
            tags=list(check.tags),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), tags=["migration"]
    )

    assert report.total_checks == 1
    assert [check.check_id for check in report.checks] == ["alpha"]
    assert report.checks[0].tags == ["migration", "smoke"]


def test_tag_filter_with_no_matches_fails(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "one.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "tags: [migration]",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="No checks found"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)),
            tags=["nonexistent"],
        )


def test_no_tag_filter_runs_all_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for check_id, tag in (("alpha", "migration"), ("beta", "docs")):
        (checks_dir / f"{check_id}.yaml").write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    f"id: {check_id}",
                    "type: deterministic",
                    f"description: {check_id}",
                    f"tags: [{tag}]",
                    "script: print('ok')",
                ]
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        check = cast(CheckDefinition, kwargs["check"])
        return CheckResult(
            check_id=check.id,
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description=check.description,
            source_path=str(kwargs["source_path"]),
            tags=list(check.tags),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.total_checks == 2
    assert [check.check_id for check in report.checks] == ["alpha", "beta"]


def test_harness_judge_without_harness_aborts_before_runner_is_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    judge_path = checks_dir / "judge.yaml"
    judge_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: judge_check",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    message = str(excinfo.value)
    assert "harness_judge check requires a harness" in message
    assert str(judge_path) in message
    assert "[harness] agent" in message
    assert "--harness-agent" in message


def test_harness_judge_with_harness_configured_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    judge_path = checks_dir / "judge.yaml"
    judge_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: judge_check",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    called = {"runner": False}
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)
    monkeypatch.setattr(
        "eval_banana.runner.write_report_files", lambda report, output_dir: None
    )

    def fake_runner(**kwargs: object) -> CheckResult:
        called["runner"] = True
        return CheckResult(
            check_id="judge_check",
            check_type=CheckType.harness_judge,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(judge_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(
            project_root=tmp_path, cwd=str(tmp_path), harness_agent="codex"
        )
    )

    assert called["runner"] is True
    assert report.run_passed is True


def test_deterministic_run_with_no_harness_agent_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    check_path = checks_dir / "one.yaml"
    check_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: one",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="one",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(check_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(config=make_config(project_root=tmp_path, cwd=str(tmp_path)))

    assert report.run_passed is True


def test_check_id_targeting_deterministic_ignores_unrelated_harness_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    deterministic_path = checks_dir / "a.yaml"
    deterministic_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("eval_banana.runner.emit_console_report", lambda report: None)

    def fake_runner(**kwargs: object) -> CheckResult:
        return CheckResult(
            check_id="a",
            check_type=CheckType.deterministic,
            check_definition_sha256=str(kwargs["check_definition_sha256"]),
            description="desc",
            source_path=str(deterministic_path),
            status=CheckStatus.passed,
            score=1,
            started_at="2026-04-09T12:00:00+00:00",
            completed_at="2026-04-09T12:00:01+00:00",
            duration_ms=1000,
        )

    monkeypatch.setattr("eval_banana.runner._select_runner", lambda check: fake_runner)

    report = run_checks(
        config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="a"
    )

    assert report.run_passed is True
    assert report.checks[0].check_id == "a"


def test_check_id_targeting_harness_judge_without_harness_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "a.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a",
                "type: deterministic",
                "description: desc",
                "script: print('ok')",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit, match="harness_judge check requires a harness"):
        run_checks(
            config=make_config(project_root=tmp_path, cwd=str(tmp_path)), check_id="b"
        )


def test_mixed_checks_without_harness_aborts_on_harness_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    (checks_dir / "a_deterministic.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: a_det",
                "type: deterministic",
                "description: desc",
                "script: print(ok)",
            ]
        ),
        encoding="utf-8",
    )
    (checks_dir / "b_judge.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: b_judge",
                "type: harness_judge",
                "description: desc",
                "instructions: Judge the output.",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eval_banana.runner._select_runner", lambda check: pytest.fail("must not run")
    )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    assert "harness_judge check requires a harness" in str(excinfo.value)
    assert str(checks_dir / "b_judge.yaml") in str(excinfo.value)


def test_multiple_harness_judge_without_harness_reports_sorted_first(
    tmp_path: Path, make_config: Callable[..., Config]
) -> None:
    checks_dir = tmp_path / "eval_checks"
    checks_dir.mkdir()
    for name, check_id in (("z_last.yaml", "z_last"), ("a_first.yaml", "a_first")):
        (checks_dir / name).write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    f"id: {check_id}",
                    "type: harness_judge",
                    "description: desc",
                    "instructions: Judge the output.",
                ]
            ),
            encoding="utf-8",
        )

    with pytest.raises(SystemExit) as excinfo:
        run_checks(config=make_config(project_root=tmp_path, harness_agent=None))

    message = str(excinfo.value)
    assert "harness_judge check requires a harness" in message
    assert str(checks_dir / "a_first.yaml") in message
    assert str(checks_dir / "z_last.yaml") not in message
