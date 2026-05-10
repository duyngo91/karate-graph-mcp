"""Shared scan filters for project file discovery."""

from pathlib import Path
from typing import Any, Union


PathLike = Union[str, Path]


def is_excluded_path(path: PathLike, parser_config: Any) -> bool:
    """Return True when path belongs to a configured excluded directory."""
    exclude_dirs = {
        entry.lower()
        for entry in getattr(parser_config, "scan_exclude_directories", [])
    }
    path_parts = [part.lower() for part in Path(path).parts]
    return any(part in exclude_dirs for part in path_parts)
