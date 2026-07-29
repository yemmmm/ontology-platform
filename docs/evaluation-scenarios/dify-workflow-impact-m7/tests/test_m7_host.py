from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from m7_contract import CONTRACT_VERSION, SEAL_TOOL, sealed_envelope_hash  # noqa: E402
from m7_host import (  # noqa: E402
    HostError,
    _require_scope_matches,
    _apply_outputs_equal,
    _probe_public_routes,
    _role_map_from_dry_run,
    candidate_hash,
    compile_frozen_assertion_queries,
    stage_run_manifest,
    validate_semantic_package,
)


SCOPE = {"project_id": "project", "ontology_id": "ontology", "build_session_id": "session"}
PUBLIC = {
    "base-class": {"resource_id": "class-base", "resource_iri": "https://m7.test/base-class"},
    "base-entity": {"resource_id": "entity-base", "resource_iri": "https://m7.test/base-entity"},
}


def item(item_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"client_item_id": item_id, "command_kind": kind, "payload": payload, "depends_on": [], "evidence_reference_ids": [], "evidence": [], "rationale": None, "competency_question_ids": []}


def raw_package() -> dict[str, Any]:
    principal = {"items": [
        item("record-class", "create_class", {"name": "Record"}),
        item("link-type", "create_relation_type", {"name": "links", "source_class_id": "class-base", "target_class_id": {"item_ref": {"client_item_id": "record-class", "output": "resource_id"}}}),
        item("record", "create_entity", {"class_iri_or_legacy_id": {"item_ref": {"client_item_id": "record-class", "output": "resource_iri"}}, "label": "R"}),
        item("record-link", "create_relation", {"source_entity_iri": "https://m7.test/base-entity", "relation_type_iri": {"item_ref": {"client_item_id": "link-type", "output": "resource_iri"}}, "target_entity_iri": {"item_ref": {"client_item_id": "record", "output": "resource_iri"}}}),
    ]}
    return {
        "principal": principal,
        "invalid_candidate": {"items": [item("bad", "create_shape", {"target_class_id": "class-base", "constraints": []})]},
        "resource_roles": [
            {"role": "base", "semantic_key": "base", "source": {"public_role": "base-entity"}},
            {"role": "record", "semantic_key": "record", "source": {"client_item_id": "record"}},
        ],
        "edge_assertions": [
            {"id": "record-link", "subject_role": "base", "predicate": {"iri": "https://example.test/p"}, "object": {"role": "record"}},
            {"id": "record-label", "subject_role": "record", "predicate": {"iri": "https://example.test/label"}, "object": {"literal": {"value": "hello", "language": "en"}}},
        ],
        "closed_snapshot_absence_assertions": [],
        "cq_claims": [{"id": "cq-one", "kind": "connected_typed_path", "assertion_ids": ["record-link", "record-label"], "bindings": {"paths": [["base", "record"]]}}],
    }


def sealed() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = stage_run_manifest(SCOPE, PUBLIC, "input", "base")
    raw = raw_package()
    package = {"schema_version": 1, "contract_version": CONTRACT_VERSION, "input_manifest_sha256": "input", "base_manifest_sha256": "base", "public_role_bindings": PUBLIC, **raw}
    package["principal_candidate_sha256"] = candidate_hash(package["principal"])
    package["invalid_candidate_sha256"] = candidate_hash(package["invalid_candidate"])
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    return package, manifest


def dry() -> dict[str, Any]:
    return {"items": [
        {"client_item_id": "record-class", "resource_outputs": {"resource_id": "class-r", "resource_iri": "https://m7.test/record-class"}},
        {"client_item_id": "link-type", "resource_outputs": {"resource_id": "link-r", "resource_iri": "https://m7.test/link-type"}},
        {"client_item_id": "record", "resource_outputs": {"resource_id": "entity-r", "resource_iri": "https://m7.test/record"}},
        {"client_item_id": "record-link", "resource_outputs": {}},
    ], "normalized_delta": {"triples": [{"subject": "https://m7.test/base-entity", "predicate": "https://example.test/p", "object": "https://m7.test/record"}, {"subject": "https://m7.test/record", "predicate": "https://example.test/label", "object": "hello"}]}}


def test_v3_package_resolves_output_roles_compiles_literals_and_rejects_relation_role() -> None:
    package, manifest = sealed()
    assert validate_semantic_package(package, PUBLIC, manifest)
    roles = _role_map_from_dry_run(package, PUBLIC, dry())
    queries = compile_frozen_assertion_queries(package, roles, dry()["normalized_delta"])
    assert '"hello"@en' in queries["record-label"] and "https://example.test/p" in queries["record-link"]
    bad = deepcopy(package)
    bad["resource_roles"].append({"role": "relation", "semantic_key": "relation", "source": {"client_item_id": "record-link"}})
    bad["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(bad)}
    with pytest.raises(HostError, match="output-capable"):
        validate_semantic_package(bad, PUBLIC, manifest)


def test_exact_executable_sealer_emits_v3_envelope_without_hidden_contracts(tmp_path: Path) -> None:
    visible = tmp_path / "agent-visible"
    shutil.copytree(SCENARIO_ROOT / "agent-input", visible)
    raw = raw_package()
    raw["principal"]["items"][1]["depends_on"] = ["record-class"]
    raw["principal"]["items"][2]["depends_on"] = ["record-class"]
    raw["principal"]["items"][3]["depends_on"] = ["link-type", "record"]
    raw["principal"]["items"][0]["evidence"] = [{"document_name": "visible-source", "excerpt": "inline source excerpt"}]
    (visible / "run-manifest.json").write_text(json.dumps(stage_run_manifest(SCOPE, PUBLIC, "input", "base")), encoding="utf-8")
    (visible / "semantic-package.json").write_text(json.dumps(raw), encoding="utf-8")
    completed = subprocess.run(["./seal_semantic_package.py", "--agent-visible", "."], cwd=visible, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    value = json.loads((visible / "semantic-package.json").read_text(encoding="utf-8"))
    assert value["contract_version"] == CONTRACT_VERSION and "query" not in value
    assert value["principal"]["items"][0]["evidence"] == raw["principal"]["items"][0]["evidence"] and value["cq_claims"]


@pytest.mark.parametrize("candidate", ["principal", "invalid_candidate"])
def test_nonempty_governed_refs_fail_in_sealer_and_host_before_dry_run(tmp_path: Path, candidate: str) -> None:
    visible = tmp_path / "agent-visible"
    shutil.copytree(SCENARIO_ROOT / "agent-input", visible)
    raw = raw_package()
    raw["principal"]["items"][1]["depends_on"] = ["record-class"]
    raw["principal"]["items"][2]["depends_on"] = ["record-class"]
    raw["principal"]["items"][3]["depends_on"] = ["link-type", "record"]
    raw[candidate]["items"][0]["evidence_reference_ids"] = ["attempt3-governed-evidence"]
    (visible / "run-manifest.json").write_text(json.dumps(stage_run_manifest(SCOPE, PUBLIC, "input", "base")), encoding="utf-8")
    (visible / "semantic-package.json").write_text(json.dumps(raw), encoding="utf-8")
    completed = subprocess.run(["./seal_semantic_package.py", "--agent-visible", "."], cwd=visible, check=False, capture_output=True, text=True)
    assert completed.returncode != 0 and "empty Evidence" in completed.stderr

    package, manifest = sealed()
    package[candidate]["items"][0]["competency_question_ids"] = ["attempt3-governed-cq"]
    package["principal_candidate_sha256" if candidate == "principal" else "invalid_candidate_sha256"] = candidate_hash(package[candidate])
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    with pytest.raises(HostError, match="empty Evidence"):
        validate_semantic_package(package, PUBLIC, manifest)


@pytest.mark.parametrize("literal", [{"value": "plain"}, {"value": "12", "datatype": "https://www.w3.org/2001/XMLSchema#integer"}, {"value": "bonjour", "language": "fr-CA"}])
def test_literal_forms_are_accepted(literal: dict[str, str]) -> None:
    package, manifest = sealed()
    package["edge_assertions"][1]["object"] = {"literal": literal}
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    validate_semantic_package(package, PUBLIC, manifest)


def test_unresolved_duplicate_and_absent_predicate_fail_closed() -> None:
    package, manifest = sealed()
    package["resource_roles"].append({"role": "duplicate", "semantic_key": "duplicate", "source": {"client_item_id": "record"}})
    package["principal_candidate_sha256"] = candidate_hash(package["principal"])
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    validate_semantic_package(package, PUBLIC, manifest)
    with pytest.raises(HostError, match="duplicate IRIs"):
        _role_map_from_dry_run(package, PUBLIC, dry())
    package, manifest = sealed()
    package["edge_assertions"][0]["predicate"] = {"iri": "https://example.test/absent"}
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    validate_semantic_package(package, PUBLIC, manifest)
    with pytest.raises(HostError, match="absent from"):
        compile_frozen_assertion_queries(package, _role_map_from_dry_run(package, PUBLIC, dry()), dry()["normalized_delta"])


def test_v1_v2_unresolved_and_swapped_envelopes_fail_before_dry_run() -> None:
    package, manifest = sealed()
    package["contract_version"] = "m7-contract-v2"
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    with pytest.raises(HostError, match="contract version drift"):
        validate_semantic_package(package, PUBLIC, manifest)
    package, manifest = sealed()
    package["resource_roles"][1] = {"role": "record", "semantic_key": "record", "source": {"client_item_id": "missing"}}
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    with pytest.raises(HostError, match="output-capable"):
        validate_semantic_package(package, PUBLIC, manifest)
    package, manifest = sealed()
    package["principal"]["items"][3]["payload"]["relation_type_iri"]["item_ref"]["output"] = "resource_id"
    package["principal_candidate_sha256"] = candidate_hash(package["principal"])
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    with pytest.raises(HostError, match="swapped representation"):
        validate_semantic_package(package, PUBLIC, manifest)


def test_claims_cannot_use_absence_or_raw_query_and_apply_outputs_must_match() -> None:
    package, manifest = sealed()
    package["closed_snapshot_absence_assertions"] = [{"id": "absent", "subject_role": "record", "predicate": {"iri": "https://example.test/p"}, "object": {"role": "base"}}]
    package["cq_claims"] = [{"id": "cq-one", "kind": "connected_typed_path", "assertion_ids": ["absent"], "bindings": {"paths": [["base", "record"]]}}]
    package["seal"] = {"tool": SEAL_TOOL, "envelope_sha256": sealed_envelope_hash(package)}
    with pytest.raises(HostError, match="positive assertions"):
        validate_semantic_package(package, PUBLIC, manifest)
    response = dry()
    changed = deepcopy(response)
    changed["items"][1]["resource_outputs"]["resource_iri"] = "https://m7.test/drift"
    with pytest.raises(HostError, match="outputs drifted"):
        _apply_outputs_equal(response, changed)


class RouteTransport:
    """Exact current REST paths/envelopes only; old top-level routes deliberately fail."""
    def __init__(self, *, stale: bool = False, truncated: bool = False, partial: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.stale, self.truncated, self.partial = stale, truncated, partial
    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        graph_set = {"id": "graph-set", "status": "active", "source_signature": "sig", "members": []}
        if (method, path) == ("GET", "/api/ontologies/ontology/modeling-context"):
            return {"status": 200, "body": {"workspace": {"workspace_version": "1"}}}
        if (method, path) == ("GET", "/api/ontologies/ontology/workspace-context"):
            return {
                "status": 200,
                "body": {
                    "ontology_id": "ontology",
                    "state": "ready",
                    "default_graph_set_id": "graph-set",
                    "source_signature": "sig",
                    "members": [],
                    "issues": [],
                },
            }
        if (method, path) == ("GET", "/api/semantic/graph-sets/graph-set"):
            return {"status": 200, "body": graph_set}
        if method == "POST" and path.endswith("/reasoning-runs"):
            assert body == {"tasks": ["consistency"], "persist_result_graph": False}
            return {"status": 200, "body": {"run_id": "reasoning", "status": "completed", "consistent": True}}
        if (method, path) == ("GET", "/api/semantic/reasoning-runs/reasoning"):
            return {"status": 200, "body": {"run_id": "reasoning", "status": "completed", "consistent": True, "graph_set_id": "graph-set", "source_signature": "sig"}}
        if method == "POST" and path.endswith("/validation-runs"):
            assert body == {"persist_report_graph": False}
            return {"status": 200, "body": {"run_id": "validation", "status": "completed", "conforms": True}}
        if (method, path) == ("GET", "/api/semantic/validation-runs/validation"):
            return {"status": 200, "body": {"run_id": "validation", "status": "completed", "conforms": True, "graph_set_id": "graph-set", "source_signature": "sig"}}
        if (method, path) == ("POST", "/api/semantic/sparql:query"):
            assert body and body["scope_mode"] == "ontologies" and body["ontology_ids"] == ["ontology"]
            warnings = [{"code": "source_signature_stale"}] if self.stale else []
            scope = {"status": "partial" if self.partial else "complete", "ontologies": [{"ontology_id": "ontology", "workspace_version": "1", "source_signature": "sig", "derived_state": {}}], "excluded_ontologies": [{"ontology_id": "other"}] if self.partial else []}
            return {"status": 200, "body": {"result": {"boolean": True}, "scope": scope, "truncated": self.truncated, "warnings": warnings}}
        raise AssertionError(f"unexpected route {method} {path}")


def test_pre_agent_probe_requires_real_graph_set_detail_and_fails_stale_or_truncated() -> None:
    transport = RouteTransport()
    result = _probe_public_routes(transport, SCOPE)
    assert result["scope"] == {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "graph-set"}
    assert transport.calls[1][1] == "/api/ontologies/ontology/workspace-context"
    assert all(path.startswith("/api/semantic/") for _method, path, _body in transport.calls[2:])
    for bad, message in ((RouteTransport(stale=True), "truncated or stale"), (RouteTransport(truncated=True), "truncated or stale"), (RouteTransport(partial=True), "incomplete")):
        with pytest.raises(HostError, match=message):
            _probe_public_routes(bad, SCOPE)


def test_workspace_and_source_signature_drift_fail_closed() -> None:
    expected = {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "graph-set"}
    with pytest.raises(HostError, match="workspace_version drift"):
        _require_scope_matches({**expected, "workspace_version": "2"}, expected, "ontology")
    with pytest.raises(HostError, match="source_signature drift"):
        _require_scope_matches({**expected, "source_signature": "other"}, expected, "ontology")
