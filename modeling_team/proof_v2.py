"""Strict, platform-neutral mechanics for the R2.3 native retrieval proof.

This module deliberately contains no platform client and no business-ontology
interpretation.  It consumes the immutable candidate and formal receipt/read
projections produced by Protocol and verifies hashes, selectors, evidence
cardinality, lineage, and pagination.  The retained v1 verifier lives in
``protocol_mechanics`` and is kept separate so historical evidence remains
readable without weakening the v2 contract.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


class ProofV2Error(ValueError):
    """A v2 proof is incomplete, ambiguous, or has drifted."""


V2_PROOF_FIELDS = {
    "mode",
    "initial_modeling_context",
    "final_modeling_context",
    "workspace_context",
    "batch_inventory",
    "batch_details",
    "entities_read",
    "statements_read",
    "candidate_required_assertions",
    "term_bindings",
    "materialized_quads",
    "materialized_digest",
    "evidence_bindings",
    "statement_lineage",
    "pagination",
}
CANDIDATE_FIELDS = {
    "schema_version",
    "candidate_revision",
    "delivery_id",
    "reply_chain",
    "semantic_digest",
    "candidate_digest",
    "items",
}
CANDIDATE_ITEM_FIELDS = {
    "assertion_id",
    "graph_role",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
    "evidence_citations",
}
CITATION_FIELDS = {
    "document_name",
    "excerpt",
    "source_artifact_sha256",
    "source_locator",
    "excerpt_sha256",
    "owner_answer_id",
}
TERM_BINDING_FIELDS = {
    "assertion_id",
    "term_position",
    "candidate_term",
    "binding_kind",
    "client_item_id",
    "batch_id",
    "applied_attempt_id",
    "quad_digest",
    "delta_index",
    "resource_output_iri",
}
QUAD_FIELDS = {
    "graph_role",
    "source_graph_iri",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
}
EVIDENCE_BINDING_FIELDS = {
    "assertion_id",
    "citation_digest",
    "evidence_reference_id",
    "client_item_id",
    "batch_id",
    "fact_id",
    "inline_evidence_identity",
    "citation_group_digest",
}
LINEAGE_FIELDS = {"assertion_id", "fact_id", "quad", "target", "response"}
TARGET_FIELDS = {"target_kind", "target_id"}
PAGINATION_FIELDS = {"schema_version", "streams"}
STREAM_FIELDS = {"stream_kind", "pages"}
PAGE_FIELDS = {
    "stream_kind",
    "request_fingerprint_sha256",
    "page_index",
    "request_cursor",
    "next_cursor",
    "response_digest",
    "root_match_ids_digest",
    "response",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _fail(message: str) -> None:
    raise ProofV2Error(message)


def _exact(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"{name} has missing or extra fields")
    return value


def _string(value: Any, name: str, *, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not value:
        _fail(f"{name} is not bound")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        _fail(f"{name} is invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProofV2Error(f"{name} is invalid") from exc
    return value


def _sorted_unique(values: Sequence[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    encoded = [canonical_bytes(value) for value in values]
    if len(encoded) != len(set(encoded)):
        _fail(f"{name} contains duplicate canonical values")
    ordered = sorted(values, key=canonical_bytes)
    if encoded != [canonical_bytes(value) for value in ordered]:
        _fail(f"{name} is not canonically sorted")
    return list(ordered)


def citation_digest(citation: Mapping[str, Any]) -> str:
    """Hash the six-field candidate citation, never the raw source text alone."""
    value = _exact(dict(citation), CITATION_FIELDS, "citation")
    _validate_citation(value)
    return canonical_digest(value)


def inline_evidence_identity(document_name: str, normalized_excerpt_sha256: str) -> str:
    _string(document_name, "document_name")
    _digest(normalized_excerpt_sha256, "normalized_excerpt_sha256")
    return canonical_digest(
        {
            "document_name": document_name,
            "normalized_excerpt_sha256": normalized_excerpt_sha256,
        }
    )


def citation_group_digest(citation_digests: Iterable[str]) -> str:
    values = list(citation_digests)
    if not values:
        _fail("citation group is empty")
    for index, value in enumerate(values):
        _digest(value, f"citation_digests[{index}]")
    unique = sorted(set(values))
    return canonical_digest(unique)


def _validate_citation(value: dict[str, Any]) -> None:
    _string(value.get("document_name"), "citation document_name")
    _string(value.get("excerpt"), "citation excerpt")
    _digest(value.get("source_artifact_sha256"), "citation source_artifact_sha256")
    _string(value.get("source_locator"), "citation source_locator")
    _digest(value.get("excerpt_sha256"), "citation excerpt_sha256")
    owner = value.get("owner_answer_id")
    if owner is not None:
        _string(owner, "citation owner_answer_id")
    # The candidate owns the exact excerpt and its digest.  This catches
    # accidental normalization/text replacement before any Batch call.
    if hashlib.sha256(value["excerpt"].encode("utf-8")).hexdigest() != value["excerpt_sha256"]:
        # Round63 calls this ``excerpt_sha256`` but existing platform receipts
        # use the normalized excerpt hash.  Accept either exact or normalized
        # whitespace form; never accept an unrelated/guessed digest.
        normalized = " ".join(value["excerpt"].split())
        if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != value["excerpt_sha256"]:
            _fail("citation excerpt_sha256 drifts")


def _validate_candidate(candidate: Any) -> dict[str, Any]:
    candidate = _exact(candidate, CANDIDATE_FIELDS, "candidate_required_assertions")
    if candidate.get("schema_version") != "candidate-required-assertions/v2":
        _fail("candidate schema_version is invalid")
    for field in ("candidate_revision", "delivery_id"):
        _string(candidate.get(field), f"candidate {field}")
    chain = candidate.get("reply_chain")
    if (
        not isinstance(chain, list)
        or not chain
        or any(not isinstance(value, str) or not value for value in chain)
        or len(chain) != len(set(chain))
    ):
        _fail("candidate reply_chain is invalid")
    _digest(candidate.get("semantic_digest"), "candidate semantic_digest")
    _digest(candidate.get("candidate_digest"), "candidate_digest")
    items = candidate.get("items")
    if not isinstance(items, list) or not items:
        _fail("candidate items are empty")
    normalized: list[dict[str, Any]] = []
    assertion_ids: set[str] = set()
    for raw in items:
        item = _exact(raw, CANDIDATE_ITEM_FIELDS, "candidate assertion item")
        assertion_id = _string(item.get("assertion_id"), "candidate assertion_id")
        assert assertion_id is not None
        if assertion_id in assertion_ids:
            _fail("candidate assertion_id is duplicated")
        assertion_ids.add(assertion_id)
        if item.get("graph_role") != "asserted_data":
            _fail("candidate assertion graph role is invalid")
        for field in ("subject", "predicate", "object", "object_kind"):
            _string(item.get(field), f"candidate assertion {field}")
        if item.get("object_datatype") is not None:
            _string(item.get("object_datatype"), "candidate object_datatype")
        if item.get("object_language") is not None:
            _string(item.get("object_language"), "candidate object_language")
        citations = item.get("evidence_citations")
        if not isinstance(citations, list) or not citations:
            _fail("candidate evidence_citations are empty")
        normalized_citations: list[dict[str, Any]] = []
        for raw_citation in citations:
            citation = _exact(raw_citation, CITATION_FIELDS, "candidate citation")
            _validate_citation(citation)
            normalized_citations.append(citation)
        item["evidence_citations"] = _sorted_unique(
            normalized_citations, "candidate evidence_citations"
        )
        normalized.append(item)
    normalized = _sorted_unique(normalized, "candidate items")
    semantic = canonical_digest(
        {"schema_version": "candidate-required-assertions/v2", "statements": normalized}
    )
    if candidate.get("semantic_digest") != semantic:
        _fail("candidate semantic_digest drifts")
    binding = {
        "schema_version": candidate["schema_version"],
        "candidate_revision": candidate["candidate_revision"],
        "delivery_id": candidate["delivery_id"],
        "reply_chain": candidate["reply_chain"],
        "semantic_digest": semantic,
    }
    expected_candidate_digest = canonical_digest(binding)
    if candidate.get("candidate_digest") != expected_candidate_digest:
        _fail("candidate_digest drifts")
    candidate["items"] = normalized
    return candidate


def build_candidate_item_evidence_map(
    candidate: Mapping[str, Any],
    client_item_ids: Mapping[str, str] | Sequence[Mapping[str, str]],
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build the immutable Round63 assertion×citation map before submit.

    ``client_item_ids`` is a Protocol-owned assertion-to-item binding.  It is
    deliberately supplied separately because the candidate itself must remain
    platform-neutral and may not contain Batch IDs.
    """
    candidate_value = _validate_candidate(json.loads(json.dumps(candidate)))
    if run_id is None:
        _string(candidate_value.get("run_id"), "run_id")
        run_id = candidate_value["run_id"]
    _string(run_id, "run_id")
    mapping: dict[str, str] = {}
    if isinstance(client_item_ids, Mapping):
        for assertion_id, client_item_id in client_item_ids.items():
            mapping[str(assertion_id)] = str(client_item_id)
    elif isinstance(client_item_ids, Sequence) and not isinstance(client_item_ids, (str, bytes)):
        for value in client_item_ids:
            if not isinstance(value, Mapping):
                _fail("client item binding is invalid")
            assertion_id = _string(value.get("assertion_id"), "client item assertion_id")
            client_item_id = _string(value.get("client_item_id"), "client_item_id")
            assert assertion_id is not None and client_item_id is not None
            if assertion_id in mapping:
                _fail("client item binding is duplicated")
            mapping[assertion_id] = client_item_id
    else:
        _fail("client item bindings are invalid")
    expected_ids = {item["assertion_id"] for item in candidate_value["items"]}
    if set(mapping) != expected_ids or len(set(mapping.values())) != len(mapping):
        _fail("client item bindings do not exactly cover candidate assertions")
    rows: list[dict[str, Any]] = []
    group_digests: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for item in candidate_value["items"]:
        assertion_id = item["assertion_id"]
        client_item_id = mapping[assertion_id]
        for citation in item["evidence_citations"]:
            digest = citation_digest(citation)
            identity = inline_evidence_identity(
                citation["document_name"], citation["excerpt_sha256"]
            )
            group_digests[(assertion_id, client_item_id, identity)].append(digest)
    group_hashes = {
        key: citation_group_digest(values) for key, values in group_digests.items()
    }
    for item in candidate_value["items"]:
        assertion_id = item["assertion_id"]
        client_item_id = mapping[assertion_id]
        for citation in item["evidence_citations"]:
            digest = citation_digest(citation)
            identity = inline_evidence_identity(
                citation["document_name"], citation["excerpt_sha256"]
            )
            rows.append(
                {
                    "assertion_id": assertion_id,
                    "citation_digest": digest,
                    "client_item_id": client_item_id,
                    "document_name": citation["document_name"],
                    "excerpt_sha256": citation["excerpt_sha256"],
                    "inline_evidence_identity": identity,
                    "citation_group_digest": group_hashes[(assertion_id, client_item_id, identity)],
                }
            )
    rows = _sorted_unique(rows, "candidate evidence map rows")
    # A duplicate digest or duplicate inline identity within a group is not
    # representable as a one-row-per-citation map.  Distinct citation digests
    # sharing one inline identity remain valid and are intentionally retained.
    seen_digest: set[tuple[str, str]] = set()
    seen_identity: set[tuple[str, str, str]] = set()
    for row in rows:
        digest_key = (row["assertion_id"], row["citation_digest"])
        identity_key = (
            row["assertion_id"],
            row["client_item_id"],
            row["inline_evidence_identity"],
        )
        if digest_key in seen_digest:
            _fail("candidate evidence map contains duplicate citation digest")
        if identity_key in seen_identity and digest_key in seen_digest:
            _fail("candidate evidence map contains duplicate citation identity")
        seen_digest.add(digest_key)
        seen_identity.add(identity_key)
    payload = {
        "schema_version": "r2-3-002-candidate-item-evidence-map/v1",
        "run_id": run_id,
        "candidate_digest": candidate_value["candidate_digest"],
        "rows": rows,
    }
    return {**payload, "map_digest": canonical_digest(payload)}


def validate_candidate_item_evidence_map(
    candidate: Mapping[str, Any],
    evidence_map: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    """Validate a retained map byte-for-byte against the candidate citations."""
    candidate_value = _validate_candidate(json.loads(json.dumps(candidate)))
    evidence_map_value = _exact(
        dict(evidence_map),
        {
            "schema_version",
            "run_id",
            "candidate_digest",
            "rows",
            "map_digest",
        },
        "candidate item evidence map",
    )
    if evidence_map_value["schema_version"] != "r2-3-002-candidate-item-evidence-map/v1":
        _fail("candidate evidence map schema_version is invalid")
    _string(evidence_map_value.get("run_id"), "candidate evidence map run_id")
    if expected_run_id is not None and evidence_map_value["run_id"] != expected_run_id:
        _fail("candidate evidence map run_id drifts")
    if evidence_map_value.get("candidate_digest") != candidate_value["candidate_digest"]:
        _fail("candidate evidence map candidate_digest drifts")
    rows = evidence_map_value.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail("candidate evidence map rows are empty")
    normalized_rows: list[dict[str, Any]] = []
    for raw in rows:
        row = _exact(
            raw,
            {
                "assertion_id",
                "citation_digest",
                "client_item_id",
                "document_name",
                "excerpt_sha256",
                "inline_evidence_identity",
                "citation_group_digest",
            },
            "candidate evidence map row",
        )
        _string(row.get("assertion_id"), "map assertion_id")
        _digest(row.get("citation_digest"), "map citation_digest")
        _string(row.get("client_item_id"), "map client_item_id")
        _string(row.get("document_name"), "map document_name")
        _digest(row.get("excerpt_sha256"), "map excerpt_sha256")
        _digest(row.get("inline_evidence_identity"), "map inline_evidence_identity")
        _digest(row.get("citation_group_digest"), "map citation_group_digest")
        normalized_rows.append(row)
    _sorted_unique(normalized_rows, "candidate evidence map rows")
    expected = build_candidate_item_evidence_map(
        candidate_value,
        {row["assertion_id"]: row["client_item_id"] for row in normalized_rows},
        run_id=evidence_map_value["run_id"],
    )
    if normalized_rows != expected["rows"]:
        _fail("candidate evidence map rows do not match candidate citations")
    payload = {key: evidence_map_value[key] for key in ("schema_version", "run_id", "candidate_digest", "rows")}
    if evidence_map_value.get("map_digest") != canonical_digest(payload):
        _fail("candidate evidence map_digest drifts")
    return evidence_map_value


def compare_dry_run_group_projection(
    evidence_map: Mapping[str, Any],
    plan_rows: Sequence[Mapping[str, Any]],
    *,
    expected_dedupe_identity: Mapping[tuple[str, str], str] | None = None,
) -> list[dict[str, str]]:
    """Compare safe dry-run Evidence rows at group, not citation, cardinality."""
    map_value = _exact(
        dict(evidence_map),
        {"schema_version", "run_id", "candidate_digest", "rows", "map_digest"},
        "candidate item evidence map",
    )
    rows = map_value.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail("candidate evidence map rows are empty")
    groups = {
        (row["client_item_id"], row["inline_evidence_identity"]): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(groups) != len(rows):
        # Multiple citations in the same group are expected and do not imply
        # a duplicate dry-run plan row, so this is deliberately not an error.
        pass
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in plan_rows:
        row = _exact(
            raw,
            {"client_item_id", "inline_evidence_identity", "dedupe_identity"},
            "dry-run Evidence projection row",
        )
        client_item_id = _string(row.get("client_item_id"), "plan client_item_id")
        identity = _digest(row.get("inline_evidence_identity"), "plan inline_evidence_identity")
        dedupe = _string(row.get("dedupe_identity"), "plan dedupe_identity")
        assert client_item_id is not None and identity is not None and dedupe is not None
        key = (client_item_id, identity)
        if key in seen:
            _fail("dry-run Evidence projection contains duplicate group")
        seen.add(key)
        if key not in groups:
            _fail("dry-run Evidence projection contains extra group")
        if expected_dedupe_identity is not None:
            expected = expected_dedupe_identity.get(key)
            if expected is None or expected != dedupe:
                _fail("dry-run Evidence dedupe identity drifts")
        normalized.append(
            {
                "client_item_id": client_item_id,
                "inline_evidence_identity": identity,
                "dedupe_identity": dedupe,
            }
        )
    if seen != set(groups):
        _fail("dry-run Evidence projection is missing a group")
    return sorted(normalized, key=canonical_bytes)


def verify_postapply_evidence_bindings(
    candidate: Mapping[str, Any],
    evidence_map: Mapping[str, Any],
    bindings: Sequence[Mapping[str, Any]],
    *,
    fact_ids: Mapping[str, str],
    batch_ids: Mapping[str, str],
    evidence_reference_ids: Mapping[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Require one post-apply binding row per assertion×citation."""
    map_value = validate_candidate_item_evidence_map(candidate, evidence_map)
    expected_rows = map_value["rows"]
    if not isinstance(bindings, Sequence) or isinstance(bindings, (str, bytes)):
        _fail("evidence_bindings are invalid")
    normalized: list[dict[str, Any]] = []
    for raw in bindings:
        row = _exact(raw, EVIDENCE_BINDING_FIELDS, "evidence binding")
        for field in ("assertion_id", "citation_digest", "evidence_reference_id", "client_item_id", "batch_id", "fact_id", "inline_evidence_identity", "citation_group_digest"):
            _string(row.get(field), f"evidence binding {field}")
        normalized.append(row)
    _sorted_unique(normalized, "evidence_bindings")
    expected: list[dict[str, Any]] = []
    for map_row in expected_rows:
        assertion_id = map_row["assertion_id"]
        fact_id = fact_ids.get(assertion_id)
        batch_id = batch_ids.get(assertion_id)
        if fact_id is None or batch_id is None:
            _fail("evidence binding receipt identity is missing")
        key = (assertion_id, map_row["citation_digest"])
        reference_id = evidence_reference_ids.get(key) if evidence_reference_ids else None
        if reference_id is None:
            # A post-apply reference ID is platform-created; permit any stable
            # non-empty ID when no independent expected map was supplied.
            reference_id = next(
                (
                    row["evidence_reference_id"]
                    for row in normalized
                    if row["assertion_id"] == assertion_id
                    and row["citation_digest"] == map_row["citation_digest"]
                ),
                None,
            )
        if reference_id is None:
            _fail("evidence reference is missing")
        expected.append(
            {
                "assertion_id": assertion_id,
                "citation_digest": map_row["citation_digest"],
                "evidence_reference_id": reference_id,
                "client_item_id": map_row["client_item_id"],
                "batch_id": batch_id,
                "fact_id": fact_id,
                "inline_evidence_identity": map_row["inline_evidence_identity"],
                "citation_group_digest": map_row["citation_group_digest"],
            }
        )
    if len(normalized) != len(expected) or sorted(normalized, key=canonical_bytes) != sorted(expected, key=canonical_bytes):
        _fail("evidence_bindings do not exactly cover candidate citations")
    return normalized


def _envelope(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"ok", "data"} or value.get("ok") is not True:
        _fail(f"{name} is not a full successful MCP envelope")
    if not isinstance(value.get("data"), dict):
        _fail(f"{name} data is invalid")
    return value["data"]


def _graph_roles(workspace: dict[str, Any], ontology_id: str) -> dict[str, str]:
    members = workspace.get("members")
    if not isinstance(members, list):
        _fail("workspace graph members are invalid")
    roles: dict[str, str] = {}
    for member in members:
        if not isinstance(member, dict):
            _fail("workspace graph member is invalid")
        role = member.get("role")
        if role not in {"asserted_ontology", "asserted_data", "shapes"}:
            continue
        if role in roles or member.get("owner_type") != "ontology" or member.get("owner_id") != ontology_id:
            _fail("workspace graph role is invalid")
        _string(member.get("graph_iri"), "workspace graph_iri")
        roles[role] = member["graph_iri"]
    if set(roles) != {"asserted_ontology", "asserted_data", "shapes"}:
        _fail("workspace graph roles are incomplete")
    return roles


def _counts(context: dict[str, Any]) -> dict[str, int]:
    counts = context.get("resource_counts")
    names = ("classes", "properties", "relation_types", "shapes", "entities", "relations", "facts")
    if not isinstance(counts, dict) or any(isinstance(counts.get(name), bool) or not isinstance(counts.get(name), int) or counts[name] < 0 for name in names):
        _fail("modeling context has invalid authoritative counts")
    return {name: counts[name] for name in names}


def _quad_tuple(value: Any) -> tuple[str, str, str, str]:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, str) and item for item in value):
        return value[0], value[1], value[2], value[3]
    if isinstance(value, dict):
        graph = value.get("graph", value.get("source_graph_iri"))
        if all(isinstance(value.get(field), str) and value[field] for field in ("subject", "predicate", "object")) and isinstance(graph, str) and graph:
            return value["subject"], value["predicate"], value["object"], graph
    _fail("normalized delta quad is invalid")
    raise AssertionError


def _fact_id_from_quad(quad: tuple[str, str, str, str], object_kind: str | None = None, datatype: str | None = None, language: str | None = None) -> str:
    subject, predicate, obj, graph = quad
    if object_kind == "iri" or (obj.startswith("<") and obj.endswith(">")):
        obj_term = obj if obj.startswith("<") else f"<{obj}>"
    elif object_kind == "literal" or not (obj.startswith("<") and obj.endswith(">")):
        obj_term = obj
        if not (obj.startswith('"') and (obj.endswith('"') or '"@' in obj or '"^^' in obj)):
            escaped = obj.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            obj_term = f'"{escaped}"'
            if language:
                obj_term += f"@{language}"
            elif datatype:
                obj_term += f"^^<{datatype}>"
    canonical = f"<{subject.strip('<>')}> <{predicate.strip('<>')}> {obj_term} <{graph.strip('<>')}>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _collect_receipts(details: Sequence[Any], graphs: Mapping[str, str]) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], list[tuple[int, tuple[str, str, str, str], dict[str, Any]]]], list[tuple[str, str, dict[str, Any]]]]:
    outputs: dict[tuple[str, str], str] = {}
    deltas: dict[tuple[str, str, str], list[tuple[int, tuple[str, str, str, str], dict[str, Any]]]] = defaultdict(list)
    applied: list[tuple[str, str, dict[str, Any]]] = []
    for detail in details:
        batch_id = _string(detail.get("batch_id"), "batch detail batch_id")
        assert batch_id is not None
        attempts = detail.get("attempts")
        items = detail.get("items")
        if not isinstance(attempts, list) or not isinstance(items, list):
            _fail("batch detail attempts/items are invalid")
        by_item = {item.get("item_id"): item for item in items if isinstance(item, dict) and isinstance(item.get("item_id"), str)}
        if len(by_item) != len(items):
            _fail("batch detail item identity is invalid")
        applied_attempts = [attempt for attempt in attempts if isinstance(attempt, dict) and attempt.get("mode") == "apply_atomic" and attempt.get("attempt_status") == "applied"]
        if len(applied_attempts) > 1:
            _fail("batch detail has multiple applied attempts")
        for attempt in applied_attempts:
            attempt_id = _string(attempt.get("attempt_id"), "applied_attempt_id")
            if attempt_id is None:
                _fail("applied attempt_id is missing")
            delta = attempt.get("normalized_delta")
            inserts = delta.get("inserts") if isinstance(delta, dict) else None
            if not isinstance(inserts, list):
                _fail("applied normalized_delta is invalid")
            for index, raw_quad in enumerate(inserts):
                quad = _quad_tuple(raw_quad)
                if quad[3] not in graphs.values():
                    _fail("applied delta targets an unknown graph")
                raw_value = raw_quad if isinstance(raw_quad, dict) else list(quad)
                digest = canonical_digest(raw_value)
                entry = (index, quad, raw_value)
                deltas[(batch_id, attempt_id, digest)].append(entry)
                # A few retained receipt projections expose quads as the v1
                # four-element list while newer projections expose a named
                # object.  Both are the same normalized quad; accepting either
                # canonical representation keeps the selector receipt-bound
                # without accepting a label-derived term.
                alternate_digest = canonical_digest(list(quad))
                if alternate_digest != digest:
                    deltas[(batch_id, attempt_id, alternate_digest)].append(entry)
            results = attempt.get("items")
            if not isinstance(results, list):
                _fail("applied attempt items are invalid")
            for result in results:
                if not isinstance(result, dict) or result.get("status") != "applied":
                    _fail("applied attempt item is invalid")
                item_id = _string(result.get("item_id"), "applied item_id")
                assert item_id is not None
                if item_id not in by_item:
                    _fail("applied attempt item has no formal command")
                resource_outputs = result.get("resource_outputs")
                if isinstance(resource_outputs, dict) and isinstance(resource_outputs.get("resource_iri"), str) and resource_outputs["resource_iri"]:
                    outputs[(batch_id, item_id)] = resource_outputs["resource_iri"]
            applied.append((batch_id, attempt_id, attempt))
    return outputs, deltas, applied


def _validate_term_bindings(
    candidate: dict[str, Any],
    raw_bindings: Any,
    outputs: Mapping[tuple[str, str], str],
    deltas: Mapping[tuple[str, str, str], list[tuple[int, tuple[str, str, str, str], dict[str, Any]]]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_bindings, list) or not raw_bindings:
        _fail("term_bindings are empty")
    expected_positions = {(item["assertion_id"], position) for item in candidate["items"] for position in ("subject", "predicate", "object")}
    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    candidate_by_id = {item["assertion_id"]: item for item in candidate["items"]}
    for raw in raw_bindings:
        row = _exact(raw, TERM_BINDING_FIELDS, "term binding")
        assertion_id = _string(row.get("assertion_id"), "term binding assertion_id")
        position = _string(row.get("term_position"), "term binding term_position")
        candidate_term = _string(row.get("candidate_term"), "term binding candidate_term")
        kind = _string(row.get("binding_kind"), "term binding binding_kind")
        client_item_id = _string(row.get("client_item_id"), "term binding client_item_id")
        batch_id = _string(row.get("batch_id"), "term binding batch_id")
        attempt_id = _string(row.get("applied_attempt_id"), "term binding applied_attempt_id")
        quad_digest = _digest(row.get("quad_digest"), "term binding quad_digest")
        delta_index = row.get("delta_index")
        if isinstance(delta_index, bool) or not isinstance(delta_index, int) or delta_index < 0:
            _fail("term binding delta_index is invalid")
        output_iri = row.get("resource_output_iri")
        if kind not in {"literal_delta", "resource_output", "relation_delta", "vocabulary"}:
            _fail("term binding binding_kind is invalid")
        if position not in {"subject", "predicate", "object"}:
            _fail("term binding term_position is invalid")
        if assertion_id not in candidate_by_id:
            _fail("term binding assertion_id is unknown")
        assert assertion_id is not None and position is not None and candidate_term is not None and client_item_id is not None and batch_id is not None and attempt_id is not None
        key = (assertion_id, position)
        if key in seen:
            _fail("term binding is ambiguous")
        seen.add(key)
        if kind == "resource_output":
            _string(output_iri, "resource_output_iri")
            if outputs.get((batch_id, client_item_id)) != output_iri:
                _fail("term binding resource output is not receipt-bound")
        elif output_iri is not None:
            _fail("term binding resource_output_iri must be null")
        selected = deltas.get((batch_id, attempt_id, quad_digest))
        if kind in {"literal_delta", "relation_delta"}:
            if not selected or len(selected) != 1 or selected[0][0] != delta_index:
                _fail("term binding delta selector is missing or ambiguous")
        normalized.append(row)
    if seen != expected_positions:
        _fail("term_bindings do not exactly cover candidate terms")
    return _sorted_unique(normalized, "term_bindings")


def _term_value(value: str) -> str:
    """Normalize only RDF IRI delimiters; lexical literals remain untouched."""
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    return value


def _literal_semantic_equal(candidate: dict[str, Any], actual: dict[str, Any]) -> bool:
    if actual.get("object_kind") != "literal":
        return False
    if actual.get("object") != candidate.get("object"):
        return False
    candidate_language = candidate.get("object_language")
    actual_language = actual.get("object_language")
    if candidate_language or actual_language:
        return candidate_language == actual_language and candidate.get("object_datatype") in (None, "") and actual.get("object_datatype") in (None, "")
    candidate_datatype = candidate.get("object_datatype")
    actual_datatype = actual.get("object_datatype")
    xsd_string = "http://www.w3.org/2001/XMLSchema#string"
    if candidate_datatype in (None, xsd_string) and actual_datatype in (None, xsd_string):
        return True
    return candidate_datatype == actual_datatype


def _assert_materialized_terms(
    candidate: dict[str, Any],
    term_bindings: Sequence[dict[str, Any]],
    quads: Sequence[dict[str, Any]],
    outputs: Mapping[tuple[str, str], str],
    deltas: Mapping[tuple[str, str, str], list[tuple[int, tuple[str, str, str, str], dict[str, Any]]]],
) -> None:
    """Ensure each quad term comes from the selected receipt, never a label."""
    by_key = {(row["assertion_id"], row["term_position"]): row for row in term_bindings}
    candidate_by_id = {item["assertion_id"]: item for item in candidate["items"]}
    if len(quads) != len(candidate_by_id):
        _fail("materialized_quads do not exactly cover candidate assertions")
    # Candidate assertions are unique; materialized quads are canonical, so
    # match by the predicate/object identity after deriving each bound term.
    unused = list(quads)
    for assertion_id, item in candidate_by_id.items():
        values: dict[str, str] = {}
        for position in ("subject", "predicate", "object"):
            row = by_key[(assertion_id, position)]
            kind = row["binding_kind"]
            if kind == "resource_output":
                selected = outputs.get((row["batch_id"], row["client_item_id"]))
                if selected is None:
                    _fail("materialized term lacks resource receipt")
                values[position] = _term_value(selected)
            elif kind in {"literal_delta", "relation_delta"}:
                selected = deltas.get((row["batch_id"], row["applied_attempt_id"], row["quad_digest"]))
                if not selected or len(selected) != 1:
                    _fail("materialized term lacks unique delta selector")
                selected_term = selected[0][1][{"subject": 0, "predicate": 1, "object": 2}[position]]
                values[position] = _term_value(selected_term)
            else:
                values[position] = _term_value(item[position])
        matching: list[dict[str, Any]] = []
        for quad in unused:
            if _term_value(quad["subject"]) != values["subject"] or _term_value(quad["predicate"]) != values["predicate"]:
                continue
            if item["object_kind"] == "literal":
                if _literal_semantic_equal(item, quad):
                    matching.append(quad)
            else:
                candidate_kind = item.get("object_kind")
                materialized_kind = quad.get("object_kind")
                kind_matches = materialized_kind == candidate_kind or (
                    candidate_kind == "resource" and materialized_kind == "iri"
                )
                if _term_value(quad["object"]) == values["object"] and kind_matches:
                    matching.append(quad)
        if len(matching) != 1:
            _fail("materialized quad does not match receipt-bound candidate terms")
        unused.remove(matching[0])
    if unused:
        _fail("materialized_quads contain unbound assertions")


def _validate_quads(raw_quads: Any, graph: str) -> list[dict[str, Any]]:
    if not isinstance(raw_quads, list) or not raw_quads:
        _fail("materialized_quads are empty")
    normalized: list[dict[str, Any]] = []
    for raw in raw_quads:
        quad = _exact(raw, QUAD_FIELDS, "materialized quad")
        if quad.get("graph_role") != "asserted_data" or quad.get("source_graph_iri") != graph:
            _fail("materialized quad graph is invalid")
        for field in ("subject", "predicate", "object", "object_kind"):
            _string(quad.get(field), f"materialized quad {field}")
        for field in ("object_datatype", "object_language"):
            if quad.get(field) is not None:
                _string(quad.get(field), f"materialized quad {field}")
        normalized.append(quad)
    return _sorted_unique(normalized, "materialized_quads")


def _validate_lineage(raw: Any, quads: Sequence[dict[str, Any]], evidence_bindings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    # The public v2 contract uses a direct record array.  A records-only
    # wrapper remains readable for retained fixture receipts, but no other
    # wrapper shape is accepted.
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict) and set(raw) == {"records"}:
        records = raw["records"]
    else:
        _fail("statement_lineage is invalid")
    if not isinstance(records, list) or not records:
        _fail("statement_lineage records are empty")
    expected_assertions = {binding["assertion_id"] for binding in evidence_bindings}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    quad_by_key = {canonical_bytes(quad): quad for quad in quads}
    for raw_record in records:
        record = _exact(raw_record, LINEAGE_FIELDS, "statement lineage record")
        assertion_id = _string(record.get("assertion_id"), "lineage assertion_id")
        fact_id = _digest(record.get("fact_id"), "lineage fact_id")
        target = _exact(record.get("target"), TARGET_FIELDS, "lineage target")
        target_kind = _string(target.get("target_kind"), "lineage target_kind")
        target_id = _string(target.get("target_id"), "lineage target_id")
        if target_kind not in {"resource", "statement"}:
            _fail("lineage target_kind is invalid")
        response = record.get("response")
        data = _envelope(response, "statement lineage response")
        if assertion_id in seen:
            _fail("statement lineage assertion is duplicated")
        if assertion_id not in expected_assertions:
            _fail("statement lineage assertion is unbound")
        quad = _exact(record.get("quad"), QUAD_FIELDS, "lineage quad")
        if canonical_bytes(quad) not in quad_by_key:
            _fail("statement lineage quad is unbound")
        # A statement target is always the calculated fact ID; a resource
        # target identifies a generated platform resource and must not be
        # inferred from a decorate/read-model appearance.
        if target_kind == "statement" and target_id != fact_id:
            _fail("statement lineage target fact drifts")
        evidence_refs = _evidence_reference_ids(data)
        if not evidence_refs:
            _fail("statement lineage response lacks EvidenceReference association")
        seen.add(assertion_id)
        normalized.append(record)
    if seen != expected_assertions:
        _fail("statement lineage is incomplete")
    return _sorted_unique(normalized, "statement_lineage records")


def _evidence_reference_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"evidence_reference_id", "evidence_reference", "evidence_references"}:
                values = item if isinstance(item, list) else [item]
                for value_item in values:
                    if isinstance(value_item, str) and value_item:
                        found.add(value_item)
                    elif isinstance(value_item, dict):
                        for candidate_key in ("id", "evidence_reference_id", "reference_id"):
                            if isinstance(value_item.get(candidate_key), str) and value_item[candidate_key]:
                                found.add(value_item[candidate_key])
            found.update(_evidence_reference_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_evidence_reference_ids(item))
    return found


def _validate_pagination(raw: Any) -> dict[str, Any]:
    pagination = _exact(raw, PAGINATION_FIELDS, "pagination")
    streams = pagination.get("streams")
    if not isinstance(streams, list) or not streams:
        _fail("pagination streams are empty")
    stream_values: dict[str, list[dict[str, Any]]] = {}
    all_match_ids: set[str] = set()
    context_roots: set[str] = set()
    cursor_tokens: dict[str, str] = {}
    for raw_stream in streams:
        stream = _exact(raw_stream, STREAM_FIELDS, "pagination stream")
        kind = _string(stream.get("stream_kind"), "pagination stream_kind")
        if kind not in {"matches", "context"}:
            _fail("pagination stream_kind is invalid")
        assert kind is not None
        if kind in stream_values:
            _fail("pagination contains duplicate stream")
        pages = stream.get("pages")
        if not isinstance(pages, list) or not pages:
            _fail("pagination stream pages are empty")
        previous_next: str | None = None
        fingerprints: set[str] = set()
        normalized_pages: list[dict[str, Any]] = []
        identities: dict[str, bytes] = {}
        for index, raw_page in enumerate(pages):
            page = _exact(raw_page, PAGE_FIELDS, "pagination page")
            if page.get("stream_kind") != kind:
                _fail("pagination page stream_kind drifts")
            fingerprint = _digest(page.get("request_fingerprint_sha256"), "pagination request fingerprint")
            fingerprints.add(fingerprint)
            page_index = page.get("page_index")
            if isinstance(page_index, bool) or not isinstance(page_index, int) or page_index != index:
                _fail("pagination page_index is not contiguous")
            request_cursor = page.get("request_cursor")
            if index == 0 and request_cursor is not None:
                _fail("pagination first request_cursor must be null")
            if index > 0 and request_cursor != previous_next:
                _fail("pagination request_cursor does not continue prior page")
            next_cursor = page.get("next_cursor")
            if next_cursor is not None:
                _string(next_cursor, "pagination next_cursor")
                if next_cursor in cursor_tokens:
                    _fail("pagination cursor is reused across streams")
                cursor_tokens[next_cursor] = kind
            previous_next = next_cursor
            response = page.get("response")
            data = _envelope(response, "pagination response")
            if data.get("truncated") is not False or data.get("degraded") is not False:
                _fail("pagination response is incomplete")
            warnings = data.get("blocking_warnings", data.get("warnings", []))
            if warnings not in (None, []) and warnings:
                _fail("pagination response has blocking warnings")
            expected_response_digest = canonical_digest(response)
            if page.get("response_digest") != expected_response_digest:
                _fail("pagination response_digest drifts")
            root_ids = data.get("root_match_ids", data.get("root_ids", []))
            if root_ids is None:
                root_ids = []
            if not isinstance(root_ids, list) or any(not isinstance(item, str) or not item for item in root_ids):
                _fail("pagination root match IDs are invalid")
            root_ids = sorted(set(root_ids))
            if page.get("root_match_ids_digest") != canonical_digest(root_ids):
                _fail("pagination root_match_ids_digest drifts")
            if kind == "matches":
                all_match_ids.update(root_ids)
                item_values = data.get("items", data.get("matches", data.get("primary_matches", [])))
            else:
                context_roots.update(root_ids)
                item_values = data.get("items", data.get("context", data.get("related_context", [])))
            if not isinstance(item_values, list):
                _fail("pagination response items are invalid")
            for item in item_values:
                if not isinstance(item, dict):
                    _fail("pagination response item is invalid")
                identity = item.get("id", item.get("fact_id", item.get("statement_id", item.get("iri"))))
                if not isinstance(identity, str) or not identity:
                    continue
                item_bytes = canonical_bytes(item)
                previous_item = identities.get(identity)
                if previous_item is not None and previous_item != item_bytes:
                    _fail("pagination duplicate identity has conflicting content")
                identities[identity] = item_bytes
            normalized_pages.append(page)
        if fingerprints == set():
            _fail("pagination request fingerprint is missing")
        if previous_next is not None:
            _fail("pagination final next_cursor must be null")
        stream_values[kind] = normalized_pages
    if set(stream_values) != {"matches", "context"}:
        _fail("pagination must contain independent matches and context streams")
    if not context_roots.issubset(all_match_ids):
        _fail("pagination context roots are outside final match union")
    return pagination


def _validate_candidate_binding_scope(candidate: Mapping[str, Any], matrix_binding: Any | None) -> None:
    if matrix_binding is None:
        return
    if not isinstance(matrix_binding, dict) or set(matrix_binding) != {"proof_matrix_path", "proof_matrix_digest"}:
        _fail("candidate matrix_binding is invalid")
    _string(matrix_binding.get("proof_matrix_path"), "candidate proof_matrix_path")
    _digest(matrix_binding.get("proof_matrix_digest"), "candidate proof_matrix_digest")


def verify_proof_v2(proof: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the complete fifteen-field native proof v2 envelope."""
    proof_value = json.loads(json.dumps(proof))
    if not isinstance(proof_value, dict) or set(proof_value) != V2_PROOF_FIELDS:
        _fail("native proof v2 has missing or extra fields")
    if proof_value.get("mode") != "create":
        _fail("native proof v2 requires create mode")
    initial = _envelope(proof_value["initial_modeling_context"], "initial modeling context")
    final = _envelope(proof_value["final_modeling_context"], "final modeling context")
    workspace = _envelope(proof_value["workspace_context"], "workspace context")
    initial_ontology = initial.get("ontology")
    final_ontology = final.get("ontology")
    ontology_id = _string(initial_ontology.get("id") if isinstance(initial_ontology, dict) else None, "initial ontology id")
    if not isinstance(final_ontology, dict) or final_ontology.get("id") != ontology_id:
        _fail("modeling context identity drifts")
    if workspace.get("ontology_id") != ontology_id or workspace.get("state") != "ready":
        _fail("workspace does not bind the selected ontology")
    graph_set_id = _string(workspace.get("default_graph_set_id"), "default_graph_set_id")
    source_signature = _string(workspace.get("source_signature"), "source_signature")
    assert ontology_id is not None and graph_set_id is not None and source_signature is not None
    graphs = _graph_roles(workspace, ontology_id)
    initial_counts = _counts(initial)
    _counts(final)
    if any(initial_counts.values()):
        _fail("native proof v2 requires an initially empty create scope")

    inventory = proof_value["batch_inventory"]
    if not isinstance(inventory, dict):
        _fail("batch inventory is invalid")
    inventory_data = _envelope(inventory.get("response"), "batch inventory")
    requested_limit = inventory.get("requested_limit")
    if isinstance(requested_limit, bool) or not isinstance(requested_limit, int) or requested_limit <= 0 or inventory.get("cursor") is not None or inventory.get("status_filter") is not None:
        _fail("batch inventory must be unfiltered")
    inventory_batches = inventory_data.get("batches")
    if not isinstance(inventory_batches, list) or inventory_data.get("next_cursor") is not None or requested_limit <= len(inventory_batches):
        _fail("batch inventory is incomplete")
    inventory_ids = {_string(item.get("batch_id"), "batch_id") for item in inventory_batches if isinstance(item, dict)}
    if None in inventory_ids or len(inventory_ids) != len(inventory_batches):
        _fail("batch inventory item is invalid")
    details_raw = proof_value["batch_details"]
    if not isinstance(details_raw, list) or not details_raw:
        _fail("batch details are unavailable")
    details = [_envelope(value, "batch detail") for value in details_raw]
    detail_ids = {_string(value.get("batch_id"), "batch_id") for value in details}
    if None in detail_ids or detail_ids != inventory_ids or len(detail_ids) != len(details):
        _fail("batch inventory does not exactly match details")
    outputs, deltas, applied = _collect_receipts(details, graphs)
    if not applied:
        _fail("native proof v2 requires an applied write batch")
    candidate = _validate_candidate(proof_value["candidate_required_assertions"])
    _validate_candidate_binding_scope(candidate, candidate.get("matrix_binding"))
    term_bindings = _validate_term_bindings(candidate, proof_value["term_bindings"], outputs, deltas)
    quads = _validate_quads(proof_value["materialized_quads"], graphs["asserted_data"])
    _assert_materialized_terms(candidate, term_bindings, quads, outputs, deltas)
    evidence_bindings_raw = proof_value["evidence_bindings"]
    if not isinstance(evidence_bindings_raw, list) or not evidence_bindings_raw:
        _fail("evidence_bindings are empty")
    evidence_bindings: list[dict[str, Any]] = []
    for raw in evidence_bindings_raw:
        row = _exact(raw, EVIDENCE_BINDING_FIELDS, "evidence binding")
        for field in EVIDENCE_BINDING_FIELDS:
            _string(row.get(field), f"evidence binding {field}")
        evidence_bindings.append(row)
    _sorted_unique(evidence_bindings, "evidence_bindings")
    # Evidence rows are checked against candidate citation cardinality directly
    # here; map-level validation can be run independently before submit.
    candidate_citations = {
        (item["assertion_id"], citation_digest(citation))
        for item in candidate["items"]
        for citation in item["evidence_citations"]
    }
    binding_citations = {(row["assertion_id"], row["citation_digest"]) for row in evidence_bindings}
    if binding_citations != candidate_citations:
        _fail("evidence_bindings do not exactly cover candidate citations")
    if len(evidence_bindings) != len(binding_citations):
        _fail("evidence_bindings contain duplicate citation rows")
    term_digest = canonical_digest(term_bindings)
    evidence_digest = canonical_digest(evidence_bindings)
    materialized_payload = {
        "candidate_digest": candidate["candidate_digest"],
        "term_bindings_digest": term_digest,
        "evidence_bindings_digest": evidence_digest,
        "materialized_quads": quads,
    }
    if proof_value.get("materialized_digest") != canonical_digest(materialized_payload):
        _fail("materialized_digest drifts")
    # The lineage array is deliberately checked after evidence cardinality so
    # a decoration/read-model response cannot mask an omitted Evidence row.
    lineage = _validate_lineage(proof_value["statement_lineage"], quads, evidence_bindings)
    _validate_pagination(proof_value["pagination"])
    statements = proof_value["statements_read"]
    if not isinstance(statements, dict):
        _fail("statement read request is invalid")
    statements_data = _envelope(statements.get("response"), "statement read")
    if statements_data.get("graph_set_id") != graph_set_id or statements_data.get("source_signature") != source_signature or statements_data.get("model_name") != "statement-list" or statements_data.get("include") != "asserted":
        _fail("statement read does not bind the verified workspace")
    statement_items = statements_data.get("items")
    if not isinstance(statement_items, list):
        _fail("statement read items are invalid")
    statement_ids = {_string(item.get("fact_id"), "statement fact_id") for item in statement_items if isinstance(item, dict) and item.get("fact_id") is not None}
    if None in statement_ids:
        _fail("statement fact ID is invalid")
    lineage_ids = {row["fact_id"] for row in lineage}
    if not lineage_ids.issubset(statement_ids):
        _fail("statement lineage fact is not read back")
    return {
        "complete": True,
        "proof_version": 2,
        "ontology_id": ontology_id,
        "candidate_digest": candidate["candidate_digest"],
        "term_bindings_digest": term_digest,
        "evidence_bindings_digest": evidence_digest,
        "materialized_digest": proof_value["materialized_digest"],
        "lineage_count": len(lineage),
    }


__all__ = [
    "ProofV2Error",
    "V2_PROOF_FIELDS",
    "canonical_bytes",
    "canonical_digest",
    "citation_digest",
    "citation_group_digest",
    "inline_evidence_identity",
    "build_candidate_item_evidence_map",
    "validate_candidate_item_evidence_map",
    "compare_dry_run_group_projection",
    "verify_postapply_evidence_bindings",
    "verify_proof_v2",
]
