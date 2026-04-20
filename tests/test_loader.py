from __future__ import annotations

from pathlib import Path

import pytest

from eval_banana.loader import load_check_definition
from eval_banana.loader import load_check_definitions


def test_yaml_parse_error_includes_path(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(":\n-", encoding="utf-8")

    with pytest.raises(ValueError, match=str(path)):
        load_check_definition(path=path)


def test_validation_error_includes_path(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "schema_version: 1\nid: bad\ntype: harness_judge\ndescription: x\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=str(path)):
        load_check_definition(path=path)


def test_legacy_type_raises_migration_error(tmp_path: Path) -> None:
    path = tmp_path / "legacy.yaml"
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: bad",
                "type: llm" + "_judge",
                "description: x",
                "target_paths:",
                "  - README.md",
                "instructions: Judge it.",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="renamed to 'harness_judge'"):
        load_check_definition(path=path)


def test_duplicate_check_ids_are_rejected(tmp_path: Path) -> None:
    first = tmp_path / "one.yaml"
    second = tmp_path / "two.yaml"
    payload = "\n".join(
        [
            "schema_version: 1",
            "id: same",
            "type: deterministic",
            "description: desc",
            "script: print('ok')",
        ]
    )
    first.write_text(payload, encoding="utf-8")
    second.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        load_check_definitions(paths=[first, second])

    assert str(first) in str(exc.value)
    assert str(second) in str(exc.value)
