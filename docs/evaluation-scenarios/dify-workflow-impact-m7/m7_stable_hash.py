#!/usr/bin/env python3
"""Print the canonical stable-content hash for the frozen M7 scenario tree."""

from __future__ import annotations

import hashlib
from pathlib import Path


SCENARIO_ROOT = Path(__file__).resolve().parent
EXCLUDED_DIRS = {"runtime", ".pytest_cache", "__pycache__"}
EXCLUDED_NAMES = {"attempts.jsonl"}


def included_files(root: Path = SCENARIO_ROOT) -> list[Path]:
    """Return sorted relative files, excluding mutable runtime/ledger and interpreter caches."""
    return sorted(
        (
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and path.name not in EXCLUDED_NAMES
            and not any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts)
        ),
        key=lambda path: path.as_posix(),
    )


def stable_scenario_hash(root: Path = SCENARIO_ROOT) -> str:
    """Hash sorted ``relative-path NUL file-sha256 LF`` records, not shell-specific output."""
    digest = hashlib.sha256()
    for relative in included_files(root):
        content_hash = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


if __name__ == "__main__":
    print(stable_scenario_hash())
