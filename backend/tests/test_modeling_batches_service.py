"""Service invariants for the R-004 Modeling Batch protocol."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BuildSessionCreate,
    ModelingBatchSubmit,
    ModelingItemInput,
    OntologyLeaseAcquire,
)
from app.core.config import Settings
from app.repositories.models import (
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    OntologyModel,
    OntologyWriteFenceModel,
    ProjectModel,
    SemanticProjectionManifestModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
    SemanticStatementOccurrenceModel,
    SemanticStatementOriginModel,
)
from app.repositories.rdf_store import GraphWriteResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchError, ModelingBatchService
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.ontology_lineage import OntologyLineageService
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteService,
    CanonicalShaclViolation,
)


PROJECT_ID = "r004-project"
ONTOLOGY_ID = "r004-ontology"


class FakeRdfStore:
    def __init__(self) -> None:
        self.deltas = []

    def graph_exists(self, _graph_iri):
        return False

    def get_graph(self, _graph_iri, _format):
        return ""

    def apply_dataset_delta(self, delta):
        self.deltas.append(delta)
        return GraphWriteResult(
            graph_iri=delta.affected_graph_iris()[0] if delta.affected_graph_iris() else "",
            applied=not delta.is_empty,
            inserted_quad_count=len(delta.inserts),
            deleted_quad_count=len(delta.deletes),
        )


class MissingNamedGraphRdfStore(FakeRdfStore):
    def get_graph(self, graph_iri, _format):
        raise AssertionError(f"get_graph must not be called for missing graph: {graph_iri}")


class UncertainRdfStore(FakeRdfStore):
    def __init__(self, *, persist_before_failure: bool) -> None:
        super().__init__()
        self.persist_before_failure = persist_before_failure
        self.failures = 0
        self.graphs: dict[str, str] = {}

    def graph_exists(self, graph_iri):
        return bool(self.graphs.get(graph_iri))

    def get_graph(self, graph_iri, _format):
        return self.graphs.get(graph_iri, "")

    def apply_dataset_delta(self, delta):
        self.failures += 1
        if self.persist_before_failure:
            for subject, predicate, obj, graph_iri in delta.inserts:
                self.graphs[graph_iri] = self.graphs.get(graph_iri, "") + (
                    f"{subject} {predicate} {obj} .\n"
                )
        raise RuntimeError("simulated uncertain RDF response")


def _settings() -> Settings:
    return Settings(
        semantic_graph_iri_prefix="https://r004.test/graph/",
        semantic_base_iri="https://r004.test/resource/",
        semantic_product_write_mode="rdf_primary",
    )


@pytest.fixture()
def modeling(in_memory_session: Session):
    settings = _settings()
    in_memory_session.add(ProjectModel(id=PROJECT_ID, name="R004", normalized_label="r004"))
    ontology = OntologyModel(id=ONTOLOGY_ID, project_id=PROJECT_ID, name="R004 ontology")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    in_memory_session.commit()
    build = BuildSessionService(in_memory_session, settings)
    session_data, _created = build.create_session(
        PROJECT_ID, BuildSessionCreate(client_session_id="agent-session")
    )
    session_id = session_data["id"]
    lease = build.acquire_ontology_lease(
        session_id,
        ONTOLOGY_ID,
        OntologyLeaseAcquire(client_request_id="lease-1", expected_session_revision=1),
    )
    rdf = FakeRdfStore()
    service = ModelingBatchService(in_memory_session, settings, rdf)  # type: ignore[arg-type]
    version = ModelingWorkspaceVersionService(in_memory_session, settings).version_for(ONTOLOGY_ID)
    return service, in_memory_session, rdf, session_id, lease, version


def _item(item_id: str, *, name: str = "Customer", **overrides):
    data = {
        "client_item_id": item_id,
        "command_kind": "create_class",
        "payload": {"name": name},
        "rationale": "Needed by customer competency questions",
        "evidence": [{"document_name": "domain.md", "excerpt": f"{name} is a domain term."}],
    }
    data.update(overrides)
    return ModelingItemInput(**data)


def _request(version, items, *, key="attempt-1", batch="batch-1", mode="dry_run", token=None):
    return ModelingBatchSubmit(
        client_batch_id=batch,
        ontology_id=ONTOLOGY_ID,
        idempotency_key=key,
        mode=mode,
        expected_workspace_version=version,
        lease_token=token,
        items=items,
    )


def test_dry_run_is_persistent_deterministic_and_has_zero_side_effects(modeling):
    service, db, rdf, session_id, _lease, version = modeling
    payload = _request(version, [_item("customer")])

    first = service.submit(session_id, payload)
    retry = service.submit(session_id, payload)

    assert first["attempt_status"] == "validated"
    assert first["created_batch"] is True and first["created_attempt"] is True
    assert retry["created_batch"] is False and retry["created_attempt"] is False
    assert first["items"][0]["resource_outputs"] == retry["items"][0]["resource_outputs"]
    assert rdf.deltas == []
    assert db.scalar(select(func.count(EvidenceReferenceModel.id))) == 0
    assert db.scalar(select(func.count(ModelingBatchModel.id))) == 1
    assert db.scalar(select(func.count(ModelingBatchAttemptModel.id))) == 1
    assert "lease" not in json.dumps(first, default=str).lower()


def test_operation_secret_is_rejected_before_batch_persistence(modeling):
    service, db, _rdf, session_id, _lease, version = modeling
    operation = _item(
        "publish",
        command_kind="create_operation",
        payload={
            "name": "Publish",
            "target_resource_type_iri": "https://example.test/Workflow",
            "idempotency": {"kind": "unknown"},
            "risk_level": "low",
            "tool_bindings": [
                {
                    "binding_id": "publish",
                    "kind": "http_api",
                    "system": "generic",
                    "operation_identifier": "POST /publish",
                    "authorization": "must-not-be-persisted",
                }
            ],
        },
    )

    with pytest.raises(ModelingBatchError) as rejected:
        service.submit(session_id, _request(version, [operation], batch="secret-batch"))

    assert rejected.value.code == "operation_secret_forbidden"
    assert "must-not-be-persisted" not in rejected.value.message
    assert db.scalar(select(func.count(ModelingBatchModel.id))) == 0
    assert db.scalar(select(func.count(ModelingBatchAttemptModel.id))) == 0


def test_operation_can_target_class_created_by_item_ref(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    operation = _item(
        "publish",
        command_kind="create_operation",
        depends_on=["workflow"],
        payload={
            "operation_id": "publish-workflow",
            "name": "Publish workflow",
            "target_resource_type_iri": {
                "item_ref": {"client_item_id": "workflow", "output": "resource_iri"}
            },
            "parameters": [],
            "preconditions": [],
            "effects": [],
            "possible_failures": [],
            "idempotency": {"kind": "idempotent"},
            "risk_level": "low",
            "tool_bindings": [
                {
                    "binding_id": "publish",
                    "kind": "mcp_tool",
                    "system": "generic",
                    "operation_identifier": "publish_workflow",
                }
            ],
            "credential_requirements": [],
        },
    )

    result = service.submit(
        session_id,
        _request(version, [_item("workflow", name="Workflow"), operation], batch="operation"),
    )

    assert result["attempt_status"] == "validated"
    outputs = {item["client_item_id"]: item["resource_outputs"] for item in result["items"]}
    assert outputs["publish"]["resource_iri"].endswith("/operation/publish-workflow")


def test_32_item_dry_run_accepts_generated_operation_id_and_shared_status_vocab(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    classes = [_item(f"workflow-class-{index}") for index in range(8)]
    operation = _item(
        "invoke-published-workflow",
        command_kind="create_operation",
        depends_on=["workflow-class-0"],
        payload={
            "operation_id": None,
            "name": "Invoke published workflow",
            "target_resource_type_iri": {
                "item_ref": {"client_item_id": "workflow-class-0", "output": "resource_iri"}
            },
            "parameters": [
                {
                    "name": "inputs",
                    "required": False,
                    "value_type": "string",
                    "enum_values": [],
                    "default_value": None,
                    "constraints": {},
                }
            ],
            "preconditions": [],
            "effects": [],
            "possible_failures": [],
            "idempotency": {"kind": "unknown"},
            "risk_level": "medium",
            "tool_bindings": [
                {
                    "binding_id": "dify-workflow-rest-api",
                    "kind": "http_api",
                    "system": "Dify Workflow API",
                    "operation_identifier": "Run Workflow",
                }
            ],
            "credential_requirements": [
                {
                    "name": "Dify app API key",
                    "reference_type": "app_api_key",
                    "description": "Required for published-app REST API calls.",
                    "required": True,
                }
            ],
            "status": "active",
            "schema_version": "operation-v1",
        },
    )
    properties = [
        _item(
            f"workflow-property-{index}",
            command_kind="create_property",
            depends_on=["workflow-class-0"],
            payload={
                "property_id": None,
                "name": f"workflow_property_{index}",
                "class_id": {
                    "item_ref": {
                        "client_item_id": "workflow-class-0",
                        "output": "resource_id",
                    }
                },
                "datatype": "string",
                "object_class_id": None,
            },
        )
        for index in range(15)
    ]
    relations = [
        _item(
            f"workflow-relation-{index}",
            command_kind="create_relation_type",
            depends_on=["workflow-class-0", "workflow-class-1"],
            payload={
                "relation_type_id": None,
                "name": f"workflow_relation_{index}",
                "source_class_id": {
                    "item_ref": {
                        "client_item_id": "workflow-class-0",
                        "output": "resource_id",
                    }
                },
                "target_class_id": {
                    "item_ref": {
                        "client_item_id": "workflow-class-1",
                        "output": "resource_id",
                    }
                },
                "scope_policy": "schema_allowed",
                "status": "active",
            },
        )
        for index in range(8)
    ]
    items = [*classes, operation, *properties, *relations]

    assert len(items) == 32
    result = service.submit(
        session_id,
        _request(version, items, batch="mixed-operation-and-relation-vocabulary"),
    )

    assert result["attempt_status"] == "validated"
    assert not any(finding["blocking"] for finding in result["findings"])
    outputs = {item["client_item_id"]: item["resource_outputs"] for item in result["items"]}
    assert outputs["invoke-published-workflow"]["resource_id"]
    assert outputs["invoke-published-workflow"]["resource_iri"].startswith(
        "https://r004.test/resource/operation/"
    )


def test_operation_dry_run_treats_not_yet_physical_ontology_graph_as_empty(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    service.rdf_store = MissingNamedGraphRdfStore()  # type: ignore[assignment]
    operation = _item(
        "publish",
        command_kind="create_operation",
        depends_on=["workflow"],
        payload={
            "operation_id": "publish-missing-graph",
            "name": "Publish workflow",
            "target_resource_type_iri": {
                "item_ref": {"client_item_id": "workflow", "output": "resource_iri"}
            },
            "parameters": [],
            "preconditions": [],
            "effects": [],
            "possible_failures": [],
            "idempotency": {"kind": "idempotent"},
            "risk_level": "low",
            "tool_bindings": [
                {
                    "binding_id": "publish",
                    "kind": "mcp_tool",
                    "system": "generic",
                    "operation_identifier": "publish_workflow",
                }
            ],
            "credential_requirements": [],
        },
    )

    result = service.submit(
        session_id,
        _request(
            version,
            [_item("workflow", name="Workflow"), operation],
            batch="missing-physical-graph",
        ),
    )

    assert result["attempt_status"] == "validated"
    assert not any(finding["blocking"] for finding in result["findings"])


def test_batch_and_attempt_idempotency_conflicts_are_request_level(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    service.submit(session_id, _request(version, [_item("customer")]))

    with pytest.raises(ModelingBatchError) as changed_batch:
        service.submit(
            session_id,
            _request(version, [_item("customer", name="Buyer")], key="attempt-2"),
        )
    assert changed_batch.value.code == "batch_content_conflict"

    with pytest.raises(ModelingBatchError) as changed_attempt:
        service.submit(
            session_id,
            _request(version, [_item("customer")], key="attempt-1", mode="apply_atomic", token="x"),
        )
    assert changed_attempt.value.code == "idempotency_conflict"


def test_atomic_validation_failure_does_not_apply_any_item(modeling):
    service, _db, rdf, session_id, lease, version = modeling
    invalid = _item("bad", command_kind="unknown_command", payload={})
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("good"), invalid],
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    status = {item["client_item_id"]: item["status"] for item in result["items"]}
    assert result["attempt_status"] == "validation_failed"
    assert status == {"bad": "failed", "good": "not_applied"}
    assert rdf.deltas == []


def test_partial_applies_stable_subset_and_only_its_evidence(modeling):
    service, db, rdf, session_id, lease, version = modeling
    invalid = _item("bad", command_kind="unknown_command", payload={})
    dependent = _item("dependent", depends_on=["bad"])
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("good"), invalid, dependent],
            mode="apply_partial",
            token=lease["lease_token"],
        ),
    )
    status = {item["client_item_id"]: item["status"] for item in result["items"]}
    assert result["attempt_status"] == "partially_applied"
    assert status == {"bad": "failed", "dependent": "blocked", "good": "applied"}
    assert len(rdf.deltas) == 1
    assert db.scalar(select(func.count(EvidenceReferenceModel.id))) == 1
    assert db.scalar(select(func.count(EvidenceAssociationModel.id))) == 1
    assert db.scalar(select(func.count(SemanticStatementOccurrenceModel.id))) > 0
    good_item_id = next(
        item["item_id"] for item in result["items"] if item["client_item_id"] == "good"
    )
    modeling_origins = list(
        db.scalars(
            select(SemanticStatementOriginModel).where(
                SemanticStatementOriginModel.origin_kind == "modeling_item"
            )
        )
    )
    assert modeling_origins
    assert {origin.origin_id for origin in modeling_origins} == {good_item_id}
    resource_iri = next(
        item["resource_outputs"]["resource_iri"]
        for item in result["items"]
        if item["client_item_id"] == "good"
    )
    lineage = OntologyLineageService(db).get_lineage(
        ontology_id=ONTOLOGY_ID,
        target_type="resource",
        target_id=resource_iri,
    )
    assert lineage["evidence_status"] == "supported"
    assert lineage["items"][0]["supporting_context"]["rationales"]


def test_item_ref_cycle_forms_atomic_group_without_becoming_an_error(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    first = _item(
        "a",
        payload={
            "name": "A",
            "parent_class_ids": [{"item_ref": {"client_item_id": "b", "output": "resource_id"}}],
        },
    )
    second = _item(
        "b",
        payload={
            "name": "B",
            "parent_class_ids": [{"item_ref": {"client_item_id": "a", "output": "resource_id"}}],
        },
    )
    result = service.submit(session_id, _request(version, [first, second]))
    assert result["attempt_status"] == "validated"
    assert len(result["groups"]) == 1
    assert result["groups"][0]["cyclic"] is True


def test_conflicting_same_single_value_slot_is_not_last_write_wins(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    same_id = "11111111-1111-1111-1111-111111111111"
    first = _item("a", payload={"class_id": same_id, "name": "A"})
    second = _item("b", payload={"class_id": same_id, "name": "B"})
    result = service.submit(session_id, _request(version, [first, second]))
    assert result["attempt_status"] == "validation_failed"
    assert "conflicting_item_effects" in {finding["code"] for finding in result["findings"]}


def test_rule_only_apply_versions_logical_rule_and_changes_workspace_version(modeling):
    service, db, _rdf, session_id, lease, version = modeling
    rule = ModelingItemInput(
        client_item_id="rule",
        command_kind="create_rule_definition",
        payload={
            "rule_iri": "https://rules.test/customer-rule",
            "name": "Customer rule",
            "language": "platform_dsl",
            "body": {
                "when": [{"s": "?s", "p": "https://x/status", "o": "active"}],
                "then": [{"s": "?s", "p": "https://x/eligible", "o": True}],
            },
            "input_roles": ["asserted_data"],
        },
        rationale="Derive customer state",
    )
    result = service.submit(
        session_id,
        _request(version, [rule], mode="apply_atomic", token=lease["lease_token"]),
    )
    assert result["attempt_status"] == "applied"
    assert db.scalar(select(func.count(SemanticRuleModel.id))) == 1
    assert db.scalar(select(func.count(SemanticRuleDefinitionModel.id))) == 1
    assert result["items"][0]["resource_outputs"]["resource_iri"] == (
        "https://rules.test/customer-rule"
    )
    assert db.scalar(select(SemanticRuleModel.rule_iri)) == "https://rules.test/customer-rule"
    assert result["workspace"]["after_version"] != version
    lineage = OntologyLineageService(db).get_lineage(
        ontology_id=ONTOLOGY_ID,
        target_type="rule",
        target_id="https://rules.test/customer-rule",
    )
    assert lineage["items"][0]["definition"]["version"].startswith("sha256:")
    assert lineage["items"][0]["supporting_context"]["rationales"] == [
        {
            "modeling_item_id": result["items"][0]["item_id"],
            "text": "Derive customer state",
        }
    ]
    assert lineage["items"][0]["supporting_context"]["edit_audits"]
    assert lineage["evidence_status"] == "missing"

    duplicate = service.submit(
        session_id,
        _request(
            result["workspace"]["after_version"],
            [rule],
            key="attempt-2",
            batch="batch-2",
        ),
    )
    assert duplicate["attempt_status"] == "validation_failed"
    assert "resource_already_exists" in {finding["code"] for finding in duplicate["findings"]}


def test_modeling_context_and_cross_session_history_hide_internal_targets(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    submitted = service.submit(session_id, _request(version, [_item("customer")]))
    context = service.get_modeling_context(ONTOLOGY_ID)
    history = service.list_ontology_batches(ONTOLOGY_ID)
    detail = service.get_batch(submitted["batch_id"])

    assert context["workspace"]["workspace_version"] == version
    assert context["query_entries"]["classes"]["rest"].startswith("/api/ontologies/")
    assert context["recent_batches"][0]["batch_id"] == submitted["batch_id"]
    assert context["recent_batches_next_cursor"] is None
    assert history["batches"][0]["batch_id"] == submitted["batch_id"]
    assert detail["attempts"][0]["findings"] == submitted["findings"]
    safe_json = json.dumps({"context": context, "history": history}, default=str)
    assert "graph_set_id" not in safe_json and "graph_iri" not in safe_json


@pytest.mark.parametrize("mode", ["dry_run", "apply_partial"])
def test_candidate_shacl_failure_is_a_finding_before_fence(modeling, monkeypatch, mode):
    service, db, rdf, session_id, lease, version = modeling

    def reject_candidate(self, compiled, **kwargs):
        raise CanonicalShaclViolation("candidate does not conform")

    monkeypatch.setattr(
        CanonicalSemanticWriteService, "validate_compiled_command", reject_candidate
    )
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("customer")],
            mode=mode,
            token=lease["lease_token"] if mode != "dry_run" else None,
        ),
    )

    assert result["attempt_status"] == "validation_failed"
    assert "shacl_violation" in {finding["code"] for finding in result["findings"]}
    assert rdf.deltas == []
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_new_shape_validates_entities_in_the_same_candidate_batch(modeling):
    service, db, _rdf, session_id, _lease, version = modeling
    shape = ModelingItemInput(
        client_item_id="customer-shape",
        command_kind="create_shape",
        payload={
            "target_class_id": "customer",
            "constraints": [{"path_id": "email", "min_count": 1}],
        },
    )
    entity = ModelingItemInput(
        client_item_id="customer-entity",
        command_kind="create_entity",
        payload={
            "class_iri_or_legacy_id": "customer",
            "label": "Alice",
        },
    )

    result = service.submit(session_id, _request(version, [shape, entity]))

    assert result["attempt_status"] == "validation_failed"
    assert "shacl_violation" in {finding["code"] for finding in result["findings"]}
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_malformed_nested_shape_payload_becomes_a_finding(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    shape = ModelingItemInput(
        client_item_id="bad-shape",
        command_kind="create_shape",
        payload={
            "target_class_id": "customer",
            "constraints": [{"path_id": "email", "min_count": "not-an-integer"}],
        },
    )

    result = service.submit(session_id, _request(version, [shape]))

    assert result["attempt_status"] == "validation_failed"
    assert "invalid_command_payload" in {finding["code"] for finding in result["findings"]}


def test_missing_rule_update_fails_validation_without_leaving_a_fence(modeling):
    service, db, rdf, session_id, lease, version = modeling
    item = ModelingItemInput(
        client_item_id="missing-rule",
        command_kind="update_rule_definition",
        payload={"rule_id": "missing", "name": "No such rule"},
    )

    result = service.submit(
        session_id,
        _request(version, [item], mode="apply_atomic", token=lease["lease_token"]),
    )

    assert result["attempt_status"] == "validation_failed"
    assert "invalid_resource_reference" in {finding["code"] for finding in result["findings"]}
    assert rdf.deltas == []
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_shape_apply_targets_workspace_member_and_changes_version(modeling):
    service, _db, rdf, session_id, lease, version = modeling
    shape = ModelingItemInput(
        client_item_id="customer-shape",
        command_kind="create_shape",
        payload={"target_class_id": "customer", "constraints": []},
    )

    result = service.submit(
        session_id,
        _request(version, [shape], mode="apply_atomic", token=lease["lease_token"]),
    )

    assert result["attempt_status"] == "applied"
    assert result["workspace"]["after_version"] != version
    assert rdf.deltas[0].affected_graph_iris() == [
        f"{_settings().semantic_graph_iri_prefix.rstrip('/')}/shapes/{ONTOLOGY_ID}"
    ]


def test_apply_marks_projection_manifest_stale_immediately(modeling):
    service, db, _rdf, session_id, lease, version = modeling
    manifest = SemanticProjectionManifestModel(
        id="projection-manifest",
        graph_set_id=OntologyWorkspaceService(db, _settings()).context(ONTOLOGY_ID)[
            "default_graph_set_id"
        ],
        projection_kind="search",
        source_signature=version,
        projection_version="v1",
        target_partition="r004",
        status="current",
    )
    db.add(manifest)
    db.commit()

    result = service.submit(
        session_id,
        _request(
            version,
            [_item("customer")],
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert result["attempt_status"] == "applied"
    assert db.get(SemanticProjectionManifestModel, manifest.id).status == "stale"
    assert service.get_modeling_context(ONTOLOGY_ID)["derived_state"]["stale_projection_count"] == 1


def test_entity_cascade_delete_conflicts_with_new_incoming_relation(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    entity_iri = "https://r004.test/resource/entity/customer"
    delete = ModelingItemInput(
        client_item_id="delete-customer",
        command_kind="delete_entity",
        payload={"entity_iri": entity_iri},
    )
    relation = ModelingItemInput(
        client_item_id="link-customer",
        command_kind="create_relation",
        payload={
            "source_entity_iri": "https://r004.test/resource/entity/order",
            "relation_type_iri": "https://r004.test/resource/relation/customer",
            "target_entity_iri": entity_iri,
        },
    )

    result = service.submit(session_id, _request(version, [delete, relation]))

    assert result["attempt_status"] == "validation_failed"
    assert "conflicting_item_effects" in {finding["code"] for finding in result["findings"]}


def test_multiple_relation_targets_for_same_subject_and_type_are_valid(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    source = "https://r004.test/resource/entity/workflow-definition"
    relation_type = "https://r004.test/resource/relation/has-input"
    relations = [
        ModelingItemInput(
            client_item_id=f"definition-input-{index}",
            command_kind="create_relation",
            payload={
                "source_entity_iri": source,
                "relation_type_iri": relation_type,
                "target_entity_iri": f"https://r004.test/resource/entity/input-{index}",
            },
        )
        for index in range(2)
    ]

    result = service.submit(session_id, _request(version, relations))

    assert result["attempt_status"] == "validated"
    assert "conflicting_item_effects" not in {finding["code"] for finding in result["findings"]}


def test_create_and_delete_same_relation_target_still_conflict(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    payload = {
        "source_entity_iri": "https://r004.test/resource/entity/workflow-definition",
        "relation_type_iri": "https://r004.test/resource/relation/has-input",
        "target_entity_iri": "https://r004.test/resource/entity/input-1",
    }
    create = ModelingItemInput(
        client_item_id="create-definition-input",
        command_kind="create_relation",
        payload=payload,
    )
    delete = ModelingItemInput(
        client_item_id="delete-definition-input",
        command_kind="delete_relation",
        payload=payload,
    )

    result = service.submit(session_id, _request(version, [create, delete]))

    assert result["attempt_status"] == "validation_failed"
    assert "conflicting_item_effects" in {finding["code"] for finding in result["findings"]}


def test_recovery_observes_applied_rdf_and_finalizes_without_rewriting(modeling):
    service, db, _rdf, session_id, lease, version = modeling
    uncertain = UncertainRdfStore(persist_before_failure=True)
    service.rdf_store = uncertain  # type: ignore[assignment]
    payload = _request(
        version,
        [_item("customer")],
        mode="apply_atomic",
        token=lease["lease_token"],
    )

    first = service.submit(session_id, payload)
    assert first["attempt_status"] == "recovering"
    retry = service.submit(session_id, payload)

    assert retry["attempt_status"] == "applied"
    assert uncertain.failures == 1
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None
    occurrence_count = db.scalar(select(func.count(SemanticStatementOccurrenceModel.id)))
    origin_count = db.scalar(select(func.count(SemanticStatementOriginModel.id)))
    terminal_retry = service.submit(session_id, payload)
    assert terminal_retry["attempt_status"] == "applied"
    assert db.scalar(select(func.count(SemanticStatementOccurrenceModel.id))) == occurrence_count
    assert db.scalar(select(func.count(SemanticStatementOriginModel.id))) == origin_count


def test_bounded_recovery_can_fail_when_no_side_effects_are_proven(modeling):
    service, db, _rdf, session_id, lease, version = modeling
    uncertain = UncertainRdfStore(persist_before_failure=False)
    service.rdf_store = uncertain  # type: ignore[assignment]
    service.settings = Settings(
        **{
            **_settings().model_dump(),
            "modeling_batch_recovery_max_steps": 1,
        }
    )
    payload = _request(
        version,
        [_item("customer")],
        mode="apply_atomic",
        token=lease["lease_token"],
    )

    assert service.submit(session_id, payload)["attempt_status"] == "recovering"
    terminal = service.submit(session_id, payload)

    assert terminal["attempt_status"] == "failed"
    assert terminal["batch_status"] == "failed"
    assert terminal["recovery"]["state"] == "failed_without_side_effects"
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_recovery_stops_for_rdf_state_outside_the_persisted_plan(modeling):
    service, db, _rdf, session_id, lease, version = modeling
    uncertain = UncertainRdfStore(persist_before_failure=True)
    service.rdf_store = uncertain  # type: ignore[assignment]
    payload = _request(
        version,
        [_item("customer")],
        mode="apply_atomic",
        token=lease["lease_token"],
    )

    first = service.submit(session_id, payload)
    graph_iri = next(iter(uncertain.graphs))
    uncertain.graphs[graph_iri] += (
        '<https://external.test/s> <https://external.test/p> "unexpected" .\n'
    )
    retry = service.submit(session_id, payload)

    assert first["attempt_status"] == retry["attempt_status"] == "recovering"
    assert retry["recovery"]["state"] == "recovery_requires_intervention"
    assert retry["recovery"]["safe_to_retry"] is False
    assert uncertain.failures == 1
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is not None


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("create_class", {"name": "Customer"}),
        ("update_class", {"class_id": "c", "name": "Buyer"}),
        ("delete_class", {"class_id": "c"}),
        ("create_property", {"class_id": "c", "name": "email", "datatype": "xsd:string"}),
        ("update_property", {"property_id": "p", "datatype": "xsd:string"}),
        ("delete_property", {"property_id": "p"}),
        ("create_relation_type", {"name": "owns", "source_class_id": "c", "target_class_id": "c"}),
        ("update_relation_type", {"relation_type_id": "r", "inverse_name": "owned by"}),
        ("delete_relation_type", {"relation_type_id": "r"}),
        ("create_shape", {"target_class_id": "c", "constraints": []}),
        ("update_shape", {"shape_id": "s", "target_class_id": "c", "constraints": []}),
        ("delete_shape", {"shape_id": "s"}),
        ("create_entity", {"class_iri_or_legacy_id": "c", "label": "Alice"}),
        ("update_entity", {"entity_id": "e", "label": "Alicia"}),
        ("delete_entity", {"entity_id": "e"}),
        (
            "create_relation",
            {
                "source_entity_iri": "https://x/s",
                "relation_type_iri": "https://x/p",
                "target_entity_iri": "https://x/o",
            },
        ),
        (
            "delete_relation",
            {
                "source_entity_iri": "https://x/s",
                "relation_type_iri": "https://x/p",
                "target_entity_iri": "https://x/o",
            },
        ),
        (
            "update_fact",
            {
                "subject_iri": "https://x/s",
                "predicate_iri": "https://x/p",
                "old_object_value": "a",
                "new_object_value": "b",
            },
        ),
        (
            "delete_fact",
            {"subject_iri": "https://x/s", "predicate_iri": "https://x/p", "object_value": "a"},
        ),
        (
            "create_mapping",
            {
                "external_field_iri": "https://x/f",
                "target_type": "class",
                "target_iri": "https://x/c",
                "join_key": "id",
            },
        ),
        ("update_mapping", {"mapping_id": "m", "join_key": "external_id"}),
        ("delete_mapping", {"mapping_id": "m"}),
        (
            "create_rule_definition",
            {
                "name": "R",
                "language": "platform_dsl",
                "body": {
                    "when": [{"s": "?s", "p": "https://x/status", "o": "active"}],
                    "then": [{"s": "?s", "p": "https://x/eligible", "o": True}],
                },
                "input_roles": ["asserted_data"],
            },
        ),
        ("update_rule_definition", {"rule_id": "r", "name": "R2"}),
        ("delete_rule_definition", {"rule_id": "r"}),
    ],
)
def test_first_version_handler_registry_covers_frozen_command_scope(kind, payload):
    prepared = ModelingCommandHandlerRegistry(_settings()).prepare(
        batch_id="batch",
        ontology_id=ONTOLOGY_ID,
        client_item_id=kind,
        command_kind=kind,
        payload=payload,
    )
    assert prepared.command_kind == kind
