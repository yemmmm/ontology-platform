"""Wait in an active Host tool call for private work or the next card check."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Sequence

from .delivery_host_actions import SESSION_EVENTS_FILENAME, host_action_state
from .host_ops import HostOpError


def wait_for_host_work(
    session_root: Path,
    *,
    timeout: float = 180,
    seen_request_ids: Sequence[str] = (),
) -> dict:
    """Return new actionable identities; never approve, consume or resume work."""
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout must be a finite nonnegative number")
    started = time.monotonic()
    deadline = started + timeout
    journal = session_root / SESSION_EVENTS_FILENAME
    seen = set(seen_request_ids)
    previous = None
    while True:
        try:
            stat = journal.stat()
            signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            signature = ()
        if previous is None or signature != previous:
            state = host_action_state(session_root)
            previous = signature
            requests = [
                {key: item[key] for key in ("request_id", "run_id", "kind")}
                for item in [*state["pending"], *state["unresolved"]]
                if item["request_id"] not in seen
            ]
            if requests or not state["history_complete"]:
                return {
                    "reason": "host_action" if requests else "journal_incomplete",
                    "requests": requests,
                    "limitations": state["limitations"],
                    "elapsed_seconds": time.monotonic() - started,
                }
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "reason": "periodic_check",
                "requests": [],
                "limitations": [],
                "elapsed_seconds": time.monotonic() - started,
            }
        time.sleep(min(1, remaining))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--seen-request-id", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        result = wait_for_host_work(
            args.session_root,
            timeout=args.timeout,
            seen_request_ids=args.seen_request_id,
        )
    except HostOpError as exc:
        print(json.dumps({"ok": False, "error": exc.as_envelope()}, ensure_ascii=False))
        return 2
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
