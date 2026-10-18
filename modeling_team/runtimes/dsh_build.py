"""Freeze the selected local Harness build; expose built dependencies, never its checkout."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

PINNED_COMMIT = "687f282e8625c6b8d11ff58211a90524be2e4317"
PLUGINS = tuple(
    "@deepseek-ai/dsh-" + name
    for name in (
        "llm",
        "session",
        "session-projection",
        "system-prompt",
        "tools",
        "fs-local",
        "working-directory",
        "agent",
        "session-persistence-jsonl",
        "session-checkpoint-policy",
        "llm-deepseek-api-key",
        "agent-loop",
        "llm-retry",
        "compaction-basic",
        "mcp-client",
        "sdk-jsonrpc-server",
    )
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_build(root: Path) -> dict:
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PINNED_COMMIT:
        raise RuntimeError(
            f"dsh-build-incompatible: expected {PINNED_COMMIT}, found {commit}; revalidate SDK contract"
        )
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "*/package.json"], text=True
    )
    packages = {}
    for relative in tracked.splitlines():
        path = root / relative
        data = json.loads(path.read_text())
        if data.get("name"):
            packages[data["name"]] = (path.parent, data)
    pending = ["@deepseek-ai/cordis", *PLUGINS]
    selected = {}
    while pending:
        name = pending.pop()
        if name in selected or name not in packages:
            continue
        path, data = packages[name]
        entry = path / data.get("main", "lib/index.js")
        if not entry.is_file() and name in ("@deepseek-ai/cordis", *PLUGINS):
            raise RuntimeError(
                f"dsh-build-missing: {name}; build the pinned Harness dependencies first"
            )
        selected[name] = (path, entry, data)
        for key in ("dependencies", "peerDependencies", "optionalDependencies"):
            pending.extend(data.get(key, {}))
    missing = set(["@deepseek-ai/cordis", *PLUGINS]) - selected.keys()
    if missing:
        raise RuntimeError(f"dsh-build-missing: {sorted(missing)}")
    mounts = []
    files = {}
    for name, (path, entry, data) in sorted(selected.items()):
        for part in ("package.json", "lib", "bin", "locale", "node_modules"):
            source = path / part
            if source.exists():
                mounts.append(str(source))
                if part != "node_modules":
                    for file in [source] if source.is_file() else source.rglob("*"):
                        if file.is_file() and file.suffix not in {".ts", ".map"}:
                            files[str(file.relative_to(root))] = digest(file)
    pnpm = root / "node_modules" / ".pnpm"
    if not pnpm.is_dir():
        raise RuntimeError("dsh-build-missing: installed pnpm dependencies unavailable")
    mounts.append(str(pnpm))
    return {
        "commit": commit,
        "sdk_protocol_sha256": digest(root / "packages/sdk/protocol/lib/index.js"),
        "lock_sha256": digest(root / "pnpm-lock.yaml"),
        "build_files": files,
        "plugins": list(PLUGINS),
        "mounts": sorted(set(mounts)),
        "modules": {name: str(entry) for name, (_, entry, _) in selected.items()},
    }
