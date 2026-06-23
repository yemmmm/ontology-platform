#!/usr/bin/env python3
"""Small dependency-free HTTP helpers for ontology-builder scripts."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def token(value: str | None) -> str | None:
    return value or os.getenv("ONTOLOGY_PLATFORM_TOKEN")


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
    auth_token: str | None = None,
    timeout: float = 30,
) -> Any:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Platform unavailable: {exc.reason}") from exc
    return json.loads(content) if content else None


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
