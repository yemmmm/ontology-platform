#!/usr/bin/env python3
"""Development-only OWL reasoner command.

This command implements the manifest/stdout contract used by
``CommandOwlReasonerRunner`` so local reasoning workflows can run without a
Java OWL reasoner installed. It only reports a deterministic, conservative
success result; it does not perform OWL DL reasoning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: dev_owl_reasoner.py <manifest.json>", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"cannot read manifest: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid manifest json: {exc}", file=sys.stderr)
        return 2

    tasks = list(manifest.get("tasks") or [])
    documents = list(manifest.get("documents") or [])
    payload = {
        "consistent": True,
        "classification": {
            "mode": "development_stub",
            "source_graph_count": len(documents),
        },
        "entailments": [],
        "metadata": {
            "engine_name": "development_stub",
            "engine_version": "dev",
            "tasks": tasks,
            "warning": "Development stub only; no OWL DL reasoning was performed.",
        },
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
