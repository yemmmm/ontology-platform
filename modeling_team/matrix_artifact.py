"""Deterministic R2.3-002 assertion-matrix generation and verification.

The matrix is implementation-owned input to the independent P2a check.  This
module only reads the retained rev7 handoff and the approved, immutable source
manifest; it never creates a ledger event, starts a semantic run, or writes the
tester-owned P2a PASS artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SOURCE_ROOT = Path("docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input")
SOURCE_MANIFEST_RELATIVE = SOURCE_ROOT / "manifest.json"
HANDOFF_RELATIVE = Path("modeling_team/references/r2-3-002-retained-rev7-handoff.json")
MATRIX_RELATIVE = Path("modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json")
SOURCE_RUN_ID = "r23002-real-20260801s"
MATRIX_SCHEMA = "r2-3-002-proof-v2-assertion-matrix/v1"
HANDOFF_SCHEMA = "r2-3-002-retained-rev7-handoff/v1"

_HANDOFF_SHA256 = "98b2968fd04313bd8bc74efbbfe89a8f3f4ec42dce4d7c7abcfb2e9a49a3eafb"
_SOURCE_MANIFEST_SHA256 = "8a77f014add302c04206e2626957e42a195b63b043d8a0a6a09e54cdb05c03e9"
_SOURCE_HASHES = {
    "official/tools.mdx": "92a97c639fb8d4782e95207cb84ede79b1739ff3abdb9bc1fe384f0741c2c96b",
    "sources/exception-handling.md": "cc0c69ef7428bd63ed7432ee0a9cae6d9acbca8cb267528a23fbaf0602638d9f",
    "sources/interface-notes.md": "9cc479c365404cf8230aeb87e609ce164fb2680a87a5c16f45476d8260870e37",
    "sources/release-register.md": "f5386a00a2a048831ce524ef605aed14c1124a6ac74fb8dc99c5b0a0f777caae",
    "sources/workflow-landscape.md": "9dde79c61d9849776c9140aa5c3be02c17aea7800efa56135fb8dfaa0be7011e",
}

_ROW_FIELDS = {
    "assertion_id",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
    "approved_citations",
    "binding_category",
    "literal_category",
    "target_kind",
    "p2a_branch_id",
    "match_coverage",
    "context_coverage",
}
_CITATION_FIELDS = {
    "document_name",
    "excerpt",
    "source_artifact_sha256",
    "source_locator",
    "excerpt_sha256",
    "owner_answer_id",
}
_HANDOFF_ITEM_FIELDS = {
    "graph_role",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
}


class MatrixArtifactError(ValueError):
    """The frozen matrix input or generated artifact is invalid."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise MatrixArtifactError(f"{name} is not a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise MatrixArtifactError(f"{name} is not a SHA-256 digest") from exc
    return value


def _exact(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise MatrixArtifactError(f"{name} fields drift")
    return value


def _load_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MatrixArtifactError(f"{name} is unreadable") from exc
    if not isinstance(value, dict):
        raise MatrixArtifactError(f"{name} must contain an object")
    return value


def _source_path(root: Path, relative: str) -> Path:
    path = root / SOURCE_ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise MatrixArtifactError(f"approved source is unavailable: {relative}")
    return path


def _verify_inputs(root: Path) -> dict[str, Path]:
    handoff = root / HANDOFF_RELATIVE
    manifest = root / SOURCE_MANIFEST_RELATIVE
    if handoff.is_symlink() or not handoff.is_file() or _sha256(handoff) != _HANDOFF_SHA256:
        raise MatrixArtifactError("retained rev7 handoff input hash drifts")
    if manifest.is_symlink() or not manifest.is_file() or _sha256(manifest) != _SOURCE_MANIFEST_SHA256:
        raise MatrixArtifactError("approved source manifest input hash drifts")
    manifest_value = _load_json(manifest, "approved source manifest")
    files = manifest_value.get("files")
    if not isinstance(files, list):
        raise MatrixArtifactError("approved source manifest files are invalid")
    by_path = {item.get("path"): item for item in files if isinstance(item, dict)}
    result: dict[str, Path] = {}
    for relative, expected_hash in _SOURCE_HASHES.items():
        source = _source_path(root, relative)
        if _sha256(source) != expected_hash:
            raise MatrixArtifactError(f"approved source hash drifts: {relative}")
        manifest_entry = by_path.get(relative)
        if not isinstance(manifest_entry, dict) or manifest_entry.get("sha256") != expected_hash:
            raise MatrixArtifactError(f"approved source manifest entry drifts: {relative}")
        result[relative] = source
    return result


def _load_handoff(root: Path) -> dict[str, Any]:
    handoff = _load_json(root / HANDOFF_RELATIVE, "retained rev7 handoff")
    if set(handoff) != {
        "candidate_revision",
        "delivery_id",
        "reply_chain",
        "required_semantic_items",
        "schema_version",
        "source_delivery_ids",
        "source_run_id",
    }:
        raise MatrixArtifactError("retained rev7 handoff fields drift")
    if handoff["schema_version"] != HANDOFF_SCHEMA or handoff["source_run_id"] != SOURCE_RUN_ID:
        raise MatrixArtifactError("retained rev7 handoff identity drifts")
    if handoff["candidate_revision"] != "7" or handoff["delivery_id"] != "delivery-22":
        raise MatrixArtifactError("retained rev7 handoff revision drifts")
    if handoff["source_delivery_ids"] != ["delivery-10", "delivery-14", "delivery-22"]:
        raise MatrixArtifactError("retained rev7 source delivery list drifts")
    chain = handoff.get("reply_chain")
    if not isinstance(chain, list) or not chain or any(not isinstance(value, str) or not value for value in chain):
        raise MatrixArtifactError("retained rev7 reply chain is invalid")
    items = handoff.get("required_semantic_items")
    if not isinstance(items, list) or len(items) != 48:
        raise MatrixArtifactError("retained rev7 handoff must contain exactly 48 semantic items")
    seen: set[bytes] = set()
    for item in items:
        _exact(item, _HANDOFF_ITEM_FIELDS, "retained semantic item")
        if item["graph_role"] != "asserted_data":
            raise MatrixArtifactError("retained semantic item graph role drifts")
        for field in ("subject", "predicate", "object", "object_kind"):
            if not isinstance(item[field], str) or not item[field]:
                raise MatrixArtifactError(f"retained semantic item {field} is invalid")
        for field in ("object_datatype", "object_language"):
            if item[field] is not None and (not isinstance(item[field], str) or not item[field]):
                raise MatrixArtifactError(f"retained semantic item {field} is invalid")
        encoded = canonical_bytes(item)
        if encoded in seen:
            raise MatrixArtifactError("retained semantic item is duplicated")
        seen.add(encoded)
    return handoff


def _excerpt(source: Path, first_line: int, last_line: int) -> str:
    lines = source.read_text(encoding="utf-8").splitlines()
    if first_line < 1 or last_line < first_line or last_line > len(lines):
        raise MatrixArtifactError("approved source excerpt range is invalid")
    return "\n".join(lines[first_line - 1 : last_line])


def _source_key(item: Mapping[str, Any]) -> tuple[str, int, int]:
    predicate = item["predicate"]
    subject = item["subject"]
    obj = item["object"]
    if predicate in {
        "canCompleteWithoutNumericScore",
        "scoreAbsentReturn",
        "ruleText",
        "publicationCondition",
        "kind",
        "unansweredQuestion",
        "rationale",
        "hasEvidence",
    } or subject.startswith(("rule:", "unknown:")):
        return "sources/exception-handling.md", 3, 6
    if predicate in {
        "hasVersion",
        "hasDraft",
        "publicationStatus",
        "isLatestPublished",
        "hasOutput",
        "fieldName",
        "fieldDatatype",
    } or subject.startswith(("workflow:C:v", "workflow:C:draft", "output:C:")):
        return "sources/release-register.md", 3, 10
    if predicate == "documentedSuccessorOf":
        return "sources/interface-notes.md", 3, 6
    if predicate in {"bindingPolicy", "resolvedPublishedVersion", "consumedOutput"} or subject.startswith("invocation:"):
        return "sources/release-register.md", 3, 10
    if predicate in {"invokesAsTool", "publishesResultOf"} or (predicate == "rdf:type" and obj == "Workflow"):
        return "sources/workflow-landscape.md", 3, 7
    if predicate == "rdf:type" and obj == "Evidence":
        return "sources/exception-handling.md", 3, 6
    return "official/tools.mdx", 5, 6


def _citation(root: Path, source_paths: Mapping[str, Path], item: Mapping[str, Any]) -> dict[str, Any]:
    relative, first_line, last_line = _source_key(item)
    source = source_paths[relative]
    excerpt = _excerpt(source, first_line, last_line)
    document_name = f"{SOURCE_ROOT.as_posix()}/{relative}"
    citation = {
        "document_name": document_name,
        "excerpt": excerpt,
        "source_artifact_sha256": _SOURCE_HASHES[relative],
        "source_locator": f"{document_name}#L{first_line}-L{last_line}",
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "owner_answer_id": None,
    }
    _exact(citation, _CITATION_FIELDS, "generated citation")
    return citation


def _binding_category(item: Mapping[str, Any]) -> str:
    if item["object_kind"] == "literal":
        return "literal_delta"
    if item["predicate"] == "rdf:type":
        return "vocabulary"
    if item["predicate"] in {"hasOutput", "consumedOutput"}:
        return "resource_output"
    return "relation_delta"


def _candidate(root: Path, handoff: Mapping[str, Any], source_paths: Mapping[str, Path]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(handoff["required_semantic_items"], 1):
        item = dict(raw)
        item["assertion_id"] = f"r23002-a{index:03d}"
        item["evidence_citations"] = [_citation(root, source_paths, item)]
        items.append(item)
    items.sort(key=canonical_bytes)
    semantic_digest = canonical_digest(
        {"schema_version": "candidate-required-assertions/v2", "statements": items}
    )
    binding = {
        "schema_version": "candidate-required-assertions/v2",
        "candidate_revision": handoff["candidate_revision"],
        "delivery_id": handoff["delivery_id"],
        "reply_chain": handoff["reply_chain"],
        "semantic_digest": semantic_digest,
    }
    return {**binding, "candidate_digest": canonical_digest(binding), "items": items}


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    binding = _binding_category(item)
    if item["object_kind"] != "literal":
        literal_category = "none"
    elif item.get("object_datatype") == "xsd:boolean":
        literal_category = "boolean"
    elif item.get("object_language"):
        literal_category = "language"
    else:
        literal_category = "xsd:string"
    target_kind = "resource" if binding in {"resource_output", "vocabulary"} else "statement"
    return {
        "assertion_id": item["assertion_id"],
        "subject": item["subject"],
        "predicate": item["predicate"],
        "object": item["object"],
        "object_kind": item["object_kind"],
        "object_datatype": item["object_datatype"],
        "object_language": item["object_language"],
        "approved_citations": item["evidence_citations"],
        "binding_category": binding,
        "literal_category": literal_category,
        "target_kind": target_kind,
        "p2a_branch_id": f"p2a-{binding}-{literal_category}-{target_kind}",
        "match_coverage": True,
        "context_coverage": True,
    }


def build_matrix(root: Path) -> dict[str, Any]:
    """Build the exact frozen matrix from the retained handoff and source files."""
    root = root.resolve()
    source_paths = _verify_inputs(root)
    handoff = _load_handoff(root)
    candidate = _candidate(root, handoff, source_paths)
    rows = sorted((_row(item) for item in candidate["items"]), key=lambda value: value["assertion_id"])
    payload = {
        "schema_version": MATRIX_SCHEMA,
        "source_run_id": SOURCE_RUN_ID,
        "source_candidate_digest": candidate["candidate_digest"],
        "rows": rows,
    }
    return {**payload, "matrix_digest": canonical_digest(payload)}


def verify_matrix(
    matrix: Mapping[str, Any], *, root: Path | None = None, source_run_id: str | None = None
) -> dict[str, Any]:
    """Validate a matrix and, when ``root`` is supplied, its deterministic inputs."""
    value = _exact(dict(matrix), {"schema_version", "source_run_id", "source_candidate_digest", "rows", "matrix_digest"}, "proof matrix")
    expected_source_run = source_run_id or SOURCE_RUN_ID
    if value["schema_version"] != MATRIX_SCHEMA or value["source_run_id"] != expected_source_run:
        raise MatrixArtifactError("proof matrix schema/source drifted")
    _digest(value["source_candidate_digest"], "source_candidate_digest")
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) != 48:
        raise MatrixArtifactError("proof matrix must contain exactly 48 rows")
    previous: str | None = None
    seen: set[str] = set()
    categories: set[str] = set()
    targets: set[str] = set()
    for raw in rows:
        row = _exact(raw, _ROW_FIELDS, "proof matrix row")
        assertion_id = row["assertion_id"]
        if not isinstance(assertion_id, str) or not assertion_id or assertion_id in seen:
            raise MatrixArtifactError("proof matrix assertion IDs are invalid")
        if previous is not None and assertion_id <= previous:
            raise MatrixArtifactError("proof matrix rows are not sorted")
        previous = assertion_id
        seen.add(assertion_id)
        if row["object_kind"] not in {"resource", "literal"}:
            raise MatrixArtifactError("proof matrix object_kind is invalid")
        if row["binding_category"] not in {"resource_output", "relation_delta", "literal_delta", "vocabulary"}:
            raise MatrixArtifactError("proof matrix binding category is invalid")
        if row["literal_category"] not in {"none", "plain", "xsd:string", "language", "boolean"}:
            raise MatrixArtifactError("proof matrix literal category is invalid")
        if row["target_kind"] not in {"resource", "statement"} or not isinstance(row["p2a_branch_id"], str) or not row["p2a_branch_id"]:
            raise MatrixArtifactError("proof matrix target branch is invalid")
        if not isinstance(row["match_coverage"], bool) or not isinstance(row["context_coverage"], bool):
            raise MatrixArtifactError("proof matrix coverage flags are invalid")
        citations = row["approved_citations"]
        if not isinstance(citations, list) or not citations:
            raise MatrixArtifactError("proof matrix citation set is empty")
        encoded_citations = [canonical_bytes(citation) for citation in citations]
        if encoded_citations != sorted(encoded_citations) or len(encoded_citations) != len(set(encoded_citations)):
            raise MatrixArtifactError("proof matrix citations are not canonical")
        for citation in citations:
            citation_value = _exact(citation, _CITATION_FIELDS, "proof matrix citation")
            for field in ("document_name", "excerpt", "source_locator"):
                if not isinstance(citation_value[field], str) or not citation_value[field]:
                    raise MatrixArtifactError(f"proof matrix citation {field} is invalid")
            _digest(citation_value["source_artifact_sha256"], "source_artifact_sha256")
            _digest(citation_value["excerpt_sha256"], "excerpt_sha256")
            if hashlib.sha256(citation_value["excerpt"].encode("utf-8")).hexdigest() != citation_value["excerpt_sha256"]:
                raise MatrixArtifactError("proof matrix citation excerpt hash drifts")
            owner = citation_value["owner_answer_id"]
            if owner is not None and (not isinstance(owner, str) or not owner):
                raise MatrixArtifactError("proof matrix owner answer ID is invalid")
        categories.add(row["binding_category"])
        targets.add(row["target_kind"])
    if categories != {"resource_output", "relation_delta", "literal_delta", "vocabulary"}:
        raise MatrixArtifactError("proof matrix does not cover all binding categories")
    if targets != {"resource", "statement"}:
        raise MatrixArtifactError("proof matrix does not cover both target kinds")
    payload = {key: value[key] for key in ("schema_version", "source_run_id", "source_candidate_digest", "rows")}
    if value["matrix_digest"] != canonical_digest(payload):
        raise MatrixArtifactError("proof matrix digest drifts")
    if root is not None and source_run_id is None:
        expected = build_matrix(root)
        if dict(value) != expected:
            raise MatrixArtifactError("proof matrix does not match deterministic retained inputs")
    return dict(value)


def load_matrix(root: Path) -> dict[str, Any]:
    path = root.resolve() / MATRIX_RELATIVE
    return verify_matrix(_load_json(path, "proof matrix"), root=root)


__all__ = [
    "HANDOFF_RELATIVE",
    "MATRIX_RELATIVE",
    "MATRIX_SCHEMA",
    "SOURCE_RUN_ID",
    "MatrixArtifactError",
    "build_matrix",
    "canonical_bytes",
    "canonical_digest",
    "load_matrix",
    "verify_matrix",
]
