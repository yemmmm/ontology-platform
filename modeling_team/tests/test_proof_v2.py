from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from modeling_team.matrix_artifact import load_matrix
from modeling_team.p2a_batch_plan import ASSERTION_CLIENT_ITEM_IDS
from modeling_team.p2a_protocol_driver import _generated_candidate
from modeling_team.proof_v2 import (
    ProofV2Error,
    _fact_id_from_quad,
    canonical_bytes,
    verify_proof_v2,
)

from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_item_evidence_map,
    canonical_digest,
    citation_digest,
    compare_dry_run_group_projection,
    inline_evidence_identity,
    validate_candidate_item_evidence_map,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate() -> dict[str, object]:
    citation = {
        "document_name": "domain.md",
        "excerpt": "A term.",
        "source_artifact_sha256": _sha("artifact"),
        "source_locator": "domain.md#1",
        "excerpt_sha256": _sha("A term."),
        "owner_answer_id": None,
    }
    item = {
        "assertion_id": "assertion-1",
        "graph_role": "asserted_data",
        "subject": "subject",
        "predicate": "predicate",
        "object": "object",
        "object_kind": "iri",
        "object_datatype": None,
        "object_language": None,
        "evidence_citations": [citation],
    }
    semantic_digest = canonical_digest(
        {"schema_version": "candidate-required-assertions/v2", "statements": [item]}
    )
    binding = {
        "schema_version": "candidate-required-assertions/v2",
        "candidate_revision": "revision-1",
        "delivery_id": "delivery-1",
        "reply_chain": ["delivery-1"],
        "semantic_digest": semantic_digest,
    }
    return {**binding, "candidate_digest": canonical_digest(binding), "items": [item]}


def _exact_four_proof_fixture() -> dict[str, object]:
    """Pure reconstruction of the Round73 R0/R1/R2 and applied proof boundary."""
    root = Path(__file__).resolve().parents[2]
    candidate = _generated_candidate(load_matrix(root))[0]
    ontology_id = "ontology-p2a-proof-v2"
    batch_id = "batch-p2a-proof-v2"
    applied_attempt_id = "attempt-p2a-apply"
    entity_iri = "urn:p2a:generated:entity-1"
    asserted_data_graph = "urn:p2a:graph:asserted-data"
    by_assertion = {item["assertion_id"]: item for item in candidate["items"]}
    actual_terms = {
        "r23002-a008": (entity_iri, "urn:p2a:publicationStatus", "published", "literal", None),
        "r23002-a009": (entity_iri, "urn:p2a:hasOutput", "urn:p2a:output", "iri", None),
        "r23002-a004": ("urn:p2a:workflow", "urn:p2a:hasVersion", entity_iri, "iri", None),
        "r23002-a001": (
            entity_iri,
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "urn:p2a:FixtureResource",
            "iri",
            None,
        ),
    }
    delta_inserts: list[list[str]] = []
    materialized_by_assertion: dict[str, dict[str, object]] = {}
    delta_selectors: dict[str, tuple[int, str]] = {}
    fact_ids: dict[str, str] = {}
    for assertion_id in ASSERTION_CLIENT_ITEM_IDS:
        subject, predicate, obj, object_kind, datatype = actual_terms[assertion_id]
        delta = [subject, predicate, obj, asserted_data_graph]
        delta_index = len(delta_inserts)
        delta_inserts.append(delta)
        delta_selectors[assertion_id] = (delta_index, canonical_digest(delta))
        quad = {
            "graph_role": "asserted_data",
            "source_graph_iri": asserted_data_graph,
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "object_kind": object_kind,
            "object_datatype": datatype,
            "object_language": None,
        }
        materialized_by_assertion[assertion_id] = quad
        fact_ids[assertion_id] = _fact_id_from_quad(
            (subject, predicate, obj, asserted_data_graph), object_kind, datatype, None
        )

    formal_items = [
        {"item_id": client_item_id, "client_item_id": client_item_id}
        for client_item_id in ASSERTION_CLIENT_ITEM_IDS.values()
    ]
    dry_run_attempt = {
        "attempt_id": "attempt-p2a-dry-run",
        "mode": "dry_run",
        "attempt_status": "validated",
        "items": [],
        "normalized_delta": {"inserts": delta_inserts},
    }
    applied_results = []
    for assertion_id, client_item_id in ASSERTION_CLIENT_ITEM_IDS.items():
        result: dict[str, object] = {"item_id": client_item_id, "status": "applied"}
        if assertion_id == "r23002-a008":
            result["resource_outputs"] = {"resource_iri": entity_iri}
        applied_results.append(result)
    applied_attempt = {
        "attempt_id": applied_attempt_id,
        "mode": "apply_atomic",
        "attempt_status": "applied",
        "items": applied_results,
        "normalized_delta": {"inserts": delta_inserts},
    }
    r0 = {"batch_id": batch_id, "items": formal_items, "attempts": [dry_run_attempt]}
    r1 = json.loads(json.dumps(r0))
    r2 = json.loads(json.dumps(r1))
    applied_detail = {
        "batch_id": batch_id,
        "items": formal_items,
        "attempts": [dry_run_attempt, applied_attempt],
    }

    term_bindings = []
    for assertion_id, client_item_id in ASSERTION_CLIENT_ITEM_IDS.items():
        item = by_assertion[assertion_id]
        delta_index, quad_digest = delta_selectors[assertion_id]
        for position in ("subject", "predicate", "object"):
            kind = "vocabulary"
            output_iri = None
            binding_client_item_id = client_item_id
            if item[position] == "p2a:generated-subject":
                kind = "resource_output"
                binding_client_item_id = ASSERTION_CLIENT_ITEM_IDS["r23002-a008"]
                output_iri = entity_iri
            elif assertion_id == "r23002-a008" and position == "object":
                kind = "literal_delta"
            elif assertion_id == "r23002-a009" and position == "object":
                kind = "relation_delta"
            term_bindings.append(
                {
                    "assertion_id": assertion_id,
                    "term_position": position,
                    "candidate_term": item[position],
                    "binding_kind": kind,
                    "client_item_id": binding_client_item_id,
                    "batch_id": batch_id,
                    "applied_attempt_id": applied_attempt_id,
                    "quad_digest": quad_digest,
                    "delta_index": delta_index,
                    "resource_output_iri": output_iri,
                }
            )
    term_bindings.sort(key=canonical_bytes)

    evidence_bindings = []
    lineage = []
    for assertion_id, client_item_id in ASSERTION_CLIENT_ITEM_IDS.items():
        citation = by_assertion[assertion_id]["evidence_citations"][0]
        citation_hash = citation_digest(citation)
        identity = inline_evidence_identity(citation["document_name"], citation["excerpt_sha256"])
        reference_id = f"evidence-reference-{assertion_id}"
        evidence_bindings.append(
            {
                "assertion_id": assertion_id,
                "citation_digest": citation_hash,
                "evidence_reference_id": reference_id,
                "client_item_id": client_item_id,
                "batch_id": batch_id,
                "fact_id": fact_ids[assertion_id],
                "inline_evidence_identity": identity,
                "citation_group_digest": canonical_digest([citation_hash]),
            }
        )
        quad = materialized_by_assertion[assertion_id]
        lineage.append(
            {
                "assertion_id": assertion_id,
                "fact_id": fact_ids[assertion_id],
                "quad": quad,
                "target": {"target_kind": "statement", "target_id": fact_ids[assertion_id]},
                "response": {"ok": True, "data": {"evidence_reference_id": reference_id}},
            }
        )
    evidence_bindings.sort(key=canonical_bytes)
    lineage.sort(key=canonical_bytes)
    materialized_quads = sorted(materialized_by_assertion.values(), key=canonical_bytes)
    materialized_digest = canonical_digest(
        {
            "candidate_digest": candidate["candidate_digest"],
            "term_bindings_digest": canonical_digest(term_bindings),
            "evidence_bindings_digest": canonical_digest(evidence_bindings),
            "materialized_quads": materialized_quads,
        }
    )

    ordered_fact_ids = [fact_ids[assertion_id] for assertion_id in ASSERTION_CLIENT_ITEM_IDS]

    def pagination_stream(kind: str) -> dict[str, object]:
        cursor = f"cursor-{kind}-episode-2"
        pages = []
        for page_index, roots in enumerate((ordered_fact_ids[:2], ordered_fact_ids[2:])):
            response = {
                "ok": True,
                "data": {
                    "truncated": False,
                    "degraded": False,
                    "blocking_warnings": [],
                    "retrieval_episode": "fallback" if page_index == 0 else "complete",
                    "root_match_ids": roots,
                    "items": [{"fact_id": fact_id, "state": "retained"} for fact_id in roots],
                },
            }
            pages.append(
                {
                    "stream_kind": kind,
                    "request_fingerprint_sha256": _sha(f"{kind}-query"),
                    "page_index": page_index,
                    "request_cursor": None if page_index == 0 else cursor,
                    "next_cursor": cursor if page_index == 0 else None,
                    "response_digest": canonical_digest(response),
                    "root_match_ids_digest": canonical_digest(sorted(set(roots))),
                    "response": response,
                }
            )
        return {"stream_kind": kind, "pages": pages}

    counts = {name: 0 for name in ("classes", "properties", "relation_types", "shapes", "entities", "relations", "facts")}
    final_counts = dict(counts)
    final_counts.update({"entities": 1, "relations": 3, "facts": 4})
    workspace_data = {
        "ontology_id": ontology_id,
        "state": "ready",
        "default_graph_set_id": "graph-set-p2a-proof-v2",
        "source_signature": "source-signature-p2a-proof-v2",
        "members": [
            {"role": "asserted_ontology", "owner_type": "ontology", "owner_id": ontology_id, "graph_iri": "urn:p2a:graph:asserted-ontology"},
            {"role": "asserted_data", "owner_type": "ontology", "owner_id": ontology_id, "graph_iri": asserted_data_graph},
            {"role": "shapes", "owner_type": "ontology", "owner_id": ontology_id, "graph_iri": "urn:p2a:graph:shapes"},
        ],
    }
    proof = {
        "mode": "create",
        "initial_modeling_context": {"ok": True, "data": {"ontology": {"id": ontology_id}, "resource_counts": counts}},
        "final_modeling_context": {"ok": True, "data": {"ontology": {"id": ontology_id}, "resource_counts": final_counts}},
        "workspace_context": {"ok": True, "data": workspace_data},
        "batch_inventory": {
            "requested_limit": 2,
            "cursor": None,
            "status_filter": None,
            "response": {"ok": True, "data": {"batches": [{"batch_id": batch_id}], "next_cursor": None}},
        },
        "batch_details": [{"ok": True, "data": applied_detail}],
        "entities_read": {"ok": True, "data": {"items": [{"iri": entity_iri}]}},
        "statements_read": {
            "response": {
                "ok": True,
                "data": {
                    "graph_set_id": workspace_data["default_graph_set_id"],
                    "source_signature": workspace_data["source_signature"],
                    "model_name": "statement-list",
                    "include": "asserted",
                    "items": [{"fact_id": fact_id} for fact_id in ordered_fact_ids],
                },
            }
        },
        "candidate_required_assertions": candidate,
        "term_bindings": term_bindings,
        "materialized_quads": materialized_quads,
        "materialized_digest": materialized_digest,
        "evidence_bindings": evidence_bindings,
        "statement_lineage": lineage,
        "pagination": {
            "schema_version": "proof-v2-pagination/v1",
            "streams": [pagination_stream("matches"), pagination_stream("context")],
        },
    }
    return {"r0": r0, "r1": r1, "r2": r2, "proof": proof}


class ProofV2MechanicsTests(unittest.TestCase):
    def test_exact_four_p2a_proof_accepts_receipt_bound_resource_iri_normalization(self) -> None:
        fixture = _exact_four_proof_fixture()
        self.assertEqual(fixture["r0"], fixture["r1"])
        self.assertEqual(fixture["r1"], fixture["r2"])
        result = verify_proof_v2(fixture["proof"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["lineage_count"], 4)

    def test_exact_four_p2a_proof_rejects_wrong_materialized_iri(self) -> None:
        proof = _exact_four_proof_fixture()["proof"]
        resource_quad = next(
            quad for quad in proof["materialized_quads"] if quad["predicate"] == "urn:p2a:hasOutput"
        )
        resource_quad["object"] = "urn:p2a:wrong-output"
        with self.assertRaisesRegex(
            ProofV2Error, "materialized quad does not match receipt-bound candidate terms"
        ):
            verify_proof_v2(proof)

    def test_exact_four_p2a_proof_rejects_literal_as_resource(self) -> None:
        proof = _exact_four_proof_fixture()["proof"]
        literal_quad = next(
            quad
            for quad in proof["materialized_quads"]
            if quad["predicate"] == "urn:p2a:publicationStatus"
        )
        literal_quad["object_kind"] = "resource"
        with self.assertRaisesRegex(
            ProofV2Error, "materialized quad does not match receipt-bound candidate terms"
        ):
            verify_proof_v2(proof)

    def test_exact_four_p2a_proof_requires_terminal_null_cursor(self) -> None:
        proof = _exact_four_proof_fixture()["proof"]
        proof["pagination"]["streams"][0]["pages"][-1]["next_cursor"] = "cursor-unconsumed"
        with self.assertRaisesRegex(ProofV2Error, "final next_cursor must be null"):
            verify_proof_v2(proof)

    def test_exact_four_p2a_proof_rejects_unconsumed_cursor(self) -> None:
        proof = _exact_four_proof_fixture()["proof"]
        pages = proof["pagination"]["streams"][1]["pages"]
        pages.pop()
        pages[0]["next_cursor"] = "cursor-context-unconsumed"
        with self.assertRaisesRegex(ProofV2Error, "final next_cursor must be null"):
            verify_proof_v2(proof)

    def test_group_map_keeps_distinct_citations_with_one_inline_identity(self) -> None:
        candidate = _candidate()
        item = candidate["items"][0]
        assert isinstance(item, dict)
        second = dict(item["evidence_citations"][0])
        second["source_locator"] = "domain.md#2"
        item["evidence_citations"] = sorted(
            [item["evidence_citations"][0], second], key=lambda value: canonical_digest(value)
        )
        # Recompute the candidate semantic/candidate digests after adding the
        # citation, as a real Modeling delivery would do.
        semantic = canonical_digest(
            {"schema_version": "candidate-required-assertions/v2", "statements": [item]}
        )
        candidate["semantic_digest"] = semantic
        binding = {
            "schema_version": candidate["schema_version"],
            "candidate_revision": candidate["candidate_revision"],
            "delivery_id": candidate["delivery_id"],
            "reply_chain": candidate["reply_chain"],
            "semantic_digest": semantic,
        }
        candidate["candidate_digest"] = canonical_digest(binding)
        evidence_map = build_candidate_item_evidence_map(candidate, {"assertion-1": "item-1"}, run_id="run-1")
        self.assertEqual(len(evidence_map["rows"]), 2)
        self.assertEqual(
            {row["inline_evidence_identity"] for row in evidence_map["rows"]},
            {inline_evidence_identity("domain.md", _sha("A term."))},
        )
        self.assertEqual(validate_candidate_item_evidence_map(candidate, evidence_map)["map_digest"], evidence_map["map_digest"])

    def test_group_projection_is_one_row_per_group_and_rejects_missing_or_extra(self) -> None:
        candidate = _candidate()
        evidence_map = build_candidate_item_evidence_map(candidate, {"assertion-1": "item-1"}, run_id="run-1")
        identity = evidence_map["rows"][0]["inline_evidence_identity"]
        row = {"client_item_id": "item-1", "inline_evidence_identity": identity, "dedupe_identity": "reference-1"}
        self.assertEqual(compare_dry_run_group_projection(evidence_map, [row]), [row])
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "extra group"):
            compare_dry_run_group_projection(
                evidence_map,
                [row, {"client_item_id": "item-2", "inline_evidence_identity": identity, "dedupe_identity": "reference-2"}],
            )
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "missing a group"):
            compare_dry_run_group_projection(evidence_map, [])

    def test_map_digest_and_citation_digest_are_canonical(self) -> None:
        candidate = _candidate()
        evidence_map = build_candidate_item_evidence_map(candidate, {"assertion-1": "item-1"}, run_id="run-1")
        self.assertEqual(evidence_map["rows"][0]["citation_digest"], citation_digest(candidate["items"][0]["evidence_citations"][0]))
        broken = dict(evidence_map)
        broken["map_digest"] = _sha("wrong")
        with self.assertRaisesRegex(ProtocolRetrievalFallbackError, "map_digest drifts"):
            validate_candidate_item_evidence_map(candidate, broken)


if __name__ == "__main__":
    unittest.main()
