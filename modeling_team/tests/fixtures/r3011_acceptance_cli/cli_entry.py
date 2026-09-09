#!/usr/bin/env python3
"""Fixture CLI entry: the real ``modeling_team.__main__.main()`` CLI path.

The only thing this wrapper changes is the one external-process boundary the
local canonical MCP forwarder owns: ``McpReadForwarder``'s child ``command``/
``args`` default to the repository backend server (a live database), so the
fixture points that default at the controlled canonical MCP server executable
instead.  Everything else -- argument parsing, run-contract/freeze/handoff
validation, the default acceptance child factory, the private namespace, the
real AF_UNIX sink/proxy sockets and both v3 sessions -- runs unchanged.

Fixture evidence (the resolved ``codex`` executable, the injected forwarder
command, the ticket tool inventory) is written to ``$R3011_FIXTURE_EVIDENCE``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(os.environ["R3011_FIXTURE_REPO"])
CANONICAL = os.environ["R3011_FIXTURE_CANONICAL"]
STATE = os.environ["R3011_FIXTURE_STATE"]
EVIDENCE = Path(os.environ["R3011_FIXTURE_EVIDENCE"])

sys.path.insert(0, str(REPO))

from modeling_team.acceptance_runtime import McpReadForwarder  # noqa: E402

_real_init = McpReadForwarder.__init__


def _fixture_init(self, *, repository_root, read_key, expected_tools, command=None, args=None, **kwargs):
    injected = None
    if command is None and args is None:
        # Controlled canonical backend MCP boundary (production never passes these).
        command = sys.executable
        args = [CANONICAL, "--state-file", STATE, "--evidence-file", str(EVIDENCE) + ".canonical.json"]
        drift = os.environ.get("R3011_FIXTURE_DRIFT", "")
        fail_read = os.environ.get("R3011_FIXTURE_FAIL_READ", "")
        if drift:
            args += ["--drift-after-read", drift]
        if fail_read:
            args += ["--fail-read-after", fail_read]
        injected = [command] + args
    EVIDENCE.write_text(
        json.dumps(
            {
                "forwarder_command": injected,
                "expected_tools": list(expected_tools),
                "codex_resolved": shutil.which("codex"),
                "fixture_codex": os.environ.get("R3011_FIXTURE_CODEX", ""),
                "canonical_is_controlled": bool(injected),
                "read_key_present": bool(read_key),
                "read_key_value": "",
                "path_entries": (os.environ.get("PATH", "").split(":"))[:3],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return _real_init(
        self,
        repository_root=repository_root,
        read_key=read_key,
        expected_tools=expected_tools,
        command=command,
        args=args,
        **kwargs,
    )


McpReadForwarder.__init__ = _fixture_init  # type: ignore[assignment]

from modeling_team import __main__ as cli  # noqa: E402

sys.argv = ["modeling_team", *sys.argv[1:]]
raise SystemExit(cli.main())
