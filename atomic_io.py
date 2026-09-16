from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def replace_with_retry(
    source: Path,
    destination: Path,
    attempts: int = 8,
    initial_delay_seconds: float = 0.1,
) -> None:
    """Replace a file, tolerating short-lived Windows scanner/indexer locks."""
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(initial_delay_seconds * min(2**attempt, 16))


def flush_file_to_disk(path: Path) -> None:
    """Ask the OS to persist a completed file before it is published."""
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    replace_with_retry(temporary, path)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True))
