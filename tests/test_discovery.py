from __future__ import annotations

from pathlib import Path

from eval_banana.discovery import discover_check_files


def test_auto_discovery_of_multiple_eval_dirs(tmp_path: Path) -> None:
    first = tmp_path / "a" / "eval_checks"
    second = tmp_path / "b" / "eval_checks" / "nested"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "one.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (second / "two.yml").write_text("schema_version: 1\n", encoding="utf-8")

    found = discover_check_files(start_dir=tmp_path, exclude_dirs=[])

    assert found == sorted(
        [(first / "one.yaml").resolve(), (second / "two.yml").resolve()]
    )


def test_excluded_directories_are_skipped(tmp_path: Path) -> None:
    skipped = tmp_path / ".git" / "eval_checks"
    skipped.mkdir(parents=True)
    (skipped / "skip.yaml").write_text("schema_version: 1\n", encoding="utf-8")

    found = discover_check_files(start_dir=tmp_path, exclude_dirs=[".git"])

    assert found == []


def test_explicit_check_dir_limits_scope(tmp_path: Path) -> None:
    explicit = tmp_path / "custom_checks"
    explicit.mkdir()
    (explicit / "one.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    other = tmp_path / "pkg" / "eval_checks"
    other.mkdir(parents=True)
    (other / "two.yaml").write_text("schema_version: 1\n", encoding="utf-8")

    found = discover_check_files(
        start_dir=tmp_path, explicit_check_dir=explicit, exclude_dirs=[]
    )

    assert found == [(explicit / "one.yaml").resolve()]
