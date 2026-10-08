"""R3.0-008A G7 semanticValue structural-gate integration tests.

Covers the shared test plan §5 B1-B5 + B7 rejection paths, the S6
create/update round-trip (L2 <-> L3 upgrade/downgrade), and the B6
zero-guess materialization checks — service-level on the Modeling Batch
deterministic validation, following the R3.0-003 precedent
(``test_modeling_batches_relational_mapping.py``). The read-side chain and
authorization behavior live in ``test_r3008a_controlled_value_chain.py``.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef
from sqlalchemy.orm import Session

from app.api.schemas import (
    BuildSessionCreate,
    ModelingBatchSubmit,
    ModelingItemInput,
    OntologyLeaseAcquire,
)
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import GraphWriteResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.ontology_workspace import OntologyWorkspaceService

PROJECT_ID = "r3008a-int-project"
ONTOLOGY_ID = "r3008a-int-ontology"
FOREIGN_ONTOLOGY_ID = "r3008a-int-foreign"
BASE = "https://r3008a-int.test/resource/"
FOREIGN_BASE = "https://r3008a-foreign.test/resource/"
GRAPH = "https://r3008a-int.test/graph/"
OP = f"{BASE}vocab/"
ONTOLOGY_GRAPH = f"{GRAPH}ontology/{ONTOLOGY_ID}"
DATA_GRAPH = f"{GRAPH}ontology/{ONTOLOGY_ID}"
FOREIGN_GRAPH = f"{GRAPH}ontology/{FOREIGN_ONTOLOGY_ID}"

RDF_TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
OWL_CLASS = "<http://www.w3.org/2002/07/owl#Class>"
OWL_DATATYPE_PROPERTY = "<http://www.w3.org/2002/07/owl#DatatypeProperty>"
OWL_OBJECT_PROPERTY = "<http://www.w3.org/2002/07/owl#ObjectProperty>"

ENTITY_PART_SHORTAGE = f"{BASE}entity/part-shortage"
ENTITY_SUPPLY_CHAIN = f"{BASE}entity/supply-chain-issue"
EM_CAUSE_PS = f"{BASE}enum-meaning/em-cause-ps"
EM_STATUS_WP = f"{BASE}enum-meaning/em-status-wp"
TM_WO = f"{BASE}table-mapping/tm-wo"
JM_WO = f"{BASE}join-mapping/jm-wo"
METRIC = f"{BASE}metric/metric-1"


class QuadRdfStore:
    """Line-based fake store that honors both inserts and wildcard deletes.

    Keeps each graph as raw N-Triples lines exactly as emitted by the
    compilers, so predicate-scoped ``?o`` deletes and whole-subject ``?p``
    deletes match the lines the compilers wrote.
    """

    def __init__(self) -> None:
        self.graphs: dict[str, list[str]] = {}

    def graph_exists(self, graph_iri):
        return bool(self.graphs.get(graph_iri))

    def get_graph(self, graph_iri, _format):
        lines = self.graphs.get(graph_iri, [])
        return "\n".join(lines) + ("\n" if lines else "")

    def apply_dataset_delta(self, delta):
        for subject, predicate, obj, graph_iri in delta.deletes:
            lines = self.graphs.get(graph_iri, [])
            if subject == "?s":
                # object-position wildcard delete: no-op here, mirroring the
                # projection semantics the deterministic validation uses
                continue
            if predicate == "?p":
                self.graphs[graph_iri] = [
                    line for line in lines if not line.startswith(f"{subject} ")
                ]
            elif obj == "?o":
                self.graphs[graph_iri] = [
                    line for line in lines if not line.startswith(f"{subject} {predicate} ")
                ]
            else:
                target = f"{subject} {predicate} {obj} ."
                self.graphs[graph_iri] = [
                    line for line in lines if line.strip() != target
                ]
        for subject, predicate, obj, graph_iri in delta.inserts:
            self.graphs.setdefault(graph_iri, []).append(f"{subject} {predicate} {obj} .")
        return GraphWriteResult(
            graph_iri=delta.affected_graph_iris()[0] if delta.affected_graph_iris() else "",
            applied=not delta.is_empty,
            inserted_quad_count=len(delta.inserts),
            deleted_quad_count=len(delta.deletes),
        )


def _settings() -> Settings:
    return Settings(
        semantic_graph_iri_prefix=GRAPH,
        semantic_base_iri=BASE,
        semantic_product_write_mode="rdf_primary",
    )


@pytest.fixture()
def modeling(in_memory_session: Session):
    settings = _settings()
    in_memory_session.add(
        ProjectModel(id=PROJECT_ID, name="R3.0-008A", normalized_label="r3008a")
    )
    ontology = OntologyModel(id=ONTOLOGY_ID, project_id=PROJECT_ID, name="R3.0-008A ontology")
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
    rdf = QuadRdfStore()
    service = ModelingBatchService(in_memory_session, settings, rdf)  # type: ignore[arg-type]
    version = OntologyModelRevisionService(in_memory_session, settings).version_for(
        ONTOLOGY_ID
    )
    return service, in_memory_session, rdf, session_id, lease, version


def _item(item_id: str, command_kind: str, payload: dict, **overrides):
    data = {
        "client_item_id": item_id,
        "command_kind": command_kind,
        "payload": payload,
        "rationale": "R3.0-008A controlled-value fixture",
    }
    data.update(overrides)
    return ModelingItemInput(**data)


def _request(version, items, *, key="attempt-1", batch="batch-1", mode="dry_run", token=None):
    return ModelingBatchSubmit(
        client_batch_id=batch,
        ontology_id=ONTOLOGY_ID,
        idempotency_key=key,
        mode=mode,
        expected_model_revision=version,
        lease_token=token,
        items=items,
    )


def _enum_item(item_id: str, **payload_overrides) -> ModelingItemInput:
    payload = {
        "enum_meaning_id": item_id,
        "name": f"enum {item_id}",
        "property_iri": f"{BASE}property/status",
        "enum_value": "PART_SHORTAGE",
        "business_meaning": "缺料",
        "schema_source": "schema-dump-2026-09-03",
    }
    payload.update(payload_overrides)
    return _item(item_id, "create_enum_meaning", payload)


def _seed_tbox(rdf: QuadRdfStore) -> None:
    lines = [
        f"<{BASE}class/work-order> {RDF_TYPE} {OWL_CLASS} .",
        f"<{BASE}class/delay-reason> {RDF_TYPE} {OWL_CLASS} .",
        f"<{BASE}property/status> {RDF_TYPE} {OWL_DATATYPE_PROPERTY} .",
        f"<{BASE}property/delay-cause> {RDF_TYPE} {OWL_DATATYPE_PROPERTY} .",
        f"<{BASE}property/currency> {RDF_TYPE} {OWL_DATATYPE_PROPERTY} .",
        f"<{BASE}property/work-order-no> {RDF_TYPE} {OWL_DATATYPE_PROPERTY} .",
        f"<{BASE}relation-type/belongs-to> {RDF_TYPE} {OWL_OBJECT_PROPERTY} .",
    ]
    rdf.graphs[ONTOLOGY_GRAPH] = [*rdf.graphs.get(ONTOLOGY_GRAPH, []), *lines]


def _compile_into(rdf: QuadRdfStore, kind: str, payload: dict) -> None:
    from app.services.semantic_command_compiler import compile_command

    compiled = compile_command(kind, {"ontology_id": ONTOLOGY_ID, **payload}, _settings())
    for subject, predicate, obj, graph_iri in compiled.delta.inserts:
        rdf.graphs.setdefault(graph_iri, []).append(f"{subject} {predicate} {obj} .")


def _seed_entities(rdf: QuadRdfStore) -> None:
    _compile_into(
        rdf,
        "create_entity",
        {
            "entity_id": "part-shortage",
            "class_iri_or_legacy_id": f"{BASE}class/delay-reason",
            "label": "缺料",
        },
    )
    _compile_into(
        rdf,
        "create_entity",
        {
            "entity_id": "supply-chain-issue",
            "class_iri_or_legacy_id": f"{BASE}class/delay-reason",
            "label": "供应链问题",
        },
    )


def _seed_mapping_resources(rdf: QuadRdfStore) -> None:
    _compile_into(
        rdf,
        "create_table_mapping",
        {
            "table_mapping_id": "tm-wo",
            "name": "work orders",
            "mapped_class_iri": f"{BASE}class/work-order",
            "table_name": "service.work_orders",
            "column_mappings": [
                {
                    "property_iri": f"{BASE}property/work-order-no",
                    "column": "work_order_no",
                    "role": "business_key",
                },
                {"property_iri": f"{BASE}property/status", "column": "status"},
            ],
            "schema_source": "schema-dump-2026-09-03",
        },
    )
    _compile_into(
        rdf,
        "create_join_mapping",
        {
            "join_mapping_id": "jm-wo",
            "name": "wo delay",
            "relation_type_iri": f"{BASE}relation-type/belongs-to",
            "join_direction": "forward",
            "join_path": [
                {
                    "from_table": "service.work_orders",
                    "to_table": "service.work_orders",
                    "from_columns": ["work_order_no"],
                    "to_columns": ["work_order_no"],
                }
            ],
            "schema_source": "schema-dump-2026-09-03",
        },
    )
    _compile_into(
        rdf,
        "create_metric_definition",
        {
            "metric_id": "metric-1",
            "name": "delay count",
            "grain": [f"{BASE}property/status"],
            "time_field": f"{BASE}property/status",
            "measure_property_iri": f"{BASE}property/status",
            "aggregation": "count",
            "filters": [],
            "null_value_rule": "none",
            "denominator_rule": "none",
            "schema_source": "schema-dump-2026-09-03",
        },
    )


def _seed_enum_meanings(rdf: QuadRdfStore) -> None:
    for item_id, property_name, enum_value in (
        ("em-cause-ps", "delay-cause", "PART_SHORTAGE"),
        ("em-status-wp", "status", "WAITING_PARTS"),
    ):
        _compile_into(
            rdf,
            "create_enum_meaning",
            {
                "enum_meaning_id": item_id,
                "name": f"enum {item_id}",
                "property_iri": f"{BASE}property/{property_name}",
                "enum_value": enum_value,
                "business_meaning": "缺料",
                "semantic_value": ENTITY_PART_SHORTAGE,
                "schema_source": "schema-dump-2026-09-03",
            },
        )


def _codes(result):
    return {finding["code"] for finding in result["findings"]}


def _findings(result, code):
    return [finding for finding in result["findings"] if finding["code"] == code]


# ---------------------------------------------------------------------------
# B1 / B2 — G7-a target existence (missing / cross topology)
# ---------------------------------------------------------------------------


def test_b1_missing_target_is_blocked_for_create_and_update(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)

    created = service.submit(
        session_id,
        _request(
            version,
            [_enum_item("em-1", semantic_value=f"{BASE}entity/never-created")],
        ),
    )
    assert created["attempt_status"] == "validation_failed"
    reference = _findings(created, "invalid_resource_reference")
    assert any(finding["path"] == ["payload", "semantic_value"] for finding in reference)

    _seed_entities(rdf)
    _seed_enum_meanings(rdf)
    updated = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "update-em",
                    "update_enum_meaning",
                    {
                        "enum_meaning_id": "em-cause-ps",
                        "semantic_value": f"{BASE}entity/never-created",
                    },
                )
            ],
            key="attempt-2",
            batch="batch-2",
        ),
    )
    assert updated["attempt_status"] == "validation_failed"
    reference = _findings(updated, "invalid_resource_reference")
    assert any(finding["path"] == ["payload", "semantic_value"] for finding in reference)


def test_b2_cross_topology_target_is_blocked(modeling):
    """A node that exists only in another Ontology's graph stays invisible in
    the dual-graph merged view and is rejected in the same B1 form."""
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    foreign_iri = f"{FOREIGN_BASE}entity/part-shortage"
    rdf.graphs[FOREIGN_GRAPH] = [
        f"<{foreign_iri}> {RDF_TYPE} {OWL_CLASS} .",
        f'<{foreign_iri}> <http://www.w3.org/2000/01/rdf-schema#label> "缺料" .',
    ]
    result = service.submit(
        session_id,
        _request(version, [_enum_item("em-1", semantic_value=foreign_iri)]),
    )
    assert result["attempt_status"] == "validation_failed"
    reference = _findings(result, "invalid_resource_reference")
    assert any(finding["path"] == ["payload", "semantic_value"] for finding in reference)
    assert "does not reference an existing" in reference[0]["message"]


# ---------------------------------------------------------------------------
# B3 — G7-b non-mapping resource type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target_iri",
    [EM_CAUSE_PS, TM_WO, JM_WO, METRIC],
    ids=["enum-meaning", "table-mapping", "join-mapping", "metric-definition"],
)
def test_b3_mapping_resource_type_targets_are_blocked(modeling, target_iri):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    _seed_mapping_resources(rdf)
    _seed_enum_meanings(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [_enum_item("em-new", semantic_value=target_iri, enum_value="OTHER_CODE")],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    reference = _findings(result, "invalid_resource_reference")
    assert any(
        finding["path"] == ["payload", "semantic_value"]
        and "must reference a non-mapping" in finding["message"]
        for finding in reference
    )


def test_b3_self_reference_is_blocked(modeling):
    """semanticValue pointing at the EnumValueMeaning itself (the expressible
    same-RDF-subject mixing form) is rejected by G7-b on the same-batch
    projection."""
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [_enum_item("em-self", semantic_value=f"{BASE}enum-meaning/em-self")],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    reference = _findings(result, "invalid_resource_reference")
    assert any(
        finding["path"] == ["payload", "semantic_value"]
        and "must reference a non-mapping" in finding["message"]
        for finding in reference
    )


# ---------------------------------------------------------------------------
# B4 — payload shape (compiler) + in-graph multi-value residue (G7-c)
# ---------------------------------------------------------------------------


def test_b4_non_string_payload_is_rejected_at_compile_layer(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    result = service.submit(
        session_id,
        _request(version, [_enum_item("em-1", semantic_value=["a", "b"])]),
    )
    assert result["attempt_status"] == "validation_failed"
    assert "invalid_command_payload" in _codes(result)


def test_b4_in_graph_multi_value_residue_is_rejected(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    # direct-write residue: one EnumValueMeaning with two semanticValue objects
    rdf.graphs[ONTOLOGY_GRAPH].extend(
        [
            f"<{EM_CAUSE_PS}> {RDF_TYPE} <{OP}EnumValueMeaning> .",
            f"<{BASE}enum-meaning/em-cause-ps> <{OP}mappedProperty> "
            f"<{BASE}property/delay-cause> .",
            f"<{BASE}enum-meaning/em-cause-ps> <{OP}enumValue> \"PART_SHORTAGE\" .",
            f"<{BASE}enum-meaning/em-cause-ps> <{OP}semanticValue> <{ENTITY_PART_SHORTAGE}> .",
            f"<{BASE}enum-meaning/em-cause-ps> <{OP}semanticValue> <{ENTITY_SUPPLY_CHAIN}> .",
        ]
    )
    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "update-em",
                    "update_enum_meaning",
                    {"enum_meaning_iri": EM_CAUSE_PS, "business_meaning": "缺料（更新）"},
                )
            ],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    reference = _findings(result, "invalid_resource_reference")
    assert any(finding["path"] == ["payload", "semantic_value"] for finding in reference)
    assert reference[0]["client_item_ids"] == ["update-em"]


# ---------------------------------------------------------------------------
# B5 — G7-d dangling protection
# ---------------------------------------------------------------------------


def test_b5_deleting_pointed_entity_is_blocked(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    _seed_enum_meanings(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("del-entity", "delete_entity", {"entity_iri": ENTITY_PART_SHORTAGE})],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    dangling = _findings(result, "semantic_value_dangling")
    assert dangling
    assert dangling[0]["client_item_ids"] == ["del-entity"]


def test_b5_same_batch_delete_and_reference_is_blocked(modeling):
    """Deleting the L3 node and creating an enum pointing at it in one batch is
    rejected (here by the generic conflicting-item-effects gate, which fires
    before G7; either gate blocks the apply)."""
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item("del-entity", "delete_entity", {"entity_iri": ENTITY_PART_SHORTAGE}),
                _enum_item("em-1", semantic_value=ENTITY_PART_SHORTAGE),
            ],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    blocking = [
        finding
        for finding in result["findings"]
        if finding["code"] in {"conflicting_item_effects", "invalid_resource_reference", "semantic_value_target_missing"}
    ]
    assert blocking
    mentioned = {item_id for finding in blocking for item_id in finding["client_item_ids"]}
    assert mentioned == {"del-entity", "em-1"} or any(
        finding["path"] == ["payload", "semantic_value"] for finding in blocking
    )


def test_b5_deleting_unpointed_entity_passes(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    _seed_enum_meanings(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [_item("del-entity", "delete_entity", {"entity_iri": ENTITY_SUPPLY_CHAIN})],
        ),
    )
    assert result["attempt_status"] == "validated", result["findings"]


# ---------------------------------------------------------------------------
# B7 — G2 view conservation
# ---------------------------------------------------------------------------


def test_b7_g2_still_ignores_the_data_graph(modeling):
    """create_enum_meaning property_iri pointing at a data-graph entity stays
    invisible to the ontology-graph-only G2 view (the dual-graph G7 view did
    not leak into G2-G6)."""
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    result = service.submit(
        session_id,
        _request(version, [_enum_item("em-1", property_iri=ENTITY_PART_SHORTAGE)]),
    )
    assert result["attempt_status"] == "validation_failed"
    reference = _findings(result, "invalid_resource_reference")
    assert any(finding["path"] == ["payload", "property_iri"] for finding in reference)


# ---------------------------------------------------------------------------
# S6 — create/update round-trip (L2 <-> L3)
# ---------------------------------------------------------------------------


def test_s6_semantic_value_roundtrip(modeling):
    service, _db, rdf, session_id, lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)

    # L2 create without semantic_value, then upgrade via update
    applied = service.submit(
        session_id,
        _request(
            version,
            [_enum_item("em-1", enum_value="WAITING_PARTS")],
            key="attempt-apply",
            batch="batch-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]

    upgraded = service.submit(
        session_id,
        _request(
            applied["workspace"]["after_version"],
            [
                _item(
                    "update-em",
                    "update_enum_meaning",
                    {"enum_meaning_id": "em-1", "semantic_value": ENTITY_PART_SHORTAGE},
                )
            ],
            key="attempt-up",
            batch="batch-up",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert upgraded["attempt_status"] == "applied", upgraded["findings"]
    ontology_graph = Graph().parse(data=rdf.get_graph(ONTOLOGY_GRAPH, "turtle"), format="turtle")
    assert (
        URIRef(f"{BASE}enum-meaning/em-1"),
        URIRef(f"{OP}semanticValue"),
        URIRef(ENTITY_PART_SHORTAGE),
    ) in ontology_graph

    # replace with another target, then clear back down to L2
    replaced = service.submit(
        session_id,
        _request(
            upgraded["workspace"]["after_version"],
            [
                _item(
                    "update-em",
                    "update_enum_meaning",
                    {"enum_meaning_id": "em-1", "semantic_value": ENTITY_SUPPLY_CHAIN},
                )
            ],
            key="attempt-replace",
            batch="batch-replace",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert replaced["attempt_status"] == "applied", replaced["findings"]
    ontology_graph = Graph().parse(data=rdf.get_graph(ONTOLOGY_GRAPH, "turtle"), format="turtle")
    assert (
        URIRef(f"{BASE}enum-meaning/em-1"),
        URIRef(f"{OP}semanticValue"),
        URIRef(ENTITY_SUPPLY_CHAIN),
    ) in ontology_graph

    cleared = service.submit(
        session_id,
        _request(
            replaced["workspace"]["after_version"],
            [
                _item(
                    "update-em",
                    "update_enum_meaning",
                    {"enum_meaning_id": "em-1", "semantic_value": None},
                )
            ],
            key="attempt-clear",
            batch="batch-clear",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert cleared["attempt_status"] == "applied", cleared["findings"]
    ontology_graph = Graph().parse(data=rdf.get_graph(ONTOLOGY_GRAPH, "turtle"), format="turtle")
    subject = URIRef(f"{BASE}enum-meaning/em-1")
    assert not list(ontology_graph.objects(subject, URIRef(f"{OP}semanticValue")))
    # downgrade is not destruction: the L2 fields survive the clear
    assert str(ontology_graph.value(subject, URIRef(f"{OP}enumValue"))) == "WAITING_PARTS"
    assert str(ontology_graph.value(subject, URIRef(f"{OP}businessMeaning"))) == "缺料"


# ---------------------------------------------------------------------------
# B6 — zero-guess materialization
# ---------------------------------------------------------------------------


def test_b6_no_guess_materialization(modeling):
    service, _db, rdf, session_id, lease, version = modeling
    _seed_tbox(rdf)
    _seed_entities(rdf)
    unconfirmed_code = "UNCONFIRMED_CODE_XYZ"  # appears only in note text

    applied = service.submit(
        session_id,
        _request(
            version,
            [
                _enum_item("em-cause-ps", property_iri=f"{BASE}property/delay-cause"),
                _enum_item(
                    "em-status-wp",
                    enum_value="WAITING_PARTS",
                ),
            ],
            key="attempt-apply",
            batch="batch-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]

    ontology_graph = Graph().parse(data=rdf.get_graph(ONTOLOGY_GRAPH, "turtle"), format="turtle")
    enum_subjects = set(
        ontology_graph.subjects(
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            URIRef(f"{OP}EnumValueMeaning"),
        )
    )
    # every EnumValueMeaning traces to an explicit batch command
    assert enum_subjects == {
        URIRef(f"{BASE}enum-meaning/em-cause-ps"),
        URIRef(f"{BASE}enum-meaning/em-status-wp"),
    }
    # the unconfirmed candidate code has no EnumValueMeaning and no L3 node
    enum_values = {
        str(value) for value in ontology_graph.objects(None, URIRef(f"{OP}enumValue"))
    }
    assert unconfirmed_code not in enum_values
    data_graph = Graph().parse(data=rdf.get_graph(DATA_GRAPH, "turtle"), format="turtle")
    labels = {
        str(value)
        for value in data_graph.objects(
            None, URIRef("http://www.w3.org/2000/01/rdf-schema#label")
        )
    }
    assert not any(unconfirmed_code in label for label in labels)

    # the command surface offers no auto-fill path: unknown fields are rejected
    rejected = service.submit(
        session_id,
        _request(
            applied["workspace"]["after_version"],
            [_enum_item("em-guess", semantic_value_auto=ENTITY_PART_SHORTAGE)],
            key="attempt-reject",
            batch="batch-reject",
        ),
    )
    assert rejected["attempt_status"] == "validation_failed"
    assert "invalid_command_payload" in _codes(rejected)
