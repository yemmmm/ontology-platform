#!/usr/bin/env python3
"""Read-only file-spool gateway for the independent M3 consumer Agent."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from m3_file_spool_gateway import FileSpoolGateway


def consumer_request_allowed(request: dict[str, object], project_id: str, ontology_id: str) -> bool:
    method, path = request.get("method"), request.get("path")
    if method == "POST":
        return path == "/api/semantic/sparql:query"
    if method != "GET" or not isinstance(path, str):
        return False
    return path in {
        "/openapi.json",
        "/api/health",
        f"/api/projects/{project_id}/build-context",
        f"/api/ontologies/{ontology_id}/modeling-context",
    } or path.startswith(f"/api/ontologies/{ontology_id}/semantic-read-models/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--ontology-id", required=True)
    args = parser.parse_args()
    api_key = os.environ.get("M3_API_KEY")
    if not api_key:
        raise SystemExit("M3_API_KEY must exist only in the host gateway environment")
    gateway = FileSpoolGateway(
        requests=args.requests,
        responses=args.responses,
        archive=args.archive,
        audit_path=args.audit,
        api_key=api_key,
        request_allowed=lambda request: consumer_request_allowed(
            request, args.project_id, args.ontology_id
        ),
    )
    try:
        while True:
            gateway.process_once()
            __import__("time").sleep(0.05)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
