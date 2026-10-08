"""R4.0-010 application boundaries, also runnable against PostgreSQL/Oxigraph."""

from __future__ import annotations

import os
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from rdflib import Graph
from sqlalchemy import delete

from app.api.schemas import BuildSessionCreate, ModelingBatchSubmit, OntologyLeaseAcquire
from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import GraphWriteResult, RdfGraphDelta, RdfStoreRepository
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingAuthorizationContext, ModelingBatchService
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic import SemanticService, SemanticServiceError
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteService,
    CanonicalSemanticWriteError,
)
from app.services.semantic_command_compiler import compile_command
from app.services.semantic_mapping_state import _project


class GraphStore:
    def __init__(self):
        self.graphs = {}

    def graph_exists(self, iri):
        return bool(self.graphs.get(iri))

    def get_graph(self, iri, _format):
        return self.graphs.get(iri, "")

    def apply_dataset_delta(self, delta):
        for iri in delta.affected_graph_iris():
            graph = Graph().parse(data=self.get_graph(iri, "turtle"), format="turtle")
            self.graphs[iri] = _project(graph, delta, iri).serialize(format="turtle")
        return GraphWriteResult(graph_iri=delta.affected_graph_iris()[0], applied=True)


@pytest.fixture(params=["memory", "live"])
def mapping_application(request, in_memory_session):
    live = request.param == "live"
    if live and os.getenv("RUN_RELATIONAL_MAPPING_LIVE") != "1":
        pytest.skip("opt-in PostgreSQL/Oxigraph fixtures")
    token = uuid4().hex
    settings = Settings().model_copy(
        update={
            "semantic_base_iri": f"https://r4010.test/{token}/resource/",
            "semantic_graph_iri_prefix": f"https://r4010.test/{token}/graph/",
            "semantic_product_write_mode": "rdf_primary",
        }
    )
    factory = create_session_factory(settings) if live else None
    session = factory() if live else in_memory_session
    store = RdfStoreRepository(settings.oxigraph_url) if live else GraphStore()
    project_id = str(uuid4())
    ontology_ids = [str(uuid4()) for _ in range(3)]
    graph_iris, sets = [], []
    try:
        session.add(
            m.ProjectModel(id=project_id, name=f"R4010 fixture {token}", normalized_label=token)
        )
        session.flush()
        for index, iri in enumerate(ontology_ids):
            ontology = m.OntologyModel(id=iri, project_id=project_id, name=f"Mapping {index}")
            session.add(ontology)
            session.flush()
            workspace = OntologyWorkspaceService(session, settings)
            workspace.ensure(ontology)
            context = workspace.context(iri)
            sets.append(context["ontology_id"])
            graph_iris.append(context["model_graph_iri"])
        session.commit()
        base = settings.semantic_base_iri
        for ontology in ontology_ids:
            for kind, payload in [
                ("create_class", {"class_id": "object", "name": "Shared object"}),
                (
                    "create_property",
                    {"property_id": "key", "name": "Business key", "datatype": "string"},
                ),
                ("create_relation_type", {"relation_type_id": "related", "name": "Related"}),
            ]:
                store.apply_dataset_delta(
                    compile_command(kind, dict(payload, ontology_id=ontology), settings).delta
                )
        session.get(m.OntologyModel, ontology_ids[1]).reference_ontology_ids = [ontology_ids[0]]
        session.commit()
        bindings = {}
        for index, ontology in enumerate(ontology_ids):
            build = BuildSessionService(session, settings)
            run, _ = build.create_session(
                project_id, BuildSessionCreate(client_session_id=f"{token}-{index}")
            )
            lease = build.acquire_ontology_lease(
                run["id"],
                ontology,
                OntologyLeaseAcquire(client_request_id=token, expected_session_revision=1),
            )
            bindings[ontology] = (run["id"], lease["lease_token"])
        yield dict(
            session=session,
            store=store,
            settings=settings,
            project=project_id,
            ontologies=ontology_ids,
            bindings=bindings,
            base=base,
            factory=factory,
            live=live,
        )
    finally:
        if live:
            session.rollback()

            session.execute(delete(m.ProjectModel).where(m.ProjectModel.id == project_id))
            for model in (m.SemanticGraphRegistryModel, m.SemanticGraphRevisionModel):
                session.execute(delete(model).where(model.graph_iri.in_(graph_iris)))
            session.commit()
            for iri in graph_iris:
                store.drop_named_graph(iri)
            session.close()


def item(key, kind, **payload):
    return {"client_item_id": key, "command_kind": kind, "payload": payload}


def submit(fixture, ontology, items, mode="apply_atomic", *, session=None):
    session = session or fixture["session"]
    build, lease = fixture["bindings"][ontology]
    token = uuid4().hex
    result = ModelingBatchService(session, fixture["settings"], fixture["store"]).submit(
        build,
        ModelingBatchSubmit(
            client_batch_id=token,
            idempotency_key=token,
            ontology_id=ontology,
            mode=mode,
            expected_workspace_version=ModelingWorkspaceVersionService(
                session, fixture["settings"]
            ).version_for(ontology),
            lease_token=lease if mode != "dry_run" else None,
            items=items,
        ),
    )
    return result


def table(f, key, source):
    return item(
        key,
        "create_table_mapping",
        table_mapping_id=key,
        name=source,
        mapped_class_iri=f["base"] + "class/object",
        table_name="records",
        column_mappings=[
            {"column": "id", "property_iri": f["base"] + "property/key"},
            {"column": "tenant"},
        ],
        schema_source="fixture schema",
        mapping_definition={
            "source_key": source,
            "row_grain": "one business object",
            "record_key_columns": ["tenant", "id"],
            "object_key_columns": None,
        },
    )


def join(f, key="join", left="left", right="right"):
    return item(
        key,
        "create_join_mapping",
        join_mapping_id=key,
        name="Composite path",
        relation_type_iri=f["base"] + "relation-type/related",
        join_direction="forward",
        schema_source="fixture schema",
        join_path=[
            {
                "from_mapping_iri": f["base"] + "table-mapping/" + left,
                "to_mapping_iri": f["base"] + "table-mapping/" + right,
                "from_role": "source",
                "to_role": "detail",
                "from_columns": ["tenant", "id"],
                "to_columns": ["tenant", "id"],
            }
        ],
    )


def test_cross_graph_reference_scope_and_final_reverse_integrity(mapping_application):
    f = mapping_application
    a, b, c = f["ontologies"]
    assert submit(f, a, [table(f, "left", "source-a")])["attempt_status"] == "applied"
    assert submit(f, b, [table(f, "right", "source-b"), join(f)])["attempt_status"] == "applied"
    # C belongs to the Project but has no approved dependency scope.
    denied = submit(f, c, [join(f, "unapproved")], "dry_run")
    assert denied["attempt_status"] == "validation_failed"
    changed = item(
        "change",
        "update_table_mapping",
        table_mapping_id="left",
        column_mappings=[{"column": "id", "property_iri": f["base"] + "property/key"}],
        mapping_definition={"source_key": "source-a", "record_key_columns": ["id"]},
    )
    rejected = submit(f, a, [changed])
    assert rejected["attempt_status"] == "validation_failed", rejected
    assert any(x["code"] == "join_path_not_mapped" for x in rejected["findings"])
    # Explicitly revise/remove dependent resources, then retry the same goal.
    assert (
        submit(f, b, [item("remove", "delete_join_mapping", join_mapping_id="join")])[
            "attempt_status"
        ]
        == "applied"
    )
    assert submit(f, a, [changed])["attempt_status"] == "applied"


def test_direct_edits_and_shacl_false_cannot_bypass_mapping_contract(mapping_application):
    f = mapping_application
    a = f["ontologies"][0]
    command = compile_command(
        "create_table_mapping",
        dict(table(f, "direct", "a")["payload"], ontology_id=a),
        f["settings"],
    )
    canonical = CanonicalSemanticWriteService(f["session"], f["store"], f["settings"])
    with pytest.raises(CanonicalSemanticWriteError) as caught:
        canonical.apply_compiled_command(command)
    assert caught.value.code == "mapping_batch_required"
    f["session"].rollback()
    assert submit(f, a, [table(f, "left", "a")])["attempt_status"] == "applied"
    graph = f["settings"].semantic_graph_iri_prefix.rstrip("/") + "/ontology/" + a
    with pytest.raises(SemanticServiceError) as caught:
        SemanticService(f["session"], f["store"], f["settings"]).apply_edit(
            "sparql-update",
            f"DELETE DATA {{ GRAPH <{graph}> {{ <{f['base']}property/key> "
            "a <http://www.w3.org/2002/07/owl#DatatypeProperty> } }",

        )
    assert caught.value.code == "mapping_batch_required"
    assert "columnMappings" in f["store"].get_graph(graph, "turtle")
    f["session"].rollback()


def test_ontology_deletion_preserves_surviving_mapping_dependencies(mapping_application):
    from fastapi import HTTPException
    from app.services.ontology_crud import delete_ontology

    f = mapping_application
    a, b, _ = f["ontologies"]
    assert submit(f, a, [table(f, "left", "a")])["attempt_status"] == "applied"
    assert submit(f, b, [table(f, "right", "b"), join(f)])["attempt_status"] == "applied"
    with pytest.raises(HTTPException) as caught:
        delete_ontology(f["session"], a, f["settings"], f["store"])
    assert caught.value.status_code == 409
    assert caught.value.detail["findings"]
    f["session"].rollback()
    assert f["session"].get(m.OntologyModel, a) is not None


def test_reference_scope_shrink_preserves_dependencies(mapping_application, monkeypatch):
    from fastapi import HTTPException
    from app.api.schemas import OntologyUpdate
    from app.services.ontology_crud import update_ontology
    f = mapping_application
    a, b, _ = f["ontologies"]
    assert submit(f, a, [table(f, "left", "a")])["attempt_status"] == "applied"
    assert submit(f, b, [table(f, "right", "b"), join(f)])["attempt_status"] == "applied"
    monkeypatch.setattr("app.services.ontology_crud.RdfStoreRepository", lambda *_: f["store"])
    with pytest.raises(HTTPException) as caught:
        update_ontology(f["session"], b, OntologyUpdate(reference_ontology_ids=[]))
    assert caught.value.detail["code"] == "mapping_reference_scope_in_use"
    assert f["session"].get(m.OntologyModel, b).reference_ontology_ids == [a]


def test_active_protocol_translation_applies_concrete_mapping_kinds(mapping_application):
    from modeling_team.tests.test_r4010_mapping_contract import (
        _active_protocol_facade,
        _neutral_mapping_candidate,
    )

    f = mapping_application
    wrapper = _active_protocol_facade()
    candidate = _neutral_mapping_candidate()
    mapped = next(x for x in candidate["items"] if x["item_kind"] == "table_mapping")
    # The source-schema key is technical, with no asserted business property.
    mapped["semantic"]["column_mappings"][0]["role"] = "value"
    mapped["semantic"]["column_mappings"][1]["property_iri"] = {"definition_ref": "property-status"}
    metric = next(x for x in candidate["items"] if x["item_kind"] == "metric_definition")
    metric["semantic"]["grain"] = [{"definition_ref": "property-status"}]
    metric["semantic"]["filters"] = []
    metric["semantic"]["schema_source"] = "isolated fixture schema"
    translated = wrapper.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": wrapper.TRANSLATE_CANDIDATE_TOOL_NAME,
                "arguments": {"candidate": candidate, "semantic_base_iri": f["base"]},
            },
        }
    )
    plan = translated["result"]["structuredContent"]
    assert not plan["conflicts"], plan
    resources = {}
    for batch in plan["batches"]:
        checked = submit(f, f["ontologies"][0], batch["items"], "dry_run")
        assert checked["attempt_status"] == "validated", json.dumps(checked, default=str)
        result = submit(f, f["ontologies"][0], batch["items"])
        assert result["attempt_status"] == "applied", json.dumps(result, default=str)
        resources.update({x["client_item_id"]: x["resource_outputs"] for x in result["items"]})
    graph = Graph().parse(
        data=f["store"].get_graph(
            f["settings"].semantic_graph_iri_prefix.rstrip("/") + "/ontology/" + f["ontologies"][0],
            "turtle",
        ),
        format="turtle",
    )
    for identity in plan["resource_identities"]:
        from rdflib import RDF, URIRef

        output = resources[identity["candidate_item_id"]]
        assert output["resource_iri"] == identity["resource_iri"]
        expected = {
            "table_mapping": "TableMapping",
            "join_mapping": "JoinMapping",
            "enum_meaning": "EnumValueMeaning",
            "metric": "MetricDefinition",
        }[identity["resource_kind"]]
        assert (
            URIRef(output["resource_iri"]),
            RDF.type,
            URIRef(f["base"] + "vocab/" + expected),
        ) in graph


def test_uncertain_write_fences_project_until_same_attempt_recovers(
    mapping_application, monkeypatch
):
    f = mapping_application
    a, b, _ = f["ontologies"]
    apply = f["store"].apply_dataset_delta
    applied_deltas = []

    def uncertain(delta):
        applied_deltas.append(delta)
        apply(delta)
        raise RuntimeError("fixture: response lost after RDF write")

    monkeypatch.setattr(f["store"], "apply_dataset_delta", uncertain)
    result = submit(f, a, [table(f, "left", "a")])
    assert result["attempt_status"] == "recovering", result
    fence = f["session"].get(m.OntologyWriteFenceModel, a)
    assert fence is not None
    attempt_id = fence.attempt_id
    attempt = f["session"].get(m.ModelingBatchAttemptModel, attempt_id)
    actual = {tuple(row) for row in applied_deltas[0].inserts}
    expected = {tuple(row) for row in attempt.normalized_delta["inserts"]}
    assert actual == expected, repr((expected - actual, actual - expected))
    monkeypatch.setattr(f["store"], "apply_dataset_delta", apply)
    blocked = submit(f, b, [table(f, "right", "b"), join(f)])
    assert blocked["attempt_status"] == "validation_failed", blocked
    assert any(x["code"] == "mapping_reference_write_fenced" for x in blocked["findings"])
    service = ModelingBatchService(f["session"], f["settings"], f["store"])
    resumed = service._resume_attempt(
        f["session"].get(m.ModelingBatchAttemptModel, attempt_id), ModelingAuthorizationContext()
    )
    assert resumed["attempt_status"] == "applied", json.dumps(resumed, default=str)
    assert f["session"].get(m.OntologyWriteFenceModel, a) is None
    assert submit(f, b, [table(f, "right", "b"), join(f)])["attempt_status"] == "applied"


def test_dependency_changed_after_precheck_is_rejected_without_write_fence(
    mapping_application, monkeypatch
):
    f = mapping_application
    a, b, _ = f["ontologies"]
    assert submit(f, a, [table(f, "left", "a")])["attempt_status"] == "applied"
    assert submit(f, b, [table(f, "right", "b")])["attempt_status"] == "applied"
    execute = ModelingBatchService._execute

    def intervening_change(service, attempt, auth, **kwargs):
        compiled = compile_command(
            "update_table_mapping",
            {
                "ontology_id": a,
                "table_mapping_id": "left",
                "column_mappings": [{"column": "id", "property_iri": f["base"] + "property/key"}],
                "mapping_definition": {"source_key": "a", "record_key_columns": ["id"]},
            },
            f["settings"],
        )
        # Fixture intervention emulates a dependency committed after the precheck.
        f["store"].apply_dataset_delta(compiled.delta)
        return execute(service, attempt, auth, **kwargs)

    monkeypatch.setattr(ModelingBatchService, "_execute", intervening_change)
    result = submit(f, b, [join(f)])
    assert result["attempt_status"] == "failed", result
    assert any(x["code"] == "join_path_not_mapped" for x in result["findings"])
    assert f["session"].get(m.OntologyWriteFenceModel, b) is None
    assert "JoinMapping" not in f["store"].get_graph(
        f["settings"].semantic_graph_iri_prefix.rstrip("/") + "/ontology/" + b, "turtle"
    )


def test_live_interleaved_cross_graph_writes_preserve_integrity(mapping_application):
    f = mapping_application
    if not f["live"]:
        pytest.skip("row-lock concurrency requires PostgreSQL")
    a, b, _ = f["ontologies"]
    assert submit(f, a, [table(f, "left", "a")])["attempt_status"] == "applied"
    assert submit(f, b, [table(f, "right", "b")])["attempt_status"] == "applied"
    removal = item(
        "remove",
        "update_table_mapping",
        table_mapping_id="left",
        column_mappings=[{"column": "id", "property_iri": f["base"] + "property/key"}],
        mapping_definition={"source_key": "a", "record_key_columns": ["id"]},
    )
    assert submit(f, a, [removal], "dry_run")["attempt_status"] == "validated"
    assert submit(f, b, [join(f)], "dry_run")["attempt_status"] == "validated"
    start = Event()

    def apply(ontology, items):
        with f["factory"]() as session:
            assert start.wait(10)
            return submit(f, ontology, items, session=session)

    # Both apply requests start from successful independent prechecks.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(apply, a, [removal]), pool.submit(apply, b, [join(f)])]
        start.set()
        results = [future.result(timeout=40) for future in futures]
    assert sum(result["attempt_status"] == "applied" for result in results) == 1, results
    from app.services.semantic_mapping_state import mapping_write_findings

    assert mapping_write_findings(f["session"], f["store"], f["settings"], RdfGraphDelta(), a) == []
