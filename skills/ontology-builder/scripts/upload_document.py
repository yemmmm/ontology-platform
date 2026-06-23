#!/usr/bin/env python3
"""Upload a PDF, Markdown, or text document using multipart/form-data."""

import argparse
import mimetypes
import uuid
from pathlib import Path

from http_client import print_json, request, token


ALLOWED_TYPES = {"application/pdf", "text/markdown", "text/plain"}


def multipart(file: Path, media_type: str) -> tuple[bytes, str]:
    boundary = f"ontology-builder-{uuid.uuid4().hex}"
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media_type\"\r\n\r\n{media_type}\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{file.name}\"\r\nContent-Type: {media_type}\r\n\r\n"
        ).encode(),
        file.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token")
    parser.add_argument("--media-type")
    args = parser.parse_args()
    media_type = args.media_type or mimetypes.guess_type(args.file.name)[0] or "text/plain"
    if media_type not in ALLOWED_TYPES:
        raise SystemExit(f"Unsupported media type: {media_type}")
    body, content_type = multipart(args.file, media_type)
    print_json(
        request(
            args.base_url,
            f"/projects/{args.project_id}/source-documents",
            method="POST",
            body=body,
            content_type=content_type,
            auth_token=token(args.token),
            timeout=120,
        )
    )


if __name__ == "__main__":
    main()
