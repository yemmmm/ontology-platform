"""R3.0-003 relational schema mapping Modeling Batch integration gates.

Covers the deterministic G2/G3/G5/G6 validation gates on the merged view
(current ontology graph + same-batch compiled commands), same-batch
dependency ordering, and the apply path for the four new resource families.
"""

from __future__ import annotations

import pytest
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
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService

PROJECT_ID = "r3003-project"
ONTOLOGY_ID = "r3003-ontology"
BASE = "https://r3003.test/resource/"
GRAPH = "https://r3003.test/graph/"
OP = f"{BASE}vocab/"
ONTOLOGY_GRAPH = f"{GRAPH}ontology/{ONTOLOGY_ID}"


class SeededRdfStore:
    """Fake store whose graphs can be pre-seeded with already-applied state."""

    def __init__(self) -> None:
        self.deltas = []
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


def _settings() -> Settings:
    return Settings(
        semantic_graph_iri_prefix=GRAPH,
        semantic_base_iri=BASE,
        semantic_product_write_mode="rdf_primary",
    )


@pytest.fixture()
def modeling(in_memory_session: Session):
    settings = _settings()
    in_memory_session.add(ProjectModel(id=PROJECT_ID, name="R3.0-003", normalized_label="r3003"))
    ontology = OntologyModel(id=ONTOLOGY_ID, project_id=PROJECT_ID, name="R3.0-003 ontology")
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
    rdf = SeededRdfStore()
    service = ModelingBatchService(in_memory_session, settings, rdf)  # type: ignore[arg-type]
    version = ModelingWorkspaceVersionService(in_memory_session, settings).version_for(ONTOLOGY_ID)
    return service, in_memory_session, rdf, session_id, lease, version


def _item(item_id: str, command_kind: str, payload: dict, **overrides):
    data = {
        "client_item_id": item_id,
        "command_kind": command_kind,
        "payload": payload,
        "rationale": "Relational schema mapping fixture",
        "evidence": [
            {"document_name": "schema-ddl.md", "excerpt": f"{item_id} mapping is grounded."}
        ],
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


def _table_mapping_item(item_id, *, class_id="work-order", table="service.work_orders", columns=None):
    if columns is None:
        columns = [
            {
                "property_iri": f"{BASE}property/work-order-no",
                "column": "work_order_no",
                "role": "business_key",
            },
            {"property_iri": f"{BASE}property/status", "column": "status"},
        ]
    return _item(
        item_id,
        "create_table_mapping",
        {
            "table_mapping_id": item_id,
            "name": f"{table} mapping",
            "mapped_class_iri": f"{BASE}class/{class_id}",
            "table_name": table,
            "column_mappings": columns,
            "schema_source": "schema-dump-2026-08-22",
        },
    )


def _join_mapping_item(item_id, *, relation_id="consumes"):
    return _item(
        item_id,
        "create_join_mapping",
        {
            "join_mapping_id": item_id,
            "name": "work order consumes spare part",
            "relation_type_iri": f"{BASE}relation-type/{relation_id}",
            "join_direction": "forward",
            "join_path": [
                {
                    "from_table": "service.work_orders",
                    "to_table": "service.work_order_parts",
                    "from_columns": ["work_order_no"],
                    "to_columns": ["work_order_no"],
                },
                {
                    "from_table": "service.work_order_parts",
                    "to_table": "service.spare_parts",
                    "from_columns": ["part_id"],
                    "to_columns": ["id"],
                },
            ],
            "schema_source": "schema-dump-2026-08-22",
        },
    )


def _seed_tbox(rdf: SeededRdfStore) -> None:
    """Pre-seed TBox types: two classes, one relation type, properties."""
    rdf_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
    owl_class = "<http://www.w3.org/2002/07/owl#Class>"
    owl_object_property = "<http://www.w3.org/2002/07/owl#ObjectProperty>"
    owl_datatype_property = "<http://www.w3.org/2002/07/owl#DatatypeProperty>"
    lines = [
        f"<{BASE}class/work-order> {rdf_type} {owl_class} .",
        f"<{BASE}class/spare-part> {rdf_type} {owl_class} .",
        f"<{BASE}relation-type/consumes> {rdf_type} {owl_object_property} .",
        f"<{BASE}property/work-order-no> {rdf_type} {owl_datatype_property} .",
        f"<{BASE}property/status> {rdf_type} {owl_datatype_property} .",
        f"<{BASE}property/reported-at> {rdf_type} {owl_datatype_property} .",
        f"<{BASE}property/repair-duration> {rdf_type} {owl_datatype_property} .",
        f"<{BASE}property/part-count> {rdf_type} {owl_datatype_property} .",
        f"<{BASE}property/part-id> {rdf_type} {owl_datatype_property} .",
    ]
    rdf.graphs[ONTOLOGY_GRAPH] = "\n".join(lines) + "\n"


def _seed_table_and_join(rdf: SeededRdfStore) -> None:
    """Pre-seed applied table mappings + one join via the real compilers."""
    from app.services.semantic_command_compiler import compile_command

    settings = _settings()
    table = compile_command(
        "create_table_mapping",
        {
            "ontology_id": ONTOLOGY_ID,
            "table_mapping_id": "tm-applied",
            "name": "applied work order table",
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
            "schema_source": "schema-dump-2026-08-22",
        },
        settings,
    )
    second = compile_command(
        "create_table_mapping",
        {
            "ontology_id": ONTOLOGY_ID,
            "table_mapping_id": "tm-applied-parts",
            "name": "applied parts table",
            "mapped_class_iri": f"{BASE}class/spare-part",
            "table_name": "service.spare_parts",
            "column_mappings": [
                {
                    "property_iri": f"{BASE}property/part-id",
                    "column": "id",
                    "role": "business_key",
                },
            ],
            "schema_source": "schema-dump-2026-08-22",
        },
        settings,
    )
    join = compile_command(
        "create_join_mapping",
        {
            "ontology_id": ONTOLOGY_ID,
            "join_mapping_id": "jm-applied",
            "name": "applied join",
            "relation_type_iri": f"{BASE}relation-type/consumes",
            "join_direction": "forward",
            "join_path": [
                {
                    "from_table": "service.work_orders",
                    "to_table": "service.spare_parts",
                    "from_columns": ["work_order_no"],
                    "to_columns": ["id"],
                }
            ],
            "schema_source": "schema-dump-2026-08-22",
        },
        settings,
    )
    for compiled in (table, second, join):
        for subject, predicate, obj, graph_iri in compiled.delta.inserts:
            rdf.graphs[graph_iri] = rdf.graphs.get(graph_iri, "") + (
                f"{subject} {predicate} {obj} .\n"
            )


def _codes(result):
    return {finding["code"] for finding in result["findings"]}


def test_same_batch_class_then_table_mapping_passes(modeling):
    """G2 on the merged view: a class created in the same batch satisfies
    mapped_class_iri without any store round-trip."""
    service, _db, _rdf, session_id, _lease, version = modeling
    items = [
        _item(
            "class-wo",
            "create_class",
            {"class_id": "work-order", "name": "Work Order"},
        ),
        _table_mapping_item("tm-1"),
    ]
    result = service.submit(session_id, _request(version, items))
    assert result["attempt_status"] == "validated", result["findings"]
    assert result["items"][1]["resource_outputs"]


def test_g2_missing_class_reference_is_blocked(modeling):
    service, _db, _rdf, session_id, _lease, version = modeling
    result = service.submit(
        session_id,
        _request(version, [_table_mapping_item("tm-1", class_id="missing-class")]),
    )
    assert result["attempt_status"] == "validation_failed"
    assert "invalid_resource_reference" in _codes(result)
    paths = [
        finding["path"]
        for finding in result["findings"]
        if finding["code"] == "invalid_resource_reference"
    ]
    assert ["payload", "mapped_class_iri"] in paths


def test_g3_forward_join_closure_with_same_batch_tables(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    items = [
        _table_mapping_item("tm-wo", table="service.work_orders"),
        _table_mapping_item(
            "tm-wop",
            class_id="spare-part",
            table="service.work_order_parts",
            columns=[
                {
                    "property_iri": f"{BASE}property/work-order-no",
                    "column": "work_order_no",
                    "role": "business_key",
                },
                {"property_iri": f"{BASE}property/part-id", "column": "part_id"},
            ],
        ),
        _table_mapping_item(
            "tm-parts",
            class_id="spare-part",
            table="service.spare_parts",
            columns=[
                {
                    "property_iri": f"{BASE}property/part-id",
                    "column": "id",
                    "role": "business_key",
                },
            ],
        ),
        _join_mapping_item("jm-1"),
    ]
    result = service.submit(session_id, _request(version, items))
    assert result["attempt_status"] == "validated", result["findings"]


def test_g3_forward_unmapped_table_is_blocked(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    items = [
        _table_mapping_item("tm-wo", table="service.work_orders"),
        _table_mapping_item(
            "tm-parts",
            class_id="spare-part",
            table="service.spare_parts",
            columns=[
                {
                    "property_iri": f"{BASE}property/part-id",
                    "column": "id",
                    "role": "business_key",
                },
            ],
        ),
        _join_mapping_item("jm-1"),
    ]
    result = service.submit(session_id, _request(version, items))
    assert result["attempt_status"] == "validation_failed"
    join_findings = [
        finding for finding in result["findings"] if finding["code"] == "join_path_not_mapped"
    ]
    assert join_findings
    assert join_findings[0]["client_item_ids"] == ["jm-1"]
    assert join_findings[0]["path"] == ["payload", "join_path"]


def test_g3_reverse_delete_table_mapping_blocks_existing_join(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_table_and_join(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "delete-tm",
                    "delete_table_mapping",
                    {"table_mapping_id": "tm-applied"},
                )
            ],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    join_findings = [
        finding for finding in result["findings"] if finding["code"] == "join_path_not_mapped"
    ]
    assert join_findings
    assert join_findings[0]["client_item_ids"] == ["delete-tm"]


def test_g3_reverse_column_removal_blocks_existing_join(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_table_and_join(rdf)
    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "update-tm",
                    "update_table_mapping",
                    {
                        "table_mapping_id": "tm-applied",
                        "column_mappings": [
                            {
                                "property_iri": f"{BASE}property/work-order-no",
                                "column": "renamed_no",
                                "role": "business_key",
                            },
                        ],
                    },
                )
            ],
        ),
    )
    assert result["attempt_status"] == "validation_failed"
    assert "join_path_not_mapped" in _codes(result)


def test_g3_reverse_allows_unrelated_table_mapping_delete(modeling):
    """Deleting a TableMapping no existing JoinMapping references passes."""
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_table_and_join(rdf)
    # A third applied table the join never references.
    from app.services.semantic_command_compiler import compile_command

    compiled = compile_command(
        "create_table_mapping",
        {
            "ontology_id": ONTOLOGY_ID,
            "table_mapping_id": "tm-applied-audit",
            "name": "applied audit table",
            "mapped_class_iri": f"{BASE}class/work-order",
            "table_name": "service.audit_log",
            "column_mappings": [
                {
                    "property_iri": f"{BASE}property/work-order-no",
                    "column": "work_order_no",
                    "role": "business_key",
                },
            ],
            "schema_source": "schema-dump-2026-08-22",
        },
        _settings(),
    )
    for subject, predicate, obj, graph_iri in compiled.delta.inserts:
        rdf.graphs[graph_iri] = rdf.graphs.get(graph_iri, "") + f"{subject} {predicate} {obj} .\n"
    result = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "delete-tm",
                    "delete_table_mapping",
                    {"table_mapping_id": "tm-applied-audit"},
                )
            ],
        ),
    )
    assert result["attempt_status"] == "validated", result["findings"]


def test_g5_enum_uniqueness_within_batch(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    payload = {
        "name": "status open",
        "property_iri": f"{BASE}property/status",
        "enum_value": "OPEN",
        "business_meaning": "工单已创建待处理",
        "schema_source": "schema-dump-2026-08-22",
    }
    items = [
        _item("em-1", "create_enum_meaning", {**payload, "enum_meaning_id": "em-1"}),
        _item("em-2", "create_enum_meaning", {**payload, "enum_meaning_id": "em-2"}),
    ]
    result = service.submit(session_id, _request(version, items))
    assert result["attempt_status"] == "validation_failed"
    duplicates = sorted(
        {
            item_id
            for finding in result["findings"]
            if finding["code"] == "resource_already_exists"
            for item_id in finding["client_item_ids"]
        }
    )
    assert duplicates == ["em-1", "em-2"]


def test_g5_enum_distinct_pairs_pass(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    items = [
        _item(
            "em-1",
            "create_enum_meaning",
            {
                "enum_meaning_id": "em-1",
                "name": "status open",
                "property_iri": f"{BASE}property/status",
                "enum_value": "OPEN",
                "business_meaning": "工单已创建待处理",
                "schema_source": "schema-dump-2026-08-22",
            },
        ),
        _item(
            "em-2",
            "create_enum_meaning",
            {
                "enum_meaning_id": "em-2",
                "name": "status closed",
                "property_iri": f"{BASE}property/status",
                "enum_value": "CLOSED",
                "business_meaning": "工单已完成",
                "schema_source": "schema-dump-2026-08-22",
            },
        ),
    ]
    result = service.submit(session_id, _request(version, items))
    assert result["attempt_status"] == "validated", result["findings"]


def test_g6_create_collision_and_update_not_found(modeling):
    service, _db, rdf, session_id, _lease, version = modeling
    _seed_tbox(rdf)
    _seed_table_and_join(rdf)
    collision = service.submit(
        session_id,
        _request(version, [_table_mapping_item("tm-applied")], key="attempt-2", batch="batch-2"),
    )
    assert collision["attempt_status"] == "validation_failed"
    assert "resource_already_exists" in _codes(collision)

    missing = service.submit(
        session_id,
        _request(
            version,
            [
                _item(
                    "update-tm",
                    "update_table_mapping",
                    {"table_mapping_id": "tm-unknown", "table_name": "service.renamed"},
                )
            ],
            key="attempt-3",
            batch="batch-3",
        ),
    )
    assert missing["attempt_status"] == "validation_failed"
    assert "resource_not_found" in _codes(missing)


def test_g6_create_then_update_across_batches_passes(modeling):
    """Same-batch create+update of one resource is blocked by the generic
    conflicting-item-effects gate; across batches the update finds its
    target in the store and passes G6."""
    service, _db, rdf, session_id, lease, version = modeling
    _seed_tbox(rdf)
    conflict = service.submit(
        session_id,
        _request(
            version,
            [
                _table_mapping_item("tm-new"),
                _item(
                    "update-tm",
                    "update_table_mapping",
                    {"table_mapping_id": "tm-new", "table_name": "service.renamed"},
                    depends_on=["tm-new"],
                ),
            ],
        ),
    )
    assert conflict["attempt_status"] == "validation_failed"
    assert "conflicting_item_effects" in _codes(conflict)

    applied = service.submit(
        session_id,
        _request(
            version,
            [_table_mapping_item("tm-new")],
            key="attempt-apply",
            batch="batch-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]
    updated = service.submit(
        session_id,
        _request(
            applied["workspace"]["after_version"],
            [
                _item(
                    "update-tm",
                    "update_table_mapping",
                    {"table_mapping_id": "tm-new", "table_name": "service.renamed"},
                )
            ],
            key="attempt-2",
            batch="batch-2",
        ),
    )
    assert updated["attempt_status"] == "validated", updated["findings"]


def test_metric_g2_reference_and_full_apply(modeling):
    """Metric references are G2-checked; the apply path writes all four
    resource families through the canonical write pipeline."""
    service, _db, rdf, session_id, lease, version = modeling
    _seed_tbox(rdf)

    bad_metric = _item(
        "metric-bad",
        "create_metric_definition",
        {
            "metric_id": "metric-bad",
            "name": "MTTR",
            "grain": [f"{BASE}property/work-order-no"],
            "time_field": f"{BASE}property/reported-at",
            "measure_property_iri": f"{BASE}property/missing-measure",
            "aggregation": "avg",
            "filters": [],
            "null_value_rule": "未确认，按 0 处理",
            "denominator_rule": "分母口径未与业务确认，暂按全部工单计",
            "schema_source": "schema-dump-2026-08-22",
        },
    )
    rejected = service.submit(
        session_id, _request(version, [bad_metric], key="attempt-reject", batch="batch-reject")
    )
    assert rejected["attempt_status"] == "validation_failed"
    assert "invalid_resource_reference" in _codes(rejected)

    good_items = [
        _table_mapping_item("tm-1"),
        _item(
            "em-1",
            "create_enum_meaning",
            {
                "enum_meaning_id": "em-1",
                "name": "status open",
                "property_iri": f"{BASE}property/status",
                "enum_value": "OPEN",
                "business_meaning": "工单已创建待处理",
                "schema_source": "schema-dump-2026-08-22",
            },
        ),
        _item(
            "jm-1",
            "create_join_mapping",
            {
                "join_mapping_id": "jm-1",
                "name": "wo consumes part",
                "relation_type_iri": f"{BASE}relation-type/consumes",
                "join_direction": "reverse",
                "join_path": [
                    {
                        "from_table": "service.work_orders",
                        "to_table": "service.work_orders",
                        "from_columns": ["work_order_no"],
                        "to_columns": ["work_order_no"],
                    }
                ],
                "schema_source": "schema-dump-2026-08-22",
            },
        ),
        _item(
            "metric-1",
            "create_metric_definition",
            {
                "metric_id": "metric-1",
                "name": "MTTR",
                "description": "平均修复时长",
                "grain": [f"{BASE}property/work-order-no"],
                "time_field": f"{BASE}property/reported-at",
                "measure_property_iri": f"{BASE}property/repair-duration",
                "value_expression": "repairDuration = resolved_at - reported_at，单位小时",
                "aggregation": "avg",
                "filters": [
                    {
                        "field": f"{BASE}property/status",
                        "operator": "eq",
                        "value": "CLOSED",
                    }
                ],
                "null_value_rule": "未确认，按 0 处理",
                "denominator_rule": "分母口径未与业务确认，暂按全部工单计",
                "schema_source": "schema-dump-2026-08-22",
                "semantic_version": "v1",
            },
        ),
    ]
    applied = service.submit(
        session_id,
        _request(
            version,
            good_items,
            key="attempt-apply",
            batch="batch-apply",
            mode="apply_atomic",
            token=lease["lease_token"],
        ),
    )
    assert applied["attempt_status"] == "applied", applied["findings"]
    content = rdf.graphs[ONTOLOGY_GRAPH]
    for fragment in (
        f"<{OP}TableMapping>",
        f"<{OP}JoinMapping>",
        f"<{OP}EnumValueMeaning>",
        f"<{OP}MetricDefinition>",
        f"<{OP}metricMeasure>",
        f"<{OP}nullValueRule>",
    ):
        assert fragment in content
    inserted_subjects = {quad[0] for delta in rdf.deltas for quad in delta.inserts}
    assert f"<{BASE}table-mapping/tm-1>" in inserted_subjects
    assert f"<{BASE}join-mapping/jm-1>" in inserted_subjects
    assert f"<{BASE}enum-meaning/em-1>" in inserted_subjects
    assert f"<{BASE}metric/metric-1>" in inserted_subjects
