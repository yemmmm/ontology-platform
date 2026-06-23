#!/usr/bin/env python3
"""Submit one structured, idempotent proposal envelope."""

import argparse
import json
from pathlib import Path

from http_client import print_json, request, token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token")
    args = parser.parse_args()
    payload = json.loads(args.proposal.read_text(encoding="utf-8"))
    body = json.dumps(payload, ensure_ascii=False).encode()
    print_json(
        request(
            args.base_url,
            "/proposals",
            method="POST",
            body=body,
            content_type="application/json",
            auth_token=token(args.token),
        )
    )


if __name__ == "__main__":
    main()
