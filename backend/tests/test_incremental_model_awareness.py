"""R4.3-028 controlled integration: old reads, explicit placement and Mapping readiness.

Uses real compiler/Batch services and RDF storage; no provider or semantic run.
"""

# ruff: noqa: F811 - pytest registers the imported shared fixture.

import pytest
from fastapi.encoders import jsonable_encoder
from rdflib import URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

from app.api.schemas import OntologyUpdate
from app.api import ontologies
from app.repositories.models import OntologyModel
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_command_compiler import compile_command
from app.services.semantic_export import namespace_from_settings, SemanticNamespace
from modeling_team.platform_scope import PlatformScope
from modeling_team.tests.test_r30008b_runner_wiring import _socket_request, _write_json
from backend.tests.test_direct_modeling_team_integration import direct_run, call  # noqa: F401
from backend.tests.test_direct_modeling_team_edges import _change


def _request(*changes):
    return {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": None,
        "changes": list(changes),
    }


def _submit(run, request, placement_ref):
    response = _socket_request(
        run.endpoint.socket_path,
        run.endpoint.token,
        "tools/call",
        name="modeling_submit_model_changes",
        arguments={"modeling_id": "modeling", "request": request, "placement_ref": placement_ref},
    )
    assert "result" in response, response
    return response["result"]["structuredContent"]["data"]


def _seed_class(run, monkeypatch, ontology="direct-o", identifier="old/object α"):
    monkeypatch.setenv("SEMANTIC_BASE_IRI", run.settings.semantic_base_iri)
    command = compile_command(
        "create_class",
        {"ontology_id": ontology, "class_id": identifier, "name": "Existing business object"},
        run.settings,
    )
    run.store.apply_dataset_delta(command.delta)
    run.store.writes.clear()
    return str(namespace_from_settings(run.settings).resource("class", identifier))


def _read_class(run, iri, ontology="direct-o", model="query_semantic_context"):
    if model == "query_semantic_context":
        read = run.runner._direct_platform_read(
            model,
            {
                "project_id": "direct-p",
                "scope_mode": "ontologies",
                "ontology_ids": [ontology],
                "query": iri,
                "context_detail": "full",
            },
        )
        rows, pointer = read["data"]["primary_matches"], "/structuredContent/data/primary_matches"
    else:
        read = run.runner._direct_platform_read(
            model, {"ontology_id": ontology, "model_name": "classes", "field_set": "full"}
        )
        rows, pointer = read["data"]["items"], "/structuredContent/data/items"
    index = next(i for i, row in enumerate(rows) if row.get("iri", row.get("id")) == iri)
    return {"artifact_ref": read["platform_ref"]["artifact_path"], "path": f"{pointer}/{index}"}


def _multi(run):
    for oid in ("direct-o2", "direct-o3"):
        obj = OntologyModel(id=oid, project_id="direct-p", name=oid)
        run.db.add(obj)
        run.db.flush()
        OntologyWorkspaceService(run.db, run.settings).ensure(obj)
    run.db.commit()
    lifecycle = run.runner.scope.request
    metadata_calls = []

    def request(method, path, body, key):
        if path == "/api/projects/direct-p/ontologies":
            return 200, [{"id": oid} for oid in ("direct-o", "direct-o2", "direct-o3")]
        if path.startswith("/api/ontologies/"):
            metadata_calls.append((method, path, body))
            oid = path.split("/")[-1]
            if method == "GET":
                return 200, jsonable_encoder(ontologies.get_ontology(oid, session=run.db))
            if method == "PATCH":
                return 200, jsonable_encoder(
                    ontologies.update_ontology(oid, OntologyUpdate(**body), session=run.db)
                )
        return lifecycle(method, path, body, key)

    scope = PlatformScope(
        "unused",
        run.runner.run.run_id,
        lambda: ("admin", "aid"),
        lambda _: True,
        request=request,
        project_id="direct-p",
        ontology_id="direct-o",
        ontology_ids=["direct-o", "direct-o2"],
        ontology_plan_ids=["direct-o", "direct-o2"],
        protocol_key="synthetic-key",
        admin_key="admin",
        mapping_reference_direction="from_slice_depends_on_to_slice",
    )
    run.runner.scope = scope
    decision = {
        "ontology_plan": [
            {"ontology_id": "direct-o", "slice_ids": ["a"]},
            {"ontology_id": "direct-o2", "slice_ids": ["b"]},
        ]
    }
    _write_json(run.staged.run_root / "scenario-map/topology-decision.json", decision)
    _write_json(
        run.staged.run_root / "scenario-map/scenario-map.json", {"cross_slice_dependencies": []}
    )
    run.runner._retain_direct_topology(decision)
    return scope, run.runner._direct_placements(), metadata_calls


@pytest.mark.parametrize("identifier", ["plain-id", "old/object α", "%2F", "a?b#c"])
def test_canonical_native_identifier_roundtrip(identifier):
    ns = SemanticNamespace("https://native.test/resource/", "https://native.test/graph/")
    iri = str(ns.resource("class", identifier))
    assert ns.resource_identifier("class", iri) == identifier
    assert str(ns.resource("class", ns.resource_identifier("class", iri))) == iri


@pytest.mark.parametrize(
    "iri",
    [
        "https://other.test/class/x",
        "https://native.test/resource/class/",
        "https://native.test/resource/class/a/b",
        "https://native.test/resource/class/%ff",
        "https://native.test/resource/class/%61",
        "https://native.test/resource/class/a%2fb",
        "https://native.test/resource/class/x?y",
        "https://native.test/resource/property/x",
    ],
)
def test_noncanonical_iri_has_no_native_identity(iri):
    ns = SemanticNamespace("https://native.test/resource", "https://native.test/graph")
    assert ns.resource_identifier("class", iri) is None


@pytest.mark.parametrize("model", ["query_semantic_context", "get_ontology_read_model"])
def test_old_class_without_receipt_connects_real_native_endpoints(direct_run, monkeypatch, model):  # noqa: F811
    run = direct_run
    old_iri = _seed_class(run, monkeypatch)
    created = call(
        run, _request(_change("new-plan", "create", "class", fields={"name": "New plan"}))
    )
    assert created["status"] == "completed", created
    new_ref = created["batches"][0]["resource_bindings"][0]["existing_resource_ref"]
    old_ref = _read_class(run, old_iri, model=model)
    request = _request(
        _change(
            "plan-target",
            "create",
            "relation_type",
            fields={
                "name": "targets",
                "source_class_id": {"existing_resource_ref": new_ref},
                "target_class_id": {"existing_resource_ref": old_ref},
            },
        )
    )
    result = call(run, request)
    assert result["status"] == "completed", result
    assert run.calls[-1]["items"][0]["payload"]["target_class_id"] == "old/object α"
    relation_iri = result["batches"][0]["resource_bindings"][0]["resource_iri"]
    assert list(run.store.dataset.quads((URIRef(relation_iri), RDFS.range, URIRef(old_iri), None)))
    governed = run.read(
        "query_semantic_context",
        {
            "project_id": "direct-p",
            "scope_mode": "ontologies",
            "ontology_ids": ["direct-o"],
            "query": relation_iri,
            "context_detail": "full",
        },
    )
    assert old_iri in str(governed)
    assert len(run.calls) == 2  # seed was not a run submission or receipt


def test_stale_old_read_is_repairable_in_same_goal(direct_run, monkeypatch):  # noqa: F811
    run = direct_run
    old = _seed_class(run, monkeypatch)
    stale = _read_class(run, old)
    created = call(run, _request(_change("plan", "create", "class", fields={"name": "Plan"})))
    new = created["batches"][0]["resource_bindings"][0]["existing_resource_ref"]
    request = _request(
        _change(
            "targets",
            "create",
            "relation_type",
            fields={
                "name": "targets",
                "source_class_id": {"existing_resource_ref": new},
                "target_class_id": {"existing_resource_ref": stale},
            },
        )
    )
    rejected = call(run, request)
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"][0]["code"] == "resource_revision_conflict"
    request["changes"][0]["fields"]["target_class_id"]["existing_resource_ref"] = _read_class(
        run, old
    )
    assert call(run, request)["status"] == "completed"
    assert len(run.calls) == 2


def test_explicit_placement_selects_two_real_ontologies_without_wrong_dedup(
    direct_run, monkeypatch
):  # noqa: F811
    run = direct_run
    _seed_class(run, monkeypatch)
    _, places, _ = _multi(run)
    req = _request(_change("new-kind", "create", "class", fields={"name": "New kind"}))
    rejected = call(run, req)
    assert rejected["status"] == "not_written" and not run.calls
    assert rejected["errors"][0]["code"] == "scope_binding_required"
    first = _submit(run, req, places[0]["placement_ref"])
    second = _submit(run, req, places[1]["placement_ref"])
    assert first["status"] == second["status"] == "completed", (first, second)
    assert first["submission_digest"] != second["submission_digest"]
    assert [batch["ontology_id"] for batch in run.calls] == ["direct-o", "direct-o2"]
    assert _submit(run, req, places[0]["placement_ref"])["status"] == "completed"
    assert len(run.calls) == 2
    ref = dict(places[0]["placement_ref"], artifact_ref="scenario-map/topology-decision.json")
    invalid = _submit(run, req, ref)
    assert invalid["status"] == "not_written" and invalid["errors"][0]["path"] == "/placement_ref"
    run.runner.scope.ontology_plan_ids.reverse()
    assert _submit(run, req, places[0]["placement_ref"])["status"] == "not_written"
    assert len(run.calls) == 2


def _dependency():
    return {
        "from_slice": "a",
        "to_slice": "b",
        "direction": "approved",
        "connection_points": ["approved existing definition"],
    }


@pytest.mark.parametrize(
    "direction", [None, "from_slice_depends_on_to_slice", "to_slice_depends_on_from_slice"]
)
@pytest.mark.parametrize("patch_fault", [None, "before", "after"])
def test_mapping_late_dependency_prepares_only_owner_preserving_old_references(
    direct_run, monkeypatch, direction, patch_fault
):  # noqa: F811
    run = direct_run
    scope, _, metadata = _multi(run)
    scope.mapping_reference_direction = direction
    original = scope.request
    failed = False

    def patch_once(method, path, body, key):
        nonlocal failed
        if method == "PATCH" and patch_fault and not failed:
            failed = True
            if patch_fault == "after":
                original(method, path, body, key)
            raise TimeoutError("Injected Mapping reference PATCH response loss")
        return original(method, path, body, key)

    scope.request = patch_once
    old = _seed_class(run, monkeypatch, ontology="direct-o2")
    old_ref = _read_class(run, old, ontology="direct-o2")
    run.db.get(OntologyModel, "direct-o").reference_ontology_ids = ["direct-o3"]
    run.db.commit()
    req = _request(
        _change(
            "new-map",
            "create",
            "table_mapping",
            fields={
                "name": "Record mapping",
                "table_name": "records",
                "schema_source": "approved schema",
                "column_mappings": [{"column": "id"}],
                "mapped_class_iri": {"existing_resource_ref": old_ref},
            },
        )
    )
    # table_mapping creation uses the candidate route by contract.
    candidate = {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "incremental",
        "candidate_id": "incremental",
        "revision": 1,
        "explicit_unknowns": [],
        "items": [
            {
                "item_id": "new-map",
                "item_kind": "table_mapping",
                "value": req["changes"][0]["fields"],
                "business_meaning": "Approved mapping",
                "slice_ids": ["a"],
                "shared_scope": None,
                "relation_endpoints": None,
                "unknowns": [],
            }
        ],
    }
    req["candidate_ref"] = "stage3-neutral-graph/candidates/incremental-r1.json"
    req["changes"][0].update(item_id="new-map", fields=None)
    _write_json(run.staged.run_root / req["candidate_ref"], candidate)
    rejected = call(run, req)
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"][0]["code"] == "mapping_reference_scope_required", rejected
    assert not run.calls and not [row for row in metadata if row[0] == "PATCH"]
    if direction is None:
        assert "historical Task has no bound direction" in rejected["errors"][0]["message"]
        return
    dependency = _dependency()
    if direction == "to_slice_depends_on_from_slice":
        dependency["from_slice"], dependency["to_slice"] = "b", "a"
    _write_json(
        run.staged.run_root / "scenario-map/scenario-map.json",
        {"cross_slice_dependencies": [dependency]},
    )
    result = call(run, req)
    if patch_fault == "before":
        assert result["status"] == "not_written", result
        assert result["errors"][0]["code"] == "mapping_reference_scope_required", result
        assert not run.calls
        result = call(run, req)
    assert result["status"] == "completed", result
    assert run.db.get(OntologyModel, "direct-o").reference_ontology_ids == [
        "direct-o2",
        "direct-o3",
    ]
    assert run.db.get(OntologyModel, "direct-o2").reference_ontology_ids == []
    assert len(run.calls) == 1
    assert [row[1] for row in metadata if row[0] == "PATCH"] == ["/api/ontologies/direct-o"]
    iri = result["batches"][0]["resource_bindings"][0]["resource_iri"]
    assert list(
        run.store.dataset.quads(
            (
                URIRef(iri),
                URIRef(str(namespace_from_settings(run.settings).vocab.mappedClass)),
                URIRef(old),
                None,
            )
        )
    )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("type", "binding_kind_mismatch"),
        ("external", "binding_identity_missing"),
        ("forged", "resource_reference_not_observed"),
    ],
)
def test_old_identity_failures_do_not_write_or_invent_ids(direct_run, monkeypatch, fault, expected):  # noqa: F811
    run = direct_run
    iri = _seed_class(run, monkeypatch)
    ns = namespace_from_settings(run.settings)
    if fault == "external":
        iri = "https://external.test/definition/old"
        graph = run.store.dataset.graph(ns.graph("ontology", "direct-o"))
        graph.add((URIRef(iri), RDF.type, OWL.Class))
        graph.add((URIRef(iri), RDFS.label, Literal("External definition")))
    ref = _read_class(run, iri)
    if fault == "type":
        graph = run.store.dataset.graph(ns.graph("ontology", "direct-o"))
        graph.remove((URIRef(iri), RDF.type, OWL.Class))
        graph.add((URIRef(iri), RDF.type, OWL.NamedIndividual))
    if fault == "forged":
        ref = dict(ref, artifact_ref="evidence/not-observed.json")
    req = _request(
        _change(
            "bad-endpoint",
            "create",
            "relation_type",
            fields={
                "name": "relates",
                "source_class_id": {"existing_resource_ref": ref},
                "target_class_id": {"existing_resource_ref": ref},
            },
        )
    )
    result = call(run, req)
    assert result["status"] == "not_written", result
    assert result["errors"][0]["code"] == expected, result
    assert not run.calls and not run.store.writes


@pytest.mark.parametrize("external_type", [str(OWL.Class), "https://external.test/vocab/ImportRun"])
def test_external_iri_remains_available_in_supported_iri_slots(
    direct_run, monkeypatch, external_type
):  # noqa: F811
    run = direct_run
    _seed_class(run, monkeypatch)
    iri = "https://external.test/definition/object"
    graph = run.store.dataset.graph(
        namespace_from_settings(run.settings).graph("ontology", "direct-o")
    )
    graph.add((URIRef(iri), RDF.type, URIRef(external_type)))
    ref = _read_class(run, iri)
    from modeling_team.direct_submission import ObservedModelBindings

    resolver = ObservedModelBindings(
        run.staged.run_root,
        run.runner.acceptance._platform_read_artifacts,
        "direct-p",
        ["direct-o"],
        run.runner._direct_platform_read,
        namespace=namespace_from_settings(run.settings),
    )
    binding = resolver.resolve(ref)
    assert binding["resource_iri"] == iri and "resource_id" not in binding


def test_placement_cannot_bypass_uncertain_original_write(direct_run, monkeypatch):  # noqa: F811
    from modeling_team.staged_batch_write_forwarder import StagedBatchForwardUnknown

    run = direct_run
    _seed_class(run, monkeypatch)
    _, places, _ = _multi(run)
    original_submit, original_read = (
        run.runner.staged_batch_forwarder,
        run.runner.staged_plan_read_forwarder,
    )

    def lose_request(batch):
        raise StagedBatchForwardUnknown("Original request transmission is unknown")

    def unavailable(tool, arguments):
        if tool == "list_session_modeling_batches":
            return {"ok": False, "error_code": "unavailable", "error": "Injected read outage"}
        return original_read(tool, arguments)

    run.runner.staged_batch_forwarder = lose_request
    run.runner.staged_plan_read_forwarder = unavailable
    req = _request(_change("new-kind", "create", "class", fields={"name": "Kind"}))
    first = _submit(run, req, places[0]["placement_ref"])
    assert first["status"] == "uncertain", first
    rejected = _submit(run, req, places[1]["placement_ref"])
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"][0]["code"] == "ontology_write_frozen"
    assert not run.calls
    run.runner.staged_plan_read_forwarder = original_read
    # The executor retains the original forwarder; restoring it is the external repair.
    run.runner._direct_model_executor.submit = original_submit
    completed = _submit(run, req, places[0]["placement_ref"])
    assert completed["status"] == "completed", completed
    assert len(run.calls) == 1 and run.calls[0]["ontology_id"] == "direct-o"


def test_relation_cross_graph_endpoints_do_not_choose_owner_or_require_mapping_gate(
    direct_run, monkeypatch
):  # noqa: F811
    run = direct_run
    scope, places, metadata = _multi(run)
    scope.mapping_reference_direction = None
    old = _seed_class(run, monkeypatch, ontology="direct-o2")
    created = _submit(
        run,
        _request(_change("plan", "create", "class", fields={"name": "Plan"})),
        places[0]["placement_ref"],
    )
    new = created["batches"][0]["resource_bindings"][0]["existing_resource_ref"]
    old_ref = _read_class(run, old, ontology="direct-o2")
    req = _request(
        _change(
            "targets",
            "create",
            "relation_type",
            fields={
                "name": "targets",
                "source_class_id": {"existing_resource_ref": new},
                "target_class_id": {"existing_resource_ref": old_ref},
            },
        )
    )
    result = _submit(run, req, places[0]["placement_ref"])
    assert result["status"] == "completed", result
    assert run.calls[-1]["ontology_id"] == "direct-o"
    assert not [row for row in metadata if row[0] == "PATCH"]
    update = _request(
        _change("rename", "update", "class", fields={"name": "Updated object"}, target_ref=old_ref)
    )
    rejected = _submit(run, update, places[0]["placement_ref"])
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"][0]["code"] == "scope_binding_required", rejected
    assert rejected["errors"][0]["path"] == "/changes/0"
    assert len(run.calls) == 2


@pytest.mark.parametrize(
    "kind,segment,rdf_type",
    [
        ("property", "property", str(OWL.ObjectProperty)),
        ("relation_type", "relation-type", str(OWL.ObjectProperty)),
        ("mapping", "mapping", "SemanticMapping"),
    ],
)
def test_cq_category_does_not_override_native_rdf_resource_kind(
    direct_run, monkeypatch, kind, segment, rdf_type
):  # noqa: F811
    from modeling_team.direct_submission import ObservedModelBindings

    run = direct_run
    _seed_class(run, monkeypatch)
    ns = namespace_from_settings(run.settings)
    iri = str(ns.resource(segment, "old-definition"))
    graph = run.store.dataset.graph(ns.graph("ontology", "direct-o"))
    graph.add(
        (URIRef(iri), RDF.type, URIRef(rdf_type if ":" in rdf_type else str(ns.vocab[rdf_type])))
    )
    ref = _read_class(run, iri)
    binding = ObservedModelBindings(
        run.staged.run_root,
        run.runner.acceptance._platform_read_artifacts,
        "direct-p",
        ["direct-o"],
        run.runner._direct_platform_read,
        namespace=ns,
    ).resolve(ref)
    assert binding["resource_kind"] == kind
    assert binding["resource_id"] == "old-definition"
    assert binding["resource_iri"] == iri


def test_existing_instance_cannot_supply_concept_relation_endpoint(direct_run, monkeypatch):  # noqa: F811
    run = direct_run
    _seed_class(run, monkeypatch)
    ns = namespace_from_settings(run.settings)
    entity = compile_command(
        "create_entity",
        {"ontology_id": "direct-o", "entity_id": "existing-instance", "label": "A concrete object"},
        run.settings,
    )
    run.store.apply_dataset_delta(entity.delta)
    run.store.writes.clear()
    iri = str(ns.resource("entity", "existing-instance"))
    ref = _read_class(run, iri)
    request = _request(
        _change(
            "wrong-level",
            "create",
            "relation_type",
            fields={
                "name": "targets",
                "source_class_id": {"existing_resource_ref": ref},
                "target_class_id": {"existing_resource_ref": ref},
            },
        )
    )
    result = call(run, request)
    assert result["status"] == "not_written", result
    assert result["errors"][0]["code"] == "binding_kind_mismatch", result
    assert result["errors"][0]["path"].endswith("/fields/source_class_id")
    assert not run.calls and not run.store.writes


def test_candidate_without_placement_ref_still_binds_confirmed_topology_identity(
    direct_run, monkeypatch
):  # noqa: F811
    from backend.tests.test_direct_modeling_team_integration import request_for
    import json

    run = direct_run
    _seed_class(run, monkeypatch)
    scope, _, _ = _multi(run)
    request = request_for(run)
    candidate_path = run.staged.run_root / request["candidate_ref"]
    candidate = json.loads(candidate_path.read_text())
    candidate["items"][0]["slice_ids"] = ["a"]
    _write_json(candidate_path, candidate)
    first = call(run, request)
    assert first["status"] == "completed", first
    # Host confirms another binding of the same business slices. The current
    # topology identity, not merely the optional parameter, must bind dedup.
    decision = {
        "ontology_plan": [
            {"ontology_id": "direct-o", "slice_ids": ["b"]},
            {"ontology_id": "direct-o2", "slice_ids": ["a"]},
        ]
    }
    _write_json(run.staged.run_root / "scenario-map/topology-decision.json", decision)
    run.runner._retain_direct_topology(decision)
    second = call(run, request)
    assert second["status"] == "completed", second
    assert first["submission_digest"] != second["submission_digest"]
    assert [batch["ontology_id"] for batch in run.calls] == ["direct-o", "direct-o2"]
    assert call(run, request)["status"] == "completed" and len(run.calls) == 2
