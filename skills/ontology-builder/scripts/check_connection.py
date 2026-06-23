#!/usr/bin/env python3
"""Check API and durable dependency health without direct database access."""

import argparse

from http_client import print_json, request, token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token")
    args = parser.parse_args()
    print_json(request(args.base_url, "/health/dependencies", auth_token=token(args.token)))


if __name__ == "__main__":
    main()
