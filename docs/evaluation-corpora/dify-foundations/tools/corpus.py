#!/usr/bin/env python3
"""Verify, rebuild, compare, and query the pinned Dify documentation corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
OFFICIAL_REPOSITORY = "https://github.com/langgenius/dify-docs"
RAW_HOST = "raw.githubusercontent.com"
ALLOWED_PAGE_HOSTS = {"docs.dify.ai", "github.com"}
ALLOWED_LANGUAGES = {"en", "zh", "neutral"}
TRANSLATION_STATUSES = {
    "source",
    "official_same_commit",
    "missing",
    "possibly_stale",
    "not_applicable",
}
ALLOWED_SUFFIXES = {".mdx", ".json"}
TOP_LEVEL_KEYS = {
    "schema_version",
    "corpus_id",
    "snapshot_id",
    "created_at",
    "purpose",
    "scope",
    "non_goals",
    "status",
    "previous_snapshot",
    "change_summary",
    "source",
    "license",
    "required_topics",
    "excluded_categories",
    "entries",
}
SOURCE_KEYS = {
    "repository",
    "commit",
    "commit_time",
    "raw_host",
    "website",
    "navigation_discovery",
}
LICENSE_KEYS = {"spdx", "name", "url", "attribution", "file"}
ENTRY_KEYS = {
    "source_path",
    "snapshot_path",
    "official_page_url",
    "language",
    "title",
    "topics",
    "selection_reason",
    "sha256",
    "translation_of",
    "translation_status",
}
REQUIRED_TOPICS = {
    "product-introduction",
    "application-types",
    "workflow-chatflow",
    "blank-workflow-creation",
    "canvas-orchestration",
    "variables",
    "test-publish",
    "app-reuse",
    "application-template",
    "dsl",
    "start-user-input",
    "llm",
    "if-else",
    "iteration",
    "jinja2-template",
    "output",
    "quick-start-example",
    "navigation-index",
    "license",
}
EXCLUDED_PREFIXES = (
    "api-reference/",
    "develop-plugin/",
    "en/api-reference/",
    "zh/api-reference/",
    "en/develop-plugin/",
    "zh/develop-plugin/",
    "en/self-host/deploy/",
    "zh/self-host/deploy/",
    "en/cloud/use-dify/knowledge/",
    "zh/cloud/use-dify/knowledge/",
    "en/cloud/use-dify/monitor/",
    "zh/cloud/use-dify/monitor/",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SNAPSHOT_ID_RE = re.compile(r"^dify-foundations-\d{4}-\d{2}-\d{2}-[0-9a-f]{7,40}$")
JWT_RE = re.compile(rb"\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")
BEARER_RE = re.compile(rb"(?i)\bbearer\s+(?!<|\{|\[|your[-_ ])[A-Za-z0-9._~-]{24,}\b")
APP_KEY_RE = re.compile(rb"\b(?:app|sk)-[A-Za-z0-9]{24,}\b")
PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class CorpusError(Exception):
    """Raised when the corpus violates its fail-closed contract."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so downloads cannot leave the pinned raw source."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise CorpusError(
            f"download redirect rejected: {code} to {urllib.parse.urlsplit(newurl).hostname}"
        )


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorpusError(f"{label} must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - value.keys())
    unknown = sorted(value.keys() - expected)
    if missing or unknown:
        raise CorpusError(f"{label} keys invalid; missing={missing}, unknown={unknown}")


def _safe_relative_path(raw_path: Any, label: str) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise CorpusError(f"{label} must be a non-empty string")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in raw_path:
        raise CorpusError(f"unsafe {label}: {raw_path!r}")
    return path


def _read_manifest(snapshot_dir: Path) -> tuple[dict[str, Any], bytes]:
    manifest_path = snapshot_dir / "manifest.json"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except FileNotFoundError as exc:
        raise CorpusError(f"manifest not found: {manifest_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"invalid manifest: {exc}") from exc
    return _require_object(manifest, "manifest"), raw


def _validate_url(url: Any, hosts: set[str], label: str) -> None:
    if not isinstance(url, str):
        raise CorpusError(f"{label} must be a string")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.port is not None
        or parsed.username
        or parsed.password
    ):
        raise CorpusError(f"non-official {label}: {url!r}")


def _validate_official_page_url(url: Any, commit: str, source_path: str) -> None:
    _validate_url(url, ALLOWED_PAGE_HOSTS, "official_page_url")
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname != "github.com":
        return
    expected_path = f"/langgenius/dify-docs/blob/{commit}/{source_path}"
    if parsed.path != expected_path or parsed.query or parsed.fragment:
        raise CorpusError(
            "GitHub official_page_url must match the official Dify repository, "
            "fixed commit, and registered source_path"
        )


def _validate_previous_snapshot_chain(manifest: dict[str, Any], snapshot_dir: Path) -> None:
    previous_snapshot = manifest["previous_snapshot"]
    seen = {manifest["snapshot_id"]}
    while previous_snapshot is not None:
        if not isinstance(previous_snapshot, str) or not SNAPSHOT_ID_RE.fullmatch(
            previous_snapshot
        ):
            raise CorpusError("previous_snapshot must be null or a safe Dify snapshot ID")
        if previous_snapshot in seen:
            raise CorpusError(f"previous_snapshot cycle detected: {previous_snapshot}")
        seen.add(previous_snapshot)
        previous_dir = snapshot_dir.parent / previous_snapshot
        if previous_dir.is_symlink() or not previous_dir.is_dir():
            raise CorpusError(f"previous_snapshot directory not found: {previous_snapshot}")
        previous_manifest, _ = _read_manifest(previous_dir)
        if previous_manifest.get("snapshot_id") != previous_snapshot:
            raise CorpusError(f"previous_snapshot manifest identity mismatch: {previous_snapshot}")
        if previous_manifest.get("corpus_id") != manifest["corpus_id"]:
            raise CorpusError(f"previous_snapshot corpus mismatch: {previous_snapshot}")
        previous_snapshot = previous_manifest.get("previous_snapshot")


def _validate_metadata(manifest: dict[str, Any], snapshot_dir: Path) -> list[dict[str, Any]]:
    _require_exact_keys(manifest, TOP_LEVEL_KEYS, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CorpusError(f"unsupported schema_version: {manifest['schema_version']!r}")
    if manifest["corpus_id"] != "dify-foundations":
        raise CorpusError("corpus_id must be 'dify-foundations'")
    if manifest["snapshot_id"] != snapshot_dir.name:
        raise CorpusError("snapshot_id must match the snapshot directory name")
    for field in ("created_at", "purpose", "status", "change_summary"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            raise CorpusError(f"{field} must be a non-empty string")
    for field in ("scope", "non_goals", "required_topics", "excluded_categories"):
        if not isinstance(manifest[field], list) or not all(
            isinstance(item, str) and item for item in manifest[field]
        ):
            raise CorpusError(f"{field} must be a non-empty string list")
    if not manifest["scope"] or not manifest["non_goals"] or not manifest["excluded_categories"]:
        raise CorpusError("scope, non_goals, and excluded_categories must not be empty")
    _validate_previous_snapshot_chain(manifest, snapshot_dir)

    source = _require_object(manifest["source"], "source")
    _require_exact_keys(source, SOURCE_KEYS, "source")
    if source["repository"] != OFFICIAL_REPOSITORY:
        raise CorpusError("source.repository is not the official Dify docs repository")
    if not isinstance(source["commit"], str) or not COMMIT_RE.fullmatch(source["commit"]):
        raise CorpusError("source.commit must be a lowercase 40-character commit SHA")
    if source["raw_host"] != RAW_HOST:
        raise CorpusError(f"source.raw_host must be {RAW_HOST}")
    _validate_url(source["website"], {"docs.dify.ai"}, "source.website")
    _validate_url(source["navigation_discovery"], {"docs.dify.ai"}, "navigation_discovery")
    if not isinstance(source["commit_time"], str) or not source["commit_time"]:
        raise CorpusError("source.commit_time must be a non-empty string")

    license_data = _require_object(manifest["license"], "license")
    _require_exact_keys(license_data, LICENSE_KEYS, "license")
    if license_data["spdx"] != "CC-BY-4.0":
        raise CorpusError("license.spdx must be CC-BY-4.0")
    _validate_url(license_data["url"], {"creativecommons.org"}, "license.url")
    if (
        not isinstance(license_data["attribution"], str)
        or "Dify" not in license_data["attribution"]
    ):
        raise CorpusError("license.attribution must identify Dify")
    license_path = _safe_relative_path(license_data["file"], "license.file")
    if str(license_path) != "official/LICENSE":
        raise CorpusError("license.file must be official/LICENSE")

    required_topics = manifest["required_topics"]
    if len(required_topics) != len(set(required_topics)) or set(required_topics) != REQUIRED_TOPICS:
        raise CorpusError("required_topics must exactly match the v1 corpus topic contract")

    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise CorpusError("entries must be a non-empty list")
    validated: list[dict[str, Any]] = []
    source_paths: set[str] = set()
    snapshot_paths: set[str] = set()
    covered_topics: set[str] = set()
    english_sources: set[str] = set()
    for index, raw_entry in enumerate(entries):
        entry = _require_object(raw_entry, f"entries[{index}]")
        _require_exact_keys(entry, ENTRY_KEYS, f"entries[{index}]")
        source_path = _safe_relative_path(entry["source_path"], "source_path")
        snapshot_path = _safe_relative_path(entry["snapshot_path"], "snapshot_path")
        if str(snapshot_path) != f"official/{source_path}":
            raise CorpusError(f"snapshot_path must be official/<source_path>: {snapshot_path}")
        if str(source_path) in source_paths or str(snapshot_path) in snapshot_paths:
            raise CorpusError(f"duplicate entry path: {source_path}")
        source_paths.add(str(source_path))
        snapshot_paths.add(str(snapshot_path))
        if str(source_path).startswith(EXCLUDED_PREFIXES):
            raise CorpusError(f"excluded corpus category present: {source_path}")
        if source_path.name != "LICENSE" and source_path.suffix not in ALLOWED_SUFFIXES:
            raise CorpusError(f"disallowed content extension: {source_path}")
        if entry["language"] not in ALLOWED_LANGUAGES:
            raise CorpusError(f"invalid language: {entry['language']!r}")
        if entry["translation_status"] not in TRANSLATION_STATUSES:
            raise CorpusError(f"invalid translation_status: {entry['translation_status']!r}")
        if not isinstance(entry["title"], str) or not entry["title"].strip():
            raise CorpusError(f"entry title missing: {source_path}")
        if not isinstance(entry["selection_reason"], str) or not entry["selection_reason"].strip():
            raise CorpusError(f"selection_reason missing: {source_path}")
        if (
            not isinstance(entry["topics"], list)
            or not entry["topics"]
            or not all(
                isinstance(topic, str) and topic in REQUIRED_TOPICS for topic in entry["topics"]
            )
        ):
            raise CorpusError(f"invalid topics: {source_path}")
        if len(entry["topics"]) != len(set(entry["topics"])):
            raise CorpusError(f"duplicate topics: {source_path}")
        covered_topics.update(entry["topics"])
        if not isinstance(entry["sha256"], str) or not SHA256_RE.fullmatch(entry["sha256"]):
            raise CorpusError(f"invalid sha256: {source_path}")
        _validate_official_page_url(entry["official_page_url"], source["commit"], str(source_path))
        translation_of = entry["translation_of"]
        if translation_of is not None:
            translation_of = str(_safe_relative_path(translation_of, "translation_of"))
        language = entry["language"]
        if language == "en":
            if entry["translation_status"] != "source" or translation_of is not None:
                raise CorpusError(f"English entry must be a source: {source_path}")
            english_sources.add(str(source_path))
        elif language == "zh":
            if entry["translation_status"] not in {"official_same_commit", "possibly_stale"}:
                raise CorpusError(f"Chinese entry must be an official translation: {source_path}")
            if translation_of is None:
                raise CorpusError(f"Chinese entry must identify translation_of: {source_path}")
        elif entry["translation_status"] != "not_applicable" or translation_of is not None:
            raise CorpusError(f"neutral entry cannot carry translation metadata: {source_path}")
        validated.append(entry)

    for entry in validated:
        if entry["language"] == "zh" and entry["translation_of"] not in english_sources:
            raise CorpusError(f"translation source is not registered: {entry['translation_of']}")
    if covered_topics != REQUIRED_TOPICS:
        raise CorpusError(
            f"topic coverage mismatch; missing={sorted(REQUIRED_TOPICS - covered_topics)}"
        )
    if "LICENSE" not in source_paths or "docs.json" not in source_paths:
        raise CorpusError("LICENSE and docs.json must be registered")
    return validated


def _scan_secret(data: bytes, path: str) -> None:
    for label, pattern in (
        ("private key", PRIVATE_KEY_RE),
        ("JWT", JWT_RE),
        ("Bearer token", BEARER_RE),
        ("application key", APP_KEY_RE),
    ):
        if pattern.search(data):
            raise CorpusError(f"possible {label} found in {path}; value suppressed")


def _verify_files(snapshot_dir: Path, entries: list[dict[str, Any]]) -> None:
    official_dir = snapshot_dir / "official"
    if official_dir.is_symlink() or not official_dir.is_dir():
        raise CorpusError(f"official directory missing or is a symlink: {official_dir}")
    expected = {entry["snapshot_path"] for entry in entries}
    actual: set[str] = set()
    for root, directories, files in os.walk(official_dir, followlinks=False):
        root_path = Path(root)
        for name in directories:
            if (root_path / name).is_symlink():
                raise CorpusError(f"symlink not allowed: {root_path / name}")
        for name in files:
            path = root_path / name
            if path.is_symlink():
                raise CorpusError(f"symlink not allowed: {path}")
            relative = path.relative_to(snapshot_dir).as_posix()
            actual.add(relative)
            mode = path.stat().st_mode
            if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                raise CorpusError(f"executable content not allowed: {relative}")
    if expected != actual:
        raise CorpusError(
            f"registered file set mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    for entry in entries:
        path = snapshot_dir / entry["snapshot_path"]
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            raise CorpusError(f"sha256 mismatch: {entry['snapshot_path']}")
        _scan_secret(data, entry["snapshot_path"])


def verify_snapshot(snapshot_dir: Path, check_files: bool = True) -> dict[str, Any]:
    """Validate manifest metadata and, by default, every committed file."""

    snapshot_dir = snapshot_dir.resolve()
    manifest, _ = _read_manifest(snapshot_dir)
    entries = _validate_metadata(manifest, snapshot_dir)
    if check_files:
        _verify_files(snapshot_dir, entries)
    return manifest


def _raw_url(manifest: dict[str, Any], source_path: str) -> str:
    quoted_path = "/".join(
        urllib.parse.quote(part, safe="") for part in PurePosixPath(source_path).parts
    )
    return f"https://{RAW_HOST}/langgenius/dify-docs/{manifest['source']['commit']}/{quoted_path}"


def _download(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != RAW_HOST
        or parsed.username
        or parsed.password
    ):
        raise CorpusError(f"download host rejected: {parsed.hostname}")
    request = urllib.request.Request(url, headers={"User-Agent": "ontology-platform-corpus/1"})
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise CorpusError(f"download failed with HTTP {response.status}: {url}")
            return response.read()
    except CorpusError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise CorpusError(f"download failed for {url}: {exc}") from exc


def rebuild_snapshot(snapshot_dir: Path, destination: Path) -> None:
    """Rebuild official bytes from the exact repository commit into an empty directory."""

    snapshot_dir = snapshot_dir.resolve()
    manifest, manifest_raw = _read_manifest(snapshot_dir)
    entries = _validate_metadata(manifest, snapshot_dir)
    destination = destination.resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise CorpusError(f"destination must be absent or empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        url = _raw_url(manifest, entry["source_path"])
        data = _download(url)
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            raise CorpusError(f"download hash mismatch: {entry['source_path']}")
        _scan_secret(data, entry["source_path"])
        output = destination / entry["snapshot_path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    (destination / "manifest.json").write_bytes(manifest_raw)
    verify_snapshot(destination)


def diff_manifests(old_manifest_path: Path, new_manifest_path: Path) -> dict[str, list[str]]:
    """Compare entries by source path and content hash using deterministic ordering."""

    def load(path: Path) -> dict[str, str]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorpusError(f"invalid manifest {path}: {exc}") from exc
        obj = _require_object(value, str(path))
        entries = obj.get("entries")
        if not isinstance(entries, list):
            raise CorpusError(f"manifest entries missing: {path}")
        result: dict[str, str] = {}
        for raw_entry in entries:
            entry = _require_object(raw_entry, f"entry in {path}")
            source_path = str(_safe_relative_path(entry.get("source_path"), "source_path"))
            digest = entry.get("sha256")
            if source_path in result:
                raise CorpusError(f"duplicate source_path in {path}: {source_path}")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise CorpusError(f"invalid sha256 in {path}: {source_path}")
            result[source_path] = digest
        return result

    old = load(old_manifest_path)
    new = load(new_manifest_path)
    old_paths = set(old)
    new_paths = set(new)
    return {
        "added": sorted(new_paths - old_paths),
        "removed": sorted(old_paths - new_paths),
        "modified": sorted(path for path in old_paths & new_paths if old[path] != new[path]),
        "unchanged": sorted(path for path in old_paths & new_paths if old[path] == new[path]),
    }


def locate_topic(snapshot_dir: Path, topic: str) -> list[dict[str, str]]:
    """Locate registered files for a topic without network access."""

    manifest = verify_snapshot(snapshot_dir)
    matches = [
        {
            "source_path": entry["source_path"],
            "snapshot_path": entry["snapshot_path"],
            "title": entry["title"],
            "language": entry["language"],
            "sha256": entry["sha256"],
        }
        for entry in manifest["entries"]
        if topic in entry["topics"]
    ]
    if not matches:
        raise CorpusError(f"unknown or uncovered topic: {topic}")
    return sorted(matches, key=lambda item: (item["source_path"], item["language"]))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="verify a committed snapshot offline")
    verify_parser.add_argument("snapshot_dir", type=Path)
    rebuild_parser = subparsers.add_parser(
        "rebuild", help="rebuild from the pinned official commit"
    )
    rebuild_parser.add_argument("snapshot_dir", type=Path)
    rebuild_parser.add_argument("--destination", required=True, type=Path)
    diff_parser = subparsers.add_parser("diff", help="compare two manifests")
    diff_parser.add_argument("old_manifest", type=Path)
    diff_parser.add_argument("new_manifest", type=Path)
    locate_parser = subparsers.add_parser("locate", help="locate files by corpus topic")
    locate_parser.add_argument("snapshot_dir", type=Path)
    locate_parser.add_argument("--topic", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the corpus command-line interface."""

    args = _build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            manifest = verify_snapshot(args.snapshot_dir)
            print(f"verified {manifest['snapshot_id']} ({len(manifest['entries'])} files)")
        elif args.command == "rebuild":
            rebuild_snapshot(args.snapshot_dir, args.destination)
            print(f"rebuilt {args.snapshot_dir.name} into {args.destination}")
        elif args.command == "diff":
            print(json.dumps(diff_manifests(args.old_manifest, args.new_manifest), indent=2))
        elif args.command == "locate":
            print(
                json.dumps(
                    locate_topic(args.snapshot_dir, args.topic), ensure_ascii=False, indent=2
                )
            )
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
