"""Service invariants for the R-004 Modeling Batch protocol."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
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
from app.repositories.rdf_store import GraphWriteResult, RdfStoreUnavailable
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchError, ModelingBatchService
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import InvalidCommandPayload
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


class PersistentFakeRdfStore(FakeRdfStore):
    """In-memory N-Quads source for apply-then-dry-run validation coverage."""

    def __init__(self) -> None:
        super().__init__()
        self.graphs: dict[str, str] = {}

    def graph_exists(self, graph_iri):
        return bool(self.graphs.get(graph_iri))

    def get_graph(self, graph_iri, _format):
        return self.graphs.get(graph_iri, "")

    def apply_dataset_delta(self, delta):
        for subject, predicate, obj, graph_iri in delta.inserts:
            self.graphs[graph_iri] = self.graphs.get(graph_iri, "") + (
                f"{subject} {predicate} {obj} .\n"
            )
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


def test_dry_run_rejects_inline_evidence_input(modeling):
    service, db, _rdf, session_id, _lease, version = modeling
    excerpt = "Customer is a domain term."
    with pytest.raises(ValidationError):
        _item("customer", evidence=[{"document_name": "domain.md", "excerpt": excerpt}])
    assert db.scalar(select(func.count(EvidenceReferenceModel.id))) == 0


def test_dry_run_without_evidence_has_no_trace_warning_or_projection(modeling):
    service, db, _rdf, session_id, _lease, version = modeling
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("customer")],
            batch="missing-evidence-plan",
            key="missing-evidence-plan",
        ),
    )

    assert all(finding["code"] != "missing_evidence" for finding in result["findings"])
    assert "operation_plan" not in result
    assert db.scalar(select(func.count(EvidenceReferenceModel.id))) == 0


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


@pytest.mark.parametrize(
    ("command_kind", "payload"),
    [
        (
            "create_entity",
            {
                "class_iri_or_legacy_id": "customer",
                "label": "Alice",
                "properties": [{"property_iri": "https://r004.test/property/name", "value": "Alice"}],
            },
        ),
        (
            "update_entity",
            {
                "entity_id": "customer-1",
                "properties": [{"property_iri": "https://r004.test/property/name", "value": "Alice"}],
            },
        ),
    ],
)
def test_entity_property_lists_are_structured_batch_validation_failures(
    modeling, command_kind, payload
):
    service, _db, rdf, session_id, _lease, version = modeling

    result = service.submit(
        session_id,
        _request(
            version,
            [_item("entity", command_kind=command_kind, payload=payload)],
            batch=f"{command_kind}-properties-list",
            key=f"{command_kind}-properties-list",
        ),
    )

    assert result["attempt_status"] == "validation_failed"
    finding = next(finding for finding in result["findings"] if finding["blocking"])
    assert finding["code"] == "invalid_command_payload"
    assert finding["client_item_ids"] == ["entity"]
    assert "must be a JSON object mapping property IRI keys to values" in finding["message"]
    assert rdf.deltas == []


@pytest.mark.parametrize(
    "payload",
    [
        {"class_iri_or_legacy_id": "customer", "label": "Alice"},
        {"class_iri_or_legacy_id": "customer", "label": "Alice", "properties": None},
        {"class_iri_or_legacy_id": "customer", "label": "Alice", "properties": {}},
        {
            "class_iri_or_legacy_id": "customer",
            "label": "Alice",
            "properties": {"https://r004.test/property/is_latest": True},
        },
    ],
)
def test_entity_property_maps_remain_valid_handler_inputs(payload):

    prepared = ModelingCommandHandlerRegistry(_settings()).prepare(
        batch_id="entity-properties-map",
        ontology_id=ONTOLOGY_ID,
        client_item_id="entity",
        command_kind="create_entity",
        payload=payload,
    )

    assert prepared.compiled is not None


@pytest.mark.parametrize("command_kind", ["create_entity", "update_entity"])
def test_entity_property_lists_are_rejected_by_handler_before_compiler(command_kind):
    payload = {"properties": [{"property_iri": "https://r004.test/property/name", "value": "Alice"}]}
    if command_kind == "create_entity":
        payload.update({"class_iri_or_legacy_id": "customer", "label": "Alice"})
    else:
        payload["entity_id"] = "customer-1"

    with pytest.raises(InvalidCommandPayload, match="must be a JSON object mapping property IRI"):
        ModelingCommandHandlerRegistry(_settings()).validate_payload_shape(command_kind, payload)


def test_partial_applies_stable_subset_without_evidence_side_effects(modeling):
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
    assert "operation_plan" not in result
    assert status == {"bad": "failed", "dependent": "blocked", "good": "applied"}
    assert len(rdf.deltas) == 1
    assert db.scalar(select(func.count(EvidenceReferenceModel.id))) == 0
    resource_iri = next(
        item["resource_outputs"]["resource_iri"]
        for item in result["items"]
        if item["client_item_id"] == "good"
    )
    assert resource_iri


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


def test_rule_only_apply_is_retired_without_side_effects(modeling):
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
    assert result["attempt_status"] == "validation_failed"
    assert any("Unsupported Modeling command" in str(f) for f in result["findings"])
    assert db.scalar(select(func.count(SemanticRuleModel.id))) == 0
    assert db.scalar(select(func.count(SemanticRuleDefinitionModel.id))) == 0
    assert ModelingWorkspaceVersionService(db, service.settings).version_for(ONTOLOGY_ID) == version


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


def test_node_target_shape_passes_validation_when_data_satisfies_it(modeling):
    """D2: a Shape command is validated with the shapes graph over the data
    candidate, so a satisfied constraint on a real focus node is accepted
    (Round 1 rejected every ``target_node_iri`` shape with ``min_count>=1``).
    """
    _service, db, _rdf, session_id, lease, version = modeling
    rdf = PersistentFakeRdfStore()
    service = ModelingBatchService(db, _settings(), rdf)  # type: ignore[arg-type]
    schema = [
        _item(
            "customer-class",
            command_kind="create_class",
            payload={"class_id": "customer", "name": "Customer"},
        ),
        _item(
            "customer-email",
            command_kind="create_property",
            depends_on=["customer-class"],
            payload={
                "class_id": "customer",
                "datatype": "string",
                "name": "email",
                "property_id": "email",
            },
        ),
        _item(
            "customer-entity",
            command_kind="create_entity",
            depends_on=["customer-class", "customer-email"],
            payload={
                "class_iri_or_legacy_id": "customer",
                "entity_id": "alice",
                "label": "Alice",
                "properties": {"email": "alice@example.com"},
            },
        ),
    ]
    applied = service.submit(
        session_id,
        _request(
            version,
            schema,
            batch="d2-schema",
            key="d2-schema-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]
    next_version = applied["workspace"]["after_version"]

    shape = ModelingItemInput(
        client_item_id="alice-shape",
        command_kind="create_shape",
        payload={
            "shape_id": "alice-email-shape",
            "target_node_iri": "https://r004.test/resource/entity/alice",
            "constraints": [{"path_id": "email", "min_count": 1}],
        },
    )
    result = service.submit(
        session_id,
        _request(
            next_version,
            [shape],
            batch="d2-shape",
            key="d2-shape-dry-run",
        ),
    )

    assert result["attempt_status"] == "validated", result["findings"]
    assert not [finding for finding in result["findings"] if finding["blocking"]]
    # dry_run stays side-effect free beyond the schema apply above.
    assert len(rdf.deltas) == 1


def test_shape_target_conflicts_are_typed_and_locatable_findings(modeling):
    """D5/D6: Shape target conflicts surface as machine-readable findings with
    per-field paths instead of an escaping exception."""
    service, _db, _rdf, session_id, _lease, version = modeling

    combined = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "combined-target",
                    command_kind="create_shape",
                    payload={
                        "shape_id": "combined",
                        "target_class_id": "customer",
                        "target_node_iri": "https://r004.test/resource/entity/alice",
                        "constraints": [{"path_id": "email", "min_count": 1}],
                    },
                )
            ],
            batch="d6-combined",
            key="d6-combined",
        ),
    )
    finding = next(
        finding
        for finding in combined["findings"]
        if finding["code"] == "shape_target_conflict"
    )
    assert finding["blocking"] is True
    assert finding["scope"] == "item"
    assert finding["client_item_ids"] == ["combined-target"]
    assert finding["path"] == [
        "items",
        0,
        "payload",
        "target_class_id",
        "target_node_iri",
    ]

    blank = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "blank-target",
                    command_kind="create_shape",
                    payload={"shape_id": "blank", "constraints": []},
                )
            ],
            batch="d5-blank",
            key="d5-blank",
        ),
    )
    blank_finding = next(
        finding
        for finding in blank["findings"]
        if finding["code"] == "shape_target_conflict"
    )
    assert blank_finding["client_item_ids"] == ["blank-target"]
    assert blank_finding["path"] == [
        "items",
        0,
        "payload",
        "target_class_id",
        "target_node_iri",
        "target_subjects_of_iri",
    ]


def test_class_membership_conflict_is_a_typed_and_locatable_finding(modeling):
    """D5: the legacy-scalar vs ``class_iris`` mismatch is a 4xx-grade typed
    finding, never an escaping exception."""
    service, _db, _rdf, session_id, _lease, version = modeling

    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "mismatch",
                    command_kind="create_entity",
                    payload={
                        "class_iri_or_legacy_id": "customer",
                        "class_iris": ["vip"],
                        "label": "Alice",
                    },
                )
            ],
            batch="d5-membership",
            key="d5-membership",
        ),
    )

    finding = next(
        finding
        for finding in result["findings"]
        if finding["code"] == "class_membership_conflict"
    )
    assert finding["blocking"] is True
    assert finding["client_item_ids"] == ["mismatch"]
    assert finding["path"] == [
        "items",
        0,
        "payload",
        "class_iri_or_legacy_id",
        "class_iris",
    ]


def test_update_shape_missing_shape_is_a_locatable_finding(modeling):
    """D11: ``update_shape`` against an unknown shape id is a repairable
    ``shape_not_found`` finding instead of a silent upsert."""
    service, db, rdf, session_id, _lease, version = modeling
    shape = ModelingItemInput(
        client_item_id="typo-shape",
        command_kind="update_shape",
        payload={
            "shape_id": "no-such-shape",
            "target_class_id": "customer",
            "constraints": [{"path_id": "email", "min_count": 1}],
        },
    )

    result = service.submit(session_id, _request(version, [shape]))

    assert result["attempt_status"] == "validation_failed"
    finding = next(
        finding
        for finding in result["findings"]
        if finding["code"] == "shape_not_found"
    )
    assert finding["blocking"] is True
    assert finding["client_item_ids"] == ["typo-shape"]
    assert finding["path"] == ["items", 0, "payload", "shape_id"]
    assert rdf.deltas == []
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_shacl_violation_finding_names_focus_node_and_result_path(modeling):
    """D8: the ``shacl_violation`` finding carries the report projection
    (focus node, result path, source shape) so the caller can repair it."""
    _service, db, _rdf, session_id, lease, version = modeling
    rdf = PersistentFakeRdfStore()
    service = ModelingBatchService(db, _settings(), rdf)  # type: ignore[arg-type]
    applied = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "workflow-class",
                    command_kind="create_class",
                    payload={"class_id": "workflow", "name": "Workflow"},
                ),
                _item(
                    "workflow-key",
                    command_kind="create_property",
                    depends_on=["workflow-class"],
                    payload={
                        "class_id": "workflow",
                        "datatype": "string",
                        "name": "workflow key",
                        "property_id": "workflowKey",
                    },
                ),
                _item(
                    "workflow-key-shape",
                    command_kind="create_shape",
                    depends_on=["workflow-class", "workflow-key"],
                    payload={
                        "shape_id": "workflow-key-shape",
                        "target_class_id": "workflow",
                        "constraints": [
                            {"path_id": "workflowKey", "min_count": 2, "max_count": 2}
                        ],
                    },
                ),
            ],
            batch="d8-schema",
            key="d8-schema-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]

    violating = service.submit(
        session_id,
        _request(
            applied["workspace"]["after_version"],
            [
                _item(
                    "violating-entity",
                    command_kind="create_entity",
                    payload={
                        "class_iri_or_legacy_id": "workflow",
                        "entity_id": "broken",
                        "label": "Broken",
                        "properties": {"workflowKey": "only-one"},
                    },
                )
            ],
            batch="d8-violating",
            key="d8-violating",
        ),
    )

    finding = next(
        finding
        for finding in violating["findings"]
        if finding["code"] == "shacl_violation"
    )
    assert finding["blocking"] is True
    assert finding["client_item_ids"] == ["violating-entity"]
    violations = finding["details"]["violations"]
    assert violations, "expected the report projection on the finding"
    first = violations[0]
    assert first["focus_node"] == "https://r004.test/resource/entity/broken"
    assert first["result_path"] == "https://r004.test/resource/property/workflowKey"
    # The source shape is reported too; for a constraint-level violation it is
    # the property shape (a blank node), so only its presence is contractual.
    assert isinstance(first["source_shape"], str) and first["source_shape"]
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


def test_urn_schema_ids_and_bare_string_datatype_validate_in_one_principal_dry_run(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    class_id = "urn:m4:Workflow"
    property_id = "urn:m4:workflowKey"
    shape_id = "urn:m4:WorkflowShape"
    items = [
        _item(
            "workflow-class",
            command_kind="create_class",
            payload={"class_id": class_id, "name": "Workflow"},
        ),
        _item(
            "workflow-key",
            command_kind="create_property",
            depends_on=["workflow-class"],
            payload={
                "class_id": class_id,
                "datatype": "string",
                "name": "workflow key",
                "property_id": property_id,
            },
        ),
        _item(
            "workflow-shape",
            command_kind="create_shape",
            depends_on=["workflow-class", "workflow-key"],
            payload={
                "constraints": [{"datatype": "string", "min_count": 1, "path_id": property_id}],
                "shape_id": shape_id,
                "target_class_id": class_id,
            },
        ),
    ]

    result = service.submit(session_id, _request(version, items, batch="urn-schema-batch"))

    assert result["mode"] == "dry_run"
    assert result["attempt_status"] == "validated"
    assert not [finding for finding in result["findings"] if finding["blocking"]]


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
    assert "unsupported_command_kind" in {finding["code"] for finding in result["findings"]}
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
    # Custom shapes sub-graph: the graph the shape endpoint reads back (D1).
    assert rdf.deltas[0].affected_graph_iris() == [
        f"{_settings().semantic_graph_iri_prefix.rstrip('/')}/shapes/{ONTOLOGY_ID}/custom"
    ]


def test_applied_multi_enum_shapes_validate_following_abox_dry_runs(modeling):
    _service, db, _rdf, session_id, lease, version = modeling
    rdf = PersistentFakeRdfStore()
    service = ModelingBatchService(db, _settings(), rdf)  # type: ignore[arg-type]
    schema_items = [
        _item(
            "workflow-class",
            command_kind="create_class",
            payload={"class_id": "workflow", "name": "Workflow"},
        ),
        _item(
            "workflow-status",
            command_kind="create_property",
            depends_on=["workflow-class"],
            payload={
                "class_id": "workflow",
                "datatype": "string",
                "name": "status",
                "property_id": "status",
            },
        ),
        _item(
            "workflow-priority",
            command_kind="create_property",
            depends_on=["workflow-class"],
            payload={
                "class_id": "workflow",
                "datatype": "string",
                "name": "priority",
                "property_id": "priority",
            },
        ),
        _item(
            "workflow-status-shape",
            command_kind="create_shape",
            depends_on=["workflow-class", "workflow-status"],
            payload={
                "shape_id": "workflow-status-shape",
                "target_class_id": "workflow",
                "constraints": [{"enum_values": ["draft", "published"], "path_id": "status"}],
            },
        ),
        _item(
            "workflow-priority-shape",
            command_kind="create_shape",
            depends_on=["workflow-class", "workflow-priority"],
            payload={
                "shape_id": "workflow-priority-shape",
                "target_class_id": "workflow",
                "constraints": [{"enum_values": ["low", "high"], "path_id": "priority"}],
            },
        ),
    ]
    applied = service.submit(
        session_id,
        _request(
            version,
            schema_items,
            batch="enum-schema",
            key="enum-schema-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert applied["attempt_status"] == "applied"
    next_version = applied["workspace"]["after_version"]
    properties = {
        "https://r004.test/resource/property/status": "published",
        "https://r004.test/resource/property/priority": "high",
    }
    allowed = service.submit(
        session_id,
        _request(
            next_version,
            [
                _item(
                    "allowed-workflow",
                    command_kind="create_entity",
                    payload={
                        "class_iri_or_legacy_id": "workflow",
                        "entity_id": "allowed-workflow",
                        "label": "Allowed workflow",
                        "properties": properties,
                    },
                )
            ],
            batch="enum-abox-allowed",
            key="enum-abox-allowed",
        ),
    )
    disallowed = service.submit(
        session_id,
        _request(
            next_version,
            [
                _item(
                    "disallowed-workflow",
                    command_kind="create_entity",
                    payload={
                        "class_iri_or_legacy_id": "workflow",
                        "entity_id": "disallowed-workflow",
                        "label": "Disallowed workflow",
                        "properties": {**properties, "https://r004.test/resource/property/status": "other"},
                    },
                )
            ],
            batch="enum-abox-disallowed",
            key="enum-abox-disallowed",
        ),
    )

    assert allowed["attempt_status"] == "validated"
    assert not [finding for finding in allowed["findings"] if finding["blocking"]]
    assert disallowed["attempt_status"] == "validation_failed"
    assert "shacl_violation" in {finding["code"] for finding in disallowed["findings"]}


def test_bare_entity_property_key_is_absolute_after_dry_run_and_unchanged_apply(modeling):
    service, _db, rdf, session_id, lease, version = modeling
    schema = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "workflow-class",
                    command_kind="create_class",
                    payload={"class_id": "workflow", "name": "Workflow"},
                ),
                _item(
                    "workflow-is-latest",
                    command_kind="create_property",
                    depends_on=["workflow-class"],
                    payload={
                        "class_id": "workflow",
                        "datatype": "boolean",
                        "name": "is latest",
                        "property_id": "is_latest",
                    },
                ),
            ],
            batch="bare-property-schema",
            key="bare-property-schema-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    entity_items = [
        _item(
            "workflow-entity",
            command_kind="create_entity",
            payload={
                "class_iri_or_legacy_id": "workflow",
                "entity_id": "workflow-entity",
                "label": "Workflow entity",
                "properties": {"is_latest": True},
            },
        )
    ]
    entity_version = schema["workspace"]["after_version"]
    dry_run = service.submit(
        session_id,
        _request(
            entity_version,
            entity_items,
            batch="bare-property-entity",
            key="bare-property-entity-dry",
        ),
    )
    applied = service.submit(
        session_id,
        _request(
            entity_version,
            entity_items,
            batch="bare-property-entity",
            key="bare-property-entity-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert schema["attempt_status"] == "applied"
    assert dry_run["attempt_status"] == "validated"
    assert applied["attempt_status"] == "applied"
    predicates = {predicate for _subject, predicate, _object, _graph in rdf.deltas[-1].inserts}
    assert "<https://r004.test/resource/property/is_latest>" in predicates
    assert "<is_latest>" not in predicates


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


def test_apply_keeps_modeling_fact_when_retrieval_rebuild_is_degraded(modeling, monkeypatch):
    service, _db, _rdf, session_id, lease, version = modeling
    calls = []

    class FailingRetrievalCoordinator:
        def __init__(self, session, rdf_store, settings):  # noqa: ANN001, ARG002
            pass

        def rebuild_affected(self, *, affected_graph_iris=(), ontology_ids=()):
            calls.append((list(affected_graph_iris), list(ontology_ids)))
            return [
                {
                    "ontology_id": ONTOLOGY_ID,
                    "write_applied": True,
                    "status": "failed",
                    "warning": "retrieval_index_failed",
                }
            ]

    monkeypatch.setattr(
        "app.services.modeling_batches.SemanticRetrievalCoordinator", FailingRetrievalCoordinator
    )
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
    assert result["retrieval_indexes"][0]["status"] == "failed"
    assert calls == [([], [ONTOLOGY_ID])]


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


@pytest.mark.parametrize("invalid_field", ["source_entity_iri", "relation_type_iri", "target_entity_iri"])
def test_relation_dry_run_rejects_relative_iri_without_side_effects(modeling, invalid_field):
    service, db, rdf, session_id, _lease, version = modeling
    payload = {
        "source_entity_iri": "https://r004.test/resource/entity/source",
        "relation_type_iri": "https://r004.test/resource/relation/depends-on",
        "target_entity_iri": "https://r004.test/resource/entity/target",
    }
    payload[invalid_field] = "same-batch-client-id"
    relation = ModelingItemInput(
        client_item_id="invalid-relative-relation",
        command_kind="create_relation",
        payload=payload,
    )

    result = service.submit(session_id, _request(version, [relation]))

    assert result["attempt_status"] == "validation_failed"
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["code"] == "invalid_command_payload"
    assert finding["message"] == f"{invalid_field} must be an absolute RDF IRI"
    assert finding["client_item_ids"] == ["invalid-relative-relation"]
    assert finding["blocking"] is True
    assert rdf.deltas == []
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None


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


def test_relation_target_replacement_for_same_subject_and_type_is_valid(modeling):
    """R4.0-007 F5/A6: one atomic Batch may delete the old relation statement and
    add a different one on the same multi-valued slot; that is a declared
    replacement, not two writers racing one target."""
    service, _db, _rdf, session_id, _lease, version = modeling
    base = {
        "source_entity_iri": "https://r004.test/resource/entity/workflow-definition",
        "relation_type_iri": "https://r004.test/resource/relation/has-input",
    }
    replacement = [
        ModelingItemInput(
            client_item_id="remove-definition-input-1",
            command_kind="delete_relation",
            payload={**base, "target_entity_iri": "https://r004.test/resource/entity/input-1"},
        ),
        ModelingItemInput(
            client_item_id="add-definition-input-2",
            command_kind="create_relation",
            payload={**base, "target_entity_iri": "https://r004.test/resource/entity/input-2"},
        ),
    ]

    result = service.submit(session_id, _request(version, replacement))

    assert result["attempt_status"] == "validated"
    assert "conflicting_item_effects" not in {
        finding["code"] for finding in result["findings"]
    }
    delta = result["normalized_delta"]
    assert len(delta["deletes"]) == 1 and "input-1" in json.dumps(delta["deletes"][0])
    assert len(delta["inserts"]) == 1 and "input-2" in json.dumps(delta["inserts"][0])


def test_single_value_slot_delete_and_add_still_conflicts(modeling):
    """The multi-valued replacement exemption must not admit single-valued
    last-write-wins: two items rewriting one entity label can still race."""
    service, _db, _rdf, session_id, _lease, version = modeling
    first = ModelingItemInput(
        client_item_id="relabel-a",
        command_kind="update_entity",
        payload={"entity_id": "https://r004.test/resource/entity/customer", "label": "A"},
    )
    second = ModelingItemInput(
        client_item_id="relabel-b",
        command_kind="update_entity",
        payload={"entity_id": "https://r004.test/resource/entity/customer", "label": "B"},
    )

    result = service.submit(session_id, _request(version, [first, second]))

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
    assert "operation_plan" not in first
    retry = service.submit(session_id, payload)

    assert retry["attempt_status"] == "applied"
    assert "operation_plan" not in retry
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
    registry = ModelingCommandHandlerRegistry(_settings())
    if kind.endswith("rule_definition"):
        with pytest.raises(InvalidCommandPayload, match="Unsupported Modeling command"):
            registry.prepare(batch_id="batch", ontology_id=ONTOLOGY_ID, client_item_id=kind, command_kind=kind, payload=payload)
        assert kind not in registry.command_kinds
    else:
        prepared = registry.prepare(batch_id="batch", ontology_id=ONTOLOGY_ID, client_item_id=kind, command_kind=kind, payload=payload)
        assert prepared.command_kind == kind





# ---------------------------------------------------------------------------
# R3.0-009 Round 2: D2 apply-path SHACL scope, D13 deterministic failure and
# recovery exit, D15 same-batch shape refinement.
# ---------------------------------------------------------------------------

CUSTOM_SHAPES_GRAPH = "https://r004.test/graph/shapes/r004-ontology/custom"


class OxigraphLikeRdfStore(PersistentFakeRdfStore):
    """Behaves like the production repository on a never-materialized graph.

    Oxigraph answers 404 for a named graph that was never written and the
    repository turns that into ``RdfStoreUnavailable`` (D13): recovery code
    must decide that a missing optional graph is empty instead of failing the
    observation.
    """

    def __init__(self, *, persist_before_failure: bool) -> None:
        super().__init__()
        self.failures = 0
        self.persist_before_failure = persist_before_failure

    def get_graph(self, graph_iri, _format):
        if not self.graphs.get(graph_iri):
            raise RdfStoreUnavailable(f"graph {graph_iri} does not exists")
        return self.graphs[graph_iri]

    def apply_dataset_delta(self, delta):
        self.failures += 1
        if self.persist_before_failure:
            super().apply_dataset_delta(delta)
        raise RuntimeError("simulated uncertain RDF response")


def _persistent_modeling(modeling):
    """The fixture store drops every delta; apply-path tests need persistence."""
    service, db, _rdf, session_id, lease, version = modeling
    store = PersistentFakeRdfStore()
    return (
        ModelingBatchService(db, _settings(), store),  # type: ignore[arg-type]
        db,
        store,
        session_id,
        lease,
        version,
    )


def _apply_customer_schema(service, session_id, lease, version, *, with_email=True):
    """Apply class + email property + Alice so shapes bind to a real entity."""
    properties = {"email": "alice@example.com"} if with_email else {}
    items = [
        _item(
            "customer-class",
            command_kind="create_class",
            payload={"class_id": "customer", "name": "Customer"},
        ),
        _item(
            "customer-email",
            command_kind="create_property",
            depends_on=["customer-class"],
            payload={
                "class_id": "customer",
                "datatype": "string",
                "name": "email",
                "property_id": "email",
            },
        ),
        _item(
            "alice",
            command_kind="create_entity",
            depends_on=["customer-class", "customer-email"],
            payload={
                "class_iri_or_legacy_id": "customer",
                "entity_id": "alice",
                "label": "Alice",
                "properties": properties,
            },
        ),
    ]
    applied = service.submit(
        session_id,
        _request(
            version,
            items,
            batch="round2-schema",
            key="round2-schema-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]
    return applied["workspace"]["after_version"]


def _shape_item(
    item_id,
    shape_id,
    *,
    target_node_iri,
    constraints,
    command_kind="create_shape",
    depends_on=None,
):
    data = {
        "client_item_id": item_id,
        "command_kind": command_kind,
        "payload": {
            "shape_id": shape_id,
            "target_node_iri": target_node_iri,
            "constraints": constraints,
        },
        "rationale": "Shape constrains a competency-question focus node",
    }
    if depends_on:
        data["depends_on"] = depends_on
    return ModelingItemInput(**data)


def test_node_target_shape_applies_when_data_satisfies_it(modeling):
    """D2 positive: the apply path reads the same data candidate as the
    pre-check, so a satisfied ``sh:targetNode`` constraint is written."""
    service, _db, store, session_id, lease, version = _persistent_modeling(modeling)
    next_version = _apply_customer_schema(service, session_id, lease, version)

    result = service.submit(
        session_id,
        _request(
            next_version,
            [
                _shape_item(
                    "alice-shape",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1}],
                )
            ],
            batch="round2-shape",
            key="round2-shape-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert result["attempt_status"] == "applied", result["findings"]
    assert "alice-email-shape" in store.graphs[CUSTOM_SHAPES_GRAPH]
    assert "minCount" in store.graphs[CUSTOM_SHAPES_GRAPH]


def test_apply_path_still_detects_a_real_target_node_violation(modeling):
    """D2 negative: a violated constraint on the data scope blocks the apply
    and leaves no shape behind."""
    service, _db, store, session_id, lease, version = _persistent_modeling(modeling)
    next_version = _apply_customer_schema(
        service, session_id, lease, version, with_email=False
    )

    result = service.submit(
        session_id,
        _request(
            next_version,
            [
                _shape_item(
                    "alice-shape",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1}],
                )
            ],
            batch="round2-shape-bad",
            key="round2-shape-bad-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert result["attempt_status"] == "validation_failed", result["findings"]
    assert any(
        finding["code"] == "shacl_violation" and finding["blocking"]
        for finding in result["findings"]
    )
    assert CUSTOM_SHAPES_GRAPH not in store.graphs


def test_recovery_observation_treats_a_missing_graph_as_empty(modeling):
    """D13: a never-materialized workspace graph is an empty observation, not
    ``rdf_observation_failed``."""
    service, _db, _rdf, _session_id, _lease, _version = modeling
    consulted: list[str] = []

    class _RepositoryLikeStore(FakeRdfStore):
        def graph_exists(self, graph_iri):
            consulted.append(graph_iri)
            return False

        def get_graph(self, graph_iri, _format):
            raise RdfStoreUnavailable(f"graph {graph_iri} does not exists")

    service.rdf_store = _RepositoryLikeStore()  # type: ignore[assignment]
    attempt = SimpleNamespace(
        operation_plan={
            "delta": {
                "inserts": [["<s:alice>", "<sh:path>", '"email"', CUSTOM_SHAPES_GRAPH]],
                "deletes": [],
            }
        },
        target_snapshot={"graphs": []},
    )

    observed = service._observe_recovery_state(attempt)

    assert observed["state"] == "not_applied", observed
    assert observed.get("reason") != "rdf_observation_failed"
    assert CUSTOM_SHAPES_GRAPH in consulted


def test_apply_failure_recovers_releases_the_fence_and_is_retryable(modeling):
    """D13 end to end: an uncertain apply enters recovery, the observation
    stays readable, bounded reconciliation terminates without side effects and
    releases the write fence so a corrected batch can be applied."""
    service, db, store, session_id, lease, version = _persistent_modeling(modeling)
    next_version = _apply_customer_schema(service, session_id, lease, version)
    failing = OxigraphLikeRdfStore(persist_before_failure=False)
    failing.graphs = dict(store.graphs)
    service.rdf_store = failing  # type: ignore[assignment]
    service.settings = Settings(
        **{**_settings().model_dump(), "modeling_batch_recovery_max_steps": 1}
    )

    shape_items = [
        _shape_item(
            "alice-shape",
            "alice-email-shape",
            target_node_iri="https://r004.test/resource/entity/alice",
            constraints=[{"path_id": "email", "min_count": 1}],
        )
    ]
    first = service.submit(
        session_id,
        _request(
            next_version,
            shape_items,
            batch="round2-uncertain",
            key="round2-uncertain-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert first["attempt_status"] == "recovering", first["findings"]
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is not None

    reconciled = service.submit(
        session_id,
        _request(
            next_version,
            shape_items,
            batch="round2-uncertain",
            key="round2-uncertain-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert reconciled["attempt_status"] == "failed", reconciled["findings"]
    assert reconciled["recovery"]["state"] == "failed_without_side_effects"
    assert reconciled["recovery"]["safe_to_retry"] is True
    assert "rdf_observation_failed" not in json.dumps(reconciled["recovery"], default=str)
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None

    service.rdf_store = store  # type: ignore[assignment]
    retry = service.submit(
        session_id,
        _request(
            next_version,
            shape_items,
            batch="round2-retry",
            key="round2-retry-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert retry["attempt_status"] == "applied", retry["findings"]
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None
    assert "alice-email-shape" in store.graphs[CUSTOM_SHAPES_GRAPH]


def test_same_batch_create_then_update_shape_is_a_declared_refinement(modeling):
    """D15: creating and refining one Shape inside a batch is a declared
    sequence, not two writers racing one target."""
    service, _db, store, session_id, lease, version = _persistent_modeling(modeling)
    next_version = _apply_customer_schema(service, session_id, lease, version)

    result = service.submit(
        session_id,
        _request(
            next_version,
            [
                _shape_item(
                    "alice-shape",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1}],
                ),
                _shape_item(
                    "alice-shape-refined",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1, "max_count": 2}],
                    command_kind="update_shape",
                    depends_on=["alice-shape"],
                ),
            ],
            batch="round2-refine",
            key="round2-refine-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert result["attempt_status"] == "applied", result["findings"]
    assert not [
        finding
        for finding in result["findings"]
        if finding["code"] == "conflicting_item_effects"
    ]
    assert "maxCount" in store.graphs[CUSTOM_SHAPES_GRAPH]


def test_shape_refinement_without_declared_order_stays_a_conflict(modeling):
    """D15 negative: the same pair without a declared order is still rejected."""
    service, db, _store, session_id, lease, version = _persistent_modeling(modeling)
    next_version = _apply_customer_schema(service, session_id, lease, version)

    result = service.submit(
        session_id,
        _request(
            next_version,
            [
                _shape_item(
                    "alice-shape",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1}],
                ),
                _shape_item(
                    "alice-shape-refined",
                    "alice-email-shape",
                    target_node_iri="https://r004.test/resource/entity/alice",
                    constraints=[{"path_id": "email", "min_count": 1, "max_count": 2}],
                    command_kind="update_shape",
                ),
            ],
            batch="round2-refine-unordered",
            key="round2-refine-unordered-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )

    assert result["attempt_status"] == "validation_failed", result["findings"]
    conflicts = [
        finding
        for finding in result["findings"]
        if finding["code"] == "conflicting_item_effects"
    ]
    assert conflicts, result["findings"]
    assert set(conflicts[0]["client_item_ids"]) == {"alice-shape", "alice-shape-refined"}
    assert db.get(OntologyWriteFenceModel, ONTOLOGY_ID) is None
