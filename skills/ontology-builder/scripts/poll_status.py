#!/usr/bin/env python3
"""Poll proposal or document state until it reaches a terminal/waiting status."""

import argparse
import time

from http_client import print_json, request, token


TERMINAL = {
    "proposal": {"validated", "approved", "rejected", "applied"},
    "document": {"parsed", "failed"},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=sorted(TERMINAL), required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token")
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    path = f"/proposals/{args.id}" if args.kind == "proposal" else f"/source-documents/{args.id}"
    deadline = time.monotonic() + args.timeout
    while True:
        result = request(args.base_url, path, auth_token=token(args.token))
        status = result.get("status") if args.kind == "proposal" else result.get("parse_status")
        if status in TERMINAL[args.kind] or time.monotonic() >= deadline:
            print_json(result)
            if status not in TERMINAL[args.kind]:
                raise SystemExit(f"Timed out waiting for {args.kind} {args.id}; last status={status}")
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
