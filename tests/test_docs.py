from __future__ import annotations

from pathlib import Path


def test_deprecation_timeline_is_documented_in_configuration_docs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    phrase = "no earlier than 0.3.0"

    assert phrase in (repo_root / "docs" / "configuration.md").read_text(
        encoding="utf-8"
    )
