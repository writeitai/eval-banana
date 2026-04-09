from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _should_skip_dir(name: str, exclude_dirs: set[str]) -> bool:
    return name in exclude_dirs


def _scan_yaml_files(*, root: Path, exclude_dirs: set[str]) -> list[Path]:
    discovered: list[Path] = []
    for current_root, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not _should_skip_dir(dirname, exclude_dirs=exclude_dirs)
            and not (current_path / dirname).is_symlink()
        ]
        for filename in filenames:
            if not filename.endswith((".yaml", ".yml")):
                continue
            discovered.append((current_path / filename).resolve())
    return discovered


def discover_check_files(
    *,
    start_dir: Path,
    explicit_check_dir: Path | None = None,
    exclude_dirs: list[str] | None = None,
) -> list[Path]:
    excluded = set(exclude_dirs or [])
    if explicit_check_dir is not None:
        logger.debug("Scanning explicit check directory %s", explicit_check_dir)
        return sorted(
            _scan_yaml_files(root=explicit_check_dir.resolve(), exclude_dirs=excluded)
        )

    discovered: list[Path] = []
    for current_root, dirnames, _filenames in os.walk(
        start_dir.resolve(), topdown=True, followlinks=False
    ):
        current_path = Path(current_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not _should_skip_dir(dirname, exclude_dirs=excluded)
            and not (current_path / dirname).is_symlink()
        ]
        if current_path.name != "eval_checks":
            continue
        logger.debug("Discovered eval_checks directory %s", current_path)
        discovered.extend(_scan_yaml_files(root=current_path, exclude_dirs=excluded))
        dirnames[:] = []

    return sorted(path.resolve() for path in discovered)
