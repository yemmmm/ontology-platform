"""Pure, fail-closed P2a candidate-to-Batch planning mechanics.

The module has no platform client, runtime context, or Host operation.  It
only validates the frozen P2a candidate/receipt/map triple, emits the exact
four-item Batch plan, and validates safe dry-run Evidence projections.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

try:
    from .proof_v2 import (
        ProofV2Error,
        _validate_candidate,
        canonical_bytes,
        canonical_digest,
        inline_evidence_identity,
        validate_candidate_item_evidence_map,
    )
except ImportError:  # pragma: no cover - exercised by the private /opt MCP mount
    from proof_v2 import (  # type: ignore[no-redef]
        ProofV2Error,
        _validate_candidate,
        canonical_bytes,
        canonical_digest,
        inline_evidence_identity,
        validate_candidate_item_evidence_map,
    )


P2A_TASK_ID = "p2a-protocol-production"
P2A_PLAN_SCHEMA = "p2a-batch-plan/v1"
P2A_CANDIDATE_REVISION = "p2a-generated-2"
P2A_CANDIDATE_DELIVERY_ID = "p2a-candidate-delivery-1"
P2A_SEMANTIC_DIGEST = "780ae626e0c94cbc51d5d8aff262bf7d4dbff07d6cb3d5ffbb6fd97a937f4e91"
P2A_CANDIDATE_DIGEST = "22f03578616c3753f0d231308bb1da52bdff7a79cafdad0d5890f1f2c70f0ec7"
XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
OWL_THING = "http://www.w3.org/2002/07/owl#Thing"

ASSERTION_CLIENT_ITEM_IDS = {
    "r23002-a008": "p2a-01-literal-a008",
    "r23002-a009": "p2a-02-resource-a009",
    "r23002-a004": "p2a-03-relation-a004",
    "r23002-a001": "p2a-04-vocabulary-a001",
}
_ASSERTION_ORDER = tuple(ASSERTION_CLIENT_ITEM_IDS)
_EXPECTED_TERMS = {
    "r23002-a008": {
        "subject": "p2a:generated-subject",
        "predicate": "urn:p2a:publicationStatus",
        "object": "published",
        "object_kind": "literal",
        "object_datatype": XSD_STRING,
        "object_language": None,
    },
    "r23002-a009": {
        "subject": "p2a:generated-subject",
        "predicate": "urn:p2a:hasOutput",
        "object": "urn:p2a:output",
        "object_kind": "resource",
        "object_datatype": None,
        "object_language": None,
    },
    "r23002-a004": {
        "subject": "urn:p2a:workflow",
        "predicate": "urn:p2a:hasVersion",
        "object": "p2a:generated-subject",
        "object_kind": "resource",
        "object_datatype": None,
        "object_language": None,
    },
    "r23002-a001": {
        "subject": "p2a:generated-subject",
        "predicate": RDF_TYPE,
        "object": "urn:p2a:FixtureResource",
        "object_kind": "resource",
        "object_datatype": None,
        "object_language": None,
    },
}
_RECEIPT_FIELDS = {
    "status",
    "candidate_revision",
    "semantic_digest",
    "candidate_digest",
}
_PLAN_ROW_FIELDS = {
    "client_item_id",
    "document_name",
    "normalized_excerpt_sha256",
    "dedupe_identity",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class P2ABatchPlanError(ValueError):
    """The frozen P2a plan or its authoritative evidence has drifted."""


def _fail(message: str) -> None:
    raise P2ABatchPlanError(message)


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{name} is not bound")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        _fail(f"{name} is invalid")
    return value


def _validate_frozen_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = _validate_candidate(_copy(candidate))
    except (ProofV2Error, TypeError, ValueError) as exc:
        raise P2ABatchPlanError("candidate is invalid") from exc
    raw_items = candidate.get("items")
    if not isinstance(raw_items, list) or raw_items != value["items"]:
        _fail("candidate item order drifts")
    if (
        value.get("candidate_revision") != P2A_CANDIDATE_REVISION
        or value.get("delivery_id") != P2A_CANDIDATE_DELIVERY_ID
        or value.get("reply_chain") != [P2A_CANDIDATE_DELIVERY_ID]
        or value.get("semantic_digest") != P2A_SEMANTIC_DIGEST
        or value.get("candidate_digest") != P2A_CANDIDATE_DIGEST
    ):
        _fail("frozen candidate identity or semantic content drifts")
    by_assertion = {item["assertion_id"]: item for item in value["items"]}
    if set(by_assertion) != set(_ASSERTION_ORDER) or len(by_assertion) != 4:
        _fail("candidate assertion set drifts")
    for assertion_id, terms in _EXPECTED_TERMS.items():
        item = by_assertion[assertion_id]
        if item.get("graph_role") != "asserted_data":
            _fail(f"{assertion_id} graph role drifts")
        if any(item.get(field) != expected for field, expected in terms.items()):
            _fail(f"{assertion_id} terms drift")
    return value


def _validate_receipt(candidate: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_FIELDS:
        _fail("candidate receipt fields drift")
    expected = {
        "status": "accepted",
        "candidate_revision": candidate["candidate_revision"],
        "semantic_digest": candidate["semantic_digest"],
        "candidate_digest": candidate["candidate_digest"],
    }
    if dict(receipt) != expected:
        _fail("candidate receipt does not exactly bind candidate")


def _validate_map(
    candidate: Mapping[str, Any],
    evidence_map: Mapping[str, Any],
    expected_run_id: str | None,
) -> dict[str, Any]:
    try:
        value = validate_candidate_item_evidence_map(
            candidate,
            evidence_map,
            expected_run_id=expected_run_id,
        )
    except (ProofV2Error, TypeError, ValueError) as exc:
        raise P2ABatchPlanError("candidate item Evidence map is invalid") from exc
    bindings: dict[str, str] = {}
    for row in value["rows"]:
        assertion_id = row["assertion_id"]
        client_item_id = row["client_item_id"]
        previous = bindings.setdefault(assertion_id, client_item_id)
        if previous != client_item_id:
            _fail("one assertion maps to multiple client item IDs")
    if bindings != ASSERTION_CLIENT_ITEM_IDS:
        _fail("candidate item IDs drift")
    return value


def _inline_evidence(item: Mapping[str, Any]) -> list[dict[str, str]]:
    values = [
        {"document_name": citation["document_name"], "excerpt": citation["excerpt"]}
        for citation in item["evidence_citations"]
    ]
    ordered = sorted(values, key=canonical_bytes)
    if len({canonical_bytes(value) for value in ordered}) != len(ordered):
        _fail("inline Evidence contains duplicate values")
    return ordered


def build_p2a_batch_plan(
    candidate: Mapping[str, Any],
    candidate_item_evidence_map: Mapping[str, Any],
    candidate_receipt: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    """Compile the frozen P2a candidate to exactly one entity and three relations."""
    candidate_value = _validate_frozen_candidate(candidate)
    _validate_receipt(candidate_value, candidate_receipt)
    evidence_map = _validate_map(candidate_value, candidate_item_evidence_map, expected_run_id)
    by_assertion = {item["assertion_id"]: item for item in candidate_value["items"]}
    entity_id = ASSERTION_CLIENT_ITEM_IDS["r23002-a008"]
    items = [
        {
            "client_item_id": entity_id,
            "command_kind": "create_entity",
            "payload": {
                "entity_id": None,
                "class_iri_or_legacy_id": OWL_THING,
                "label": "P2a generated subject",
                "aliases": [],
                "properties": {"urn:p2a:publicationStatus": "published"},
            },
            "depends_on": [],
            "evidence_reference_ids": [],
            "evidence": _inline_evidence(by_assertion["r23002-a008"]),
            "rationale": "Materialize the approved P2a literal assertion as a plain literal.",
            "competency_question_ids": [],
        },
        {
            "client_item_id": ASSERTION_CLIENT_ITEM_IDS["r23002-a009"],
            "command_kind": "create_relation",
            "payload": {
                "source_entity_iri": {
                    "item_ref": {"client_item_id": entity_id, "output": "resource_iri"}
                },
                "relation_type_iri": "urn:p2a:hasOutput",
                "target_entity_iri": "urn:p2a:output",
            },
            "depends_on": [entity_id],
            "evidence_reference_ids": [],
            "evidence": _inline_evidence(by_assertion["r23002-a009"]),
            "rationale": "Materialize the approved generated-subject output relation.",
            "competency_question_ids": [],
        },
        {
            "client_item_id": ASSERTION_CLIENT_ITEM_IDS["r23002-a004"],
            "command_kind": "create_relation",
            "payload": {
                "source_entity_iri": "urn:p2a:workflow",
                "relation_type_iri": "urn:p2a:hasVersion",
                "target_entity_iri": {
                    "item_ref": {"client_item_id": entity_id, "output": "resource_iri"}
                },
            },
            "depends_on": [entity_id],
            "evidence_reference_ids": [],
            "evidence": _inline_evidence(by_assertion["r23002-a004"]),
            "rationale": "Materialize the approved workflow version relation.",
            "competency_question_ids": [],
        },
        {
            "client_item_id": ASSERTION_CLIENT_ITEM_IDS["r23002-a001"],
            "command_kind": "create_relation",
            "payload": {
                "source_entity_iri": {
                    "item_ref": {"client_item_id": entity_id, "output": "resource_iri"}
                },
                "relation_type_iri": RDF_TYPE,
                "target_entity_iri": "urn:p2a:FixtureResource",
            },
            "depends_on": [entity_id],
            "evidence_reference_ids": [],
            "evidence": _inline_evidence(by_assertion["r23002-a001"]),
            "rationale": "Materialize the approved generated-subject vocabulary relation.",
            "competency_question_ids": [],
        },
    ]
    return {
        "schema_version": P2A_PLAN_SCHEMA,
        "run_id": evidence_map["run_id"],
        "candidate_digest": candidate_value["candidate_digest"],
        "items": items,
    }


def _unwrap(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} is invalid")
    if set(value) == {"ok", "data"}:
        if value.get("ok") is not True or not isinstance(value.get("data"), dict):
            _fail(f"{name} envelope is unsuccessful")
        return value["data"]
    return value


def _validated_dry_run(value: Any, name: str) -> tuple[str, str, dict[str, Any], list[str]]:
    detail = _unwrap(value, name)
    batch_id = _string(detail.get("batch_id"), f"{name} batch_id")
    items = detail.get("items")
    if not isinstance(items, list):
        _fail(f"{name} items are invalid")
    client_item_ids = [
        _string(item.get("client_item_id"), f"{name} client_item_id")
        for item in items
        if isinstance(item, dict)
    ]
    if len(client_item_ids) != len(items) or len(client_item_ids) != len(set(client_item_ids)):
        _fail(f"{name} item identities are invalid")
    attempts = detail.get("attempts")
    if isinstance(attempts, list):
        valid = [
            attempt
            for attempt in attempts
            if isinstance(attempt, dict)
            and attempt.get("mode") == "dry_run"
            and attempt.get("attempt_status") == "validated"
        ]
    elif detail.get("mode") == "dry_run" and detail.get("attempt_status") == "validated":
        valid = [detail]
    else:
        _fail(f"{name} attempts are invalid")
    if len(valid) != 1:
        _fail(f"{name} must contain exactly one validated dry-run")
    attempt = valid[0]
    attempt_id = _string(attempt.get("attempt_id"), f"{name} attempt_id")
    findings = attempt.get("findings")
    if not isinstance(findings, list):
        _fail(f"{name} findings are invalid")
    if any(isinstance(item, dict) and item.get("code") == "missing_evidence" for item in findings):
        _fail(f"{name} reports missing Evidence")
    plan = attempt.get("operation_plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("evidence"), list):
        _fail(f"{name} Evidence operation plan is unavailable")
    return batch_id, attempt_id, attempt, sorted(client_item_ids)


def _projection(
    evidence_map: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    expected_groups = {
        (row["client_item_id"], row["inline_evidence_identity"])
        for row in evidence_map["rows"]
    }
    plan = attempt["operation_plan"]
    raw_rows = plan["evidence"]
    projected: list[dict[str, str]] = []
    identity_to_dedupe: dict[str, str] = {}
    dedupe_to_identity: dict[str, str] = {}
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict) or set(raw) != _PLAN_ROW_FIELDS:
            _fail(f"dry-run Evidence row {index} fields drift")
        client_item_id = _string(raw.get("client_item_id"), "dry-run client_item_id")
        document_name = _string(raw.get("document_name"), "dry-run document_name")
        excerpt_hash = _digest(
            raw.get("normalized_excerpt_sha256"),
            "dry-run normalized_excerpt_sha256",
        )
        dedupe = _string(raw.get("dedupe_identity"), "dry-run dedupe_identity")
        identity = inline_evidence_identity(document_name, excerpt_hash)
        if (client_item_id, identity) not in expected_groups:
            _fail("dry-run Evidence projection contains an unexpected group")
        if identity in identity_to_dedupe and identity_to_dedupe[identity] != dedupe:
            _fail("one inline identity maps to multiple dedupe identities")
        if dedupe in dedupe_to_identity and dedupe_to_identity[dedupe] != identity:
            _fail("one dedupe identity maps to multiple inline identities")
        identity_to_dedupe[identity] = dedupe
        dedupe_to_identity[dedupe] = identity
        projected.append(
            {
                "client_item_id": client_item_id,
                "inline_evidence_identity": identity,
                "dedupe_identity": dedupe,
            }
        )
    encoded = [canonical_bytes(row) for row in projected]
    if len(encoded) != len(set(encoded)):
        _fail("dry-run Evidence projection contains duplicate groups")
    projected = sorted(projected, key=canonical_bytes)
    if {(row["client_item_id"], row["inline_evidence_identity"]) for row in projected} != expected_groups:
        _fail("dry-run Evidence projection is incomplete")
    bijection = sorted(
        (
            {"inline_evidence_identity": identity, "dedupe_identity": dedupe}
            for identity, dedupe in identity_to_dedupe.items()
        ),
        key=canonical_bytes,
    )
    return projected, bijection


def _verify_postapply_bindings(
    plan_rows: Sequence[Mapping[str, str]],
    bindings: Any,
) -> None:
    if not isinstance(bindings, list):
        _fail("post-apply Evidence bindings are invalid")
    expected = {
        (row["client_item_id"], row["inline_evidence_identity"], row["dedupe_identity"])
        for row in plan_rows
    }
    actual: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            _fail(f"post-apply Evidence binding {index} is invalid")
        client_item_id = _string(binding.get("client_item_id"), "binding client_item_id")
        identity = _digest(
            binding.get("inline_evidence_identity"),
            "binding inline_evidence_identity",
        )
        reference_id = _string(
            binding.get("evidence_reference_id"),
            "binding evidence_reference_id",
        )
        actual.add((client_item_id, identity, reference_id))
    if actual != expected:
        _fail("post-apply Evidence bindings do not back-reference dry-run identities")


def verify_p2a_dry_run_evidence_projection(
    candidate: Mapping[str, Any],
    candidate_item_evidence_map: Mapping[str, Any],
    dry_run_receipt: Mapping[str, Any],
    detail_read_1: Mapping[str, Any],
    detail_read_2: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
    postapply_evidence_bindings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate receipt plus two authorized detail reads and the 4-to-3 projection."""
    candidate_value = _validate_frozen_candidate(candidate)
    evidence_map = _validate_map(candidate_value, candidate_item_evidence_map, expected_run_id)
    expected_item_ids = sorted(ASSERTION_CLIENT_ITEM_IDS.values())
    sources = [dry_run_receipt, detail_read_1, detail_read_2]
    observations = [_validated_dry_run(value, name) for value, name in zip(
        sources,
        ("dry-run receipt", "first detail read", "second detail read"),
        strict=True,
    )]
    signatures: list[tuple[str, str, list[str], list[dict[str, str]]]] = []
    bijections: list[list[dict[str, str]]] = []
    for batch_id, attempt_id, attempt, item_ids in observations:
        if item_ids != expected_item_ids:
            _fail("dry-run item set drifts")
        plan_rows, bijection = _projection(evidence_map, attempt)
        signatures.append((batch_id, attempt_id, item_ids, plan_rows))
        bijections.append(bijection)
    if signatures[0] != signatures[1] or signatures[1] != signatures[2]:
        _fail("dry-run receipt and repeated detail reads are not canonically stable")
    if bijections[0] != bijections[1] or bijections[1] != bijections[2]:
        _fail("dry-run Evidence identity bijection is unstable")
    batch_id, attempt_id, _, plan_rows = signatures[0]
    if postapply_evidence_bindings is not None:
        _verify_postapply_bindings(plan_rows, postapply_evidence_bindings)
    return {
        "batch_id": batch_id,
        "dry_run_attempt_id": attempt_id,
        "client_item_ids": expected_item_ids,
        "plan_rows": plan_rows,
        "plan_sha256": canonical_digest(plan_rows),
        "dedupe_by_inline_identity": bijections[0],
        "postapply_bound": postapply_evidence_bindings is not None,
    }


def materialize_overlay_contract(template: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    """Bind the immutable overlay template to one P2a run and recompute self-digest."""
    _string(run_id, "overlay run_id")
    value = _copy(template)
    if value.get("run_id") != "$P2A_RUNTIME_RUN_ID":
        _fail("overlay template run_id placeholder drifts")
    value["run_id"] = run_id
    value.pop("contract_digest", None)
    return {**value, "contract_digest": canonical_digest(value)}


def validate_overlay_contract(
    contract: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_task_id: str = P2A_TASK_ID,
) -> dict[str, Any]:
    """Validate a materialized overlay contract including its canonical self-digest."""
    value = _copy(contract)
    fields = {
        "schema_version",
        "task_id",
        "run_id",
        "server_name",
        "tools",
        "assets",
        "contract_digest",
    }
    if set(value) != fields:
        _fail("overlay contract fields drift")
    digest = value.pop("contract_digest", None)
    if digest != canonical_digest(value):
        _fail("overlay contract self-digest drifts")
    if value.get("schema_version") != "p2a-protocol-overlay-contract/v1":
        _fail("overlay contract schema drifts")
    if value.get("task_id") != expected_task_id or value.get("run_id") != expected_run_id:
        _fail("overlay task/run binding drifts")
    if value.get("server_name") != "p2a_protocol_overlay":
        _fail("overlay server name drifts")
    if value.get("tools") != [
        "build_p2a_batch_plan",
        "verify_p2a_dry_run_evidence_projection",
    ]:
        _fail("overlay tool surface drifts")
    assets = value.get("assets")
    if not isinstance(assets, list) or len(assets) != 3:
        _fail("overlay asset contract drifts")
    expected_mounts = {
        "/opt/p2a_batch_plan.py",
        "/opt/p2a_protocol_overlay_mcp.py",
        "/opt/proof_v2.py",
    }
    if {asset.get("mount_path") for asset in assets if isinstance(asset, dict)} != expected_mounts:
        _fail("overlay asset mounts drift")
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) != {
            "source_path",
            "mount_path",
            "sha256",
            "mode",
        }:
            _fail("overlay asset fields drift")
        _digest(asset.get("sha256"), "overlay asset sha256")
        if asset.get("mode") not in {"0444", "0600"}:
            _fail("overlay asset mode drifts")
    return {**value, "contract_digest": digest}
