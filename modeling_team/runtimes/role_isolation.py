"""Small shared immutable-role staging and Linux namespace primitives."""

from __future__ import annotations

import shutil
from pathlib import Path


def stage_skills(package, target: Path) -> None:
    seen: set[str] = set()
    for source in package.required_skills:
        directory = source.parent
        if directory.name in seen:
            raise RuntimeError("duplicate staged Skill directory")
        seen.add(directory.name)
        shutil.copytree(directory, target / directory.name, symlinks=False)
        for item in (target / directory.name).rglob("*"):
            if item.is_symlink():
                raise RuntimeError("Skill staging refuses symlinks")
            if item.is_file():
                item.chmod(0o444)


def namespace_base() -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bubblewrap is required for per-Agent isolation")
    command = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/agent/home",
    ]
    for source in (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ld.so.cache",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/nsswitch.conf",
        "/etc/ssl/certs",
    ):
        if Path(source).exists():
            command += ["--ro-bind", source, source]
    return command
