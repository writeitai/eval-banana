from __future__ import annotations

import logging
from pathlib import Path

from pydantic import TypeAdapter
from pydantic import ValidationError
import yaml

from eval_banana.models import CheckDefinition

logger = logging.getLogger(__name__)

_CHECK_DEFINITION_ADAPTER = TypeAdapter(CheckDefinition)


def load_check_definition(*, path: Path) -> CheckDefinition:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"Failed to parse YAML in {path}: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(raw, dict):
        msg = f"Invalid check definition in {path}: top-level YAML must be a mapping"
        raise ValueError(msg)

    try:
        return _CHECK_DEFINITION_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        msg = f"Invalid check definition in {path}: {exc}"
        raise ValueError(msg) from exc


def load_check_definitions(*, paths: list[Path]) -> list[tuple[Path, CheckDefinition]]:
    loaded: list[tuple[Path, CheckDefinition]] = []
    seen: dict[str, Path] = {}

    for path in paths:
        definition = load_check_definition(path=path)
        existing = seen.get(definition.id)
        if existing is not None:
            msg = f"Duplicate check id '{definition.id}' found in {existing} and {path}"
            raise ValueError(msg)
        seen[definition.id] = path
        loaded.append((path, definition))

    return loaded
