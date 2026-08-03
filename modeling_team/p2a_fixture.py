"""No-semantic-start P2a representative fixture.

The driver validates every frozen matrix row and builds a disposable,
generated-IRI proof for four representative rows.  It deliberately has no
``StartLedger`` or Runner import and does not write the tester-owned
``p2a-pass.json``; an independent tester may use the returned hashes to create
that artifact after reviewing the evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .matrix_artifact import MATRIX_RELATIVE, MatrixArtifactError, load_matrix
from .proof_v2 import (
    canonical_bytes,
    canonical_digest,
    citation_digest,
    citation_group_digest,
    inline_evidence_identity,
    verify_proof_v2,
)


GRAPH_ASSERTED_DATA = "https://p2a.example.test/graph/asserted-data"
GRAPH_ASSERTED_ONTOLOGY = "https://p2a.example.test/graph/asserted-ontology"
GRAPH_SHAPES = "https://p2a.example.test/graph/shapes"
ONTOLOGY_ID = "p2a-generated-ontology"
GRAPH_SET_ID = "p2a-generated-graph-set"
SOURCE_SIGNATURE = "p2a-generated-source-signature"


class P2AFixtureError(RuntimeError):
    """The disposable no-start fixture did not satisfy native proof v2."""


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _choose_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    required = {"resource_output", "relation_delta", "literal_delta", "vocabulary"}
    for category in ("resource_output", "relation_delta", "literal_delta", "vocabulary"):
        row = next((item for item in matrix["rows"] if item["binding_category"] == category), None)
        if row is None:
            raise P2AFixtureError(f"matrix lacks representative {category} row")
        chosen.append(row)
    if {row["binding_category"] for row in chosen} != required:
        raise P2AFixtureError("representative matrix rows are not category-complete")
    if not {row["target_kind"] for row in chosen} == {"resource", "statement"}:
        raise P2AFixtureError("representative matrix rows do not cover both target kinds")
    return chosen


def _candidate(matrix: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        item = {
            "assertion_id": row["assertion_id"],
            "graph_role": "asserted_data",
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "object_kind": row["object_kind"],
            "object_datatype": row["object_datatype"],
            "object_language": row["object_language"],
            "evidence_citations": row["approved_citations"],
        }
        items.append(item)
    items.sort(key=canonical_bytes)
    semantic = canonical_digest({"schema_version": "candidate-required-assertions/v2", "statements": items})
    binding = {
        "schema_version": "candidate-required-assertions/v2",
        "candidate_revision": "p2a-representative-1",
        "delivery_id": "p2a-candidate-delivery-1",
        "reply_chain": ["p2a-candidate-delivery-1"],
        "semantic_digest": semantic,
    }
    return {**binding, "candidate_digest": canonical_digest(binding), "items": items}


def _proof(matrix: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    batch_id = "p2a-batch-generated-1"
    attempt_id = "p2a-attempt-generated-1"
    client_ids = {row["assertion_id"]: f"p2a-item-{index}" for index, row in enumerate(rows, 1)}
    generated = {
        row["assertion_id"]: f"https://p2a.example.test/generated/{index}"
        for index, row in enumerate(rows, 1)
    }
    quads: list[dict[str, Any]] = []
    inserts: list[list[str]] = []
    term_bindings: list[dict[str, Any]] = []
    applied_items: list[dict[str, Any]] = []
    fact_ids: dict[str, str] = {}
    evidence_bindings: list[dict[str, Any]] = []
    candidate_by_id = {item["assertion_id"]: item for item in candidate["items"]}
    for delta_index, row in enumerate(rows):
        # The representative rows are selected by category rather than sort
        # order; bind each one back to its candidate item by assertion ID.
        assertion_id = row["assertion_id"]
        item = candidate_by_id[assertion_id]
        client_item_id = client_ids[assertion_id]
        subject = row["subject"]
        predicate = row["predicate"]
        obj = row["object"]
        if row["binding_category"] == "resource_output":
            obj = generated[assertion_id]
        elif row["binding_category"] == "relation_delta":
            obj = generated[assertion_id]
        quad = {
            "graph_role": "asserted_data",
            "source_graph_iri": GRAPH_ASSERTED_DATA,
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "object_kind": row["object_kind"],
            "object_datatype": row["object_datatype"],
            "object_language": row["object_language"],
        }
        quads.append(quad)
        raw_quad = [subject, predicate, obj, GRAPH_ASSERTED_DATA]
        inserts.append(raw_quad)
        quad_digest = canonical_digest(raw_quad)
        binding_kind = row["binding_category"]
        for position in ("subject", "predicate", "object"):
            if position == "object" and binding_kind in {"resource_output", "relation_delta", "literal_delta"}:
                position_kind = binding_kind
            else:
                position_kind = "vocabulary"
            term_bindings.append(
                {
                    "assertion_id": assertion_id,
                    "term_position": position,
                    "candidate_term": item[position],
                    "binding_kind": position_kind,
                    "client_item_id": client_item_id,
                    "batch_id": batch_id,
                    "applied_attempt_id": attempt_id,
                    "quad_digest": quad_digest,
                    "delta_index": delta_index,
                    "resource_output_iri": generated[assertion_id]
                    if position_kind == "resource_output"
                    else None,
                }
            )
        fact_id = hashlib.sha256(f"p2a-fact:{assertion_id}".encode("utf-8")).hexdigest()
        fact_ids[assertion_id] = fact_id
        citation = item["evidence_citations"][0]
        citation_hash = citation_digest(citation)
        identity = inline_evidence_identity(citation["document_name"], citation["excerpt_sha256"])
        group_hash = citation_group_digest([citation_hash])
        evidence_bindings.append(
            {
                "assertion_id": assertion_id,
                "citation_digest": citation_hash,
                "evidence_reference_id": f"p2a-evidence-reference-{delta_index + 1}",
                "client_item_id": client_item_id,
                "batch_id": batch_id,
                "fact_id": fact_id,
                "inline_evidence_identity": identity,
                "citation_group_digest": group_hash,
            }
        )
        applied_item = {"item_id": client_item_id, "status": "applied"}
        if binding_kind == "resource_output":
            applied_item["resource_outputs"] = {"resource_iri": generated[assertion_id]}
        applied_items.append(applied_item)

    quads = sorted(quads, key=canonical_bytes)
    term_bindings = sorted(term_bindings, key=canonical_bytes)
    evidence_bindings = sorted(evidence_bindings, key=canonical_bytes)
    batch_detail = _envelope(
        {
            "batch_id": batch_id,
            "items": [{"item_id": client_ids[row["assertion_id"]]} for row in rows],
            "attempts": [
                {
                    "attempt_id": attempt_id,
                    "mode": "apply_atomic",
                    "attempt_status": "applied",
                    "normalized_delta": {"inserts": inserts, "deletes": []},
                    "items": applied_items,
                }
            ],
        }
    )
    initial_context = _envelope(
        {
            "ontology": {"id": ONTOLOGY_ID},
            "resource_counts": {name: 0 for name in ("classes", "properties", "relation_types", "shapes", "entities", "relations", "facts")},
        }
    )
    final_context = _envelope(
        {
            "ontology": {"id": ONTOLOGY_ID},
            "resource_counts": {name: 1 for name in ("classes", "properties", "relation_types", "shapes", "entities", "relations", "facts")},
        }
    )
    workspace = _envelope(
        {
            "ontology_id": ONTOLOGY_ID,
            "state": "ready",
            "default_graph_set_id": GRAPH_SET_ID,
            "source_signature": SOURCE_SIGNATURE,
            "members": [
                {"role": "asserted_ontology", "owner_type": "ontology", "owner_id": ONTOLOGY_ID, "graph_iri": GRAPH_ASSERTED_ONTOLOGY},
                {"role": "asserted_data", "owner_type": "ontology", "owner_id": ONTOLOGY_ID, "graph_iri": GRAPH_ASSERTED_DATA},
                {"role": "shapes", "owner_type": "ontology", "owner_id": ONTOLOGY_ID, "graph_iri": GRAPH_SHAPES},
            ],
        }
    )
    fact_items = [{"fact_id": fact_ids[row["assertion_id"]], "id": fact_ids[row["assertion_id"]]} for row in rows]
    statements = {
        "response": _envelope(
            {
                "graph_set_id": GRAPH_SET_ID,
                "source_signature": SOURCE_SIGNATURE,
                "model_name": "statement-list",
                "include": "asserted",
                "items": fact_items,
            }
        )
    }
    lineage = []
    for row in rows:
        assertion_id = row["assertion_id"]
        fact_id = fact_ids[assertion_id]
        evidence_reference_id = next(item["evidence_reference_id"] for item in evidence_bindings if item["assertion_id"] == assertion_id)
        response = _envelope({"evidence_reference_id": evidence_reference_id})
        lineage.append(
            {
                "assertion_id": assertion_id,
                "fact_id": fact_id,
                "quad": next(quad for quad in quads if quad["subject"] == row["subject"] and quad["predicate"] == row["predicate"]),
                "target": {"target_kind": row["target_kind"], "target_id": fact_id if row["target_kind"] == "statement" else f"p2a-resource-{assertion_id}"},
                "response": response,
            }
        )
    lineage.sort(key=canonical_bytes)
    match_ids = sorted(fact_ids.values())
    pagination = {"schema_version": "semantic-context-pagination/v2", "streams": []}
    for stream_kind in ("matches", "context"):
        response = _envelope(
            {
                "truncated": False,
                "degraded": False,
                "blocking_warnings": [],
                "root_match_ids": match_ids,
                "items": [{"id": value, "fact_id": value} for value in match_ids],
            }
        )
        pagination["streams"].append(
            {
                "stream_kind": stream_kind,
                "pages": [
                    {
                        "stream_kind": stream_kind,
                        "request_fingerprint_sha256": _sha({"stream": stream_kind, "cursor": None}),
                        "page_index": 0,
                        "request_cursor": None,
                        "next_cursor": None,
                        "response_digest": canonical_digest(response),
                        "root_match_ids_digest": canonical_digest(match_ids),
                        "response": response,
                    }
                ],
            }
        )
    materialized_payload = {
        "candidate_digest": candidate["candidate_digest"],
        "term_bindings_digest": canonical_digest(term_bindings),
        "evidence_bindings_digest": canonical_digest(evidence_bindings),
        "materialized_quads": quads,
    }
    return {
        "mode": "create",
        "initial_modeling_context": initial_context,
        "final_modeling_context": final_context,
        "workspace_context": workspace,
        "batch_inventory": {
            "requested_limit": 10,
            "cursor": None,
            "status_filter": None,
            "response": _envelope({"batches": [{"batch_id": batch_id}], "next_cursor": None}),
        },
        "batch_details": [batch_detail],
        "entities_read": {"response": _envelope({"items": []})},
        "statements_read": statements,
        "candidate_required_assertions": candidate,
        "term_bindings": term_bindings,
        "materialized_quads": quads,
        "materialized_digest": canonical_digest(materialized_payload),
        "evidence_bindings": evidence_bindings,
        "statement_lineage": lineage,
        "pagination": pagination,
    }


def run_p2a_fixture(root: Path) -> dict[str, Any]:
    """Validate all 48 rows and verify a representative proof without a start."""
    try:
        matrix = load_matrix(root)
        rows = _choose_rows(matrix)
        candidate = _candidate(matrix, rows)
        proof = _proof(matrix, candidate, rows)
        result = verify_proof_v2(proof)
    except (MatrixArtifactError, ValueError, KeyError, StopIteration) as exc:
        raise P2AFixtureError(str(exc)) from exc
    proof_hash = canonical_digest(proof)
    return {
        "matrix_path": MATRIX_RELATIVE.as_posix(),
        "matrix_digest": matrix["matrix_digest"],
        "source_candidate_digest": matrix["source_candidate_digest"],
        "representative_assertion_ids": [row["assertion_id"] for row in rows],
        "representative_binding_categories": sorted({row["binding_category"] for row in rows}),
        "representative_target_kinds": sorted({row["target_kind"] for row in rows}),
        "proof_digest": proof_hash,
        "verifier": result,
        "semantic_start_written": False,
        "p2a_pass_written": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the no-semantic-start P2a representative fixture")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    print(json.dumps(run_p2a_fixture(args.root), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())


__all__ = ["P2AFixtureError", "run_p2a_fixture"]
