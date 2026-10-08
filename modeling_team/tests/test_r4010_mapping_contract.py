"""Focused R4.0-010 Team contracts.

These tests stay at the candidate/Protocol boundary: they prove that the
neutral mapping items survive validation, recursive references are resolved in
the deterministic plan, and governed reads/approval identities retain the
concrete resource kind.  Backend application and live read acceptance belong
to the backend integration suite.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import sys
from pathlib import Path

import pytest

from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_unified_resource_binding_receipt,
    translate_candidate_to_batches,
    validate_unified_resource_binding_receipt,
)
from modeling_team.p2a_protocol_driver import P2AProtocolDriverError, _batch_safe_snapshot
from modeling_team.platform_scope import PlatformScope
from modeling_team.staged_decisions import (
    build_approval_projection,
    build_decision_binding,
    build_identity_binding,
    candidate_item_digest,
    candidate_items_digest,
    unified_identity_issue,
    validate_unified_candidate,
)


def _neutral_mapping_candidate() -> dict:
    return {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": 4,
        "scope": "mapping-contract",
        "constraints": ["rows remain in the source database"],
        "items": [
            {
                "item_id": "class-work-order",
                "item_kind": "class",
                "semantic": {"class_id": "WorkOrder", "label": "Work order"},
            },
            {
                "item_id": "property-status",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "hasStatus",
                    "predicate_kind": "relation",
                    "range": "Status",
                },
            },
            {
                "item_id": "table-work-orders",
                "item_kind": "table_mapping",
                "semantic": {
                    "table_mapping_id": "tm-work-orders",
                    "name": "Work orders table",
                    "mapped_definition": {"definition_ref": "class-work-order"},
                    "table_name": "service.work_orders",
                    "column_mappings": [
                        {"column": "work_order_id", "role": "business_key"},
                        {"column": "status_code", "role": "value"},
                    ],
                    "schema_source": "schema-v1",
                    "mapping_definition": {
                        "source_key": "service-db",
                        "row_grain": "one work order row",
                        "identifiers": [
                            {
                                "columns": ["work_order_id"],
                                "kind": "business",
                                "scope": "service",
                                "property_iri": {"definition_ref": "property-status"},
                            }
                        ],
                    },
                    "semantic_definition": {
                        "semantic_role": "data_mapping",
                        "business_meaning": "Rows identify work orders.",
                    },
                },
            },
            {
                "item_id": "join-work-status",
                "item_kind": "join_mapping",
                "semantic": {
                    "join_mapping_id": "jm-work-status",
                    "name": "Work order status join",
                    "relation_type": {"definition_ref": "property-status"},
                    "join_direction": "forward",
                    "join_path": [
                        {
                            "from_mapping_iri": {"definition_ref": "table-work-orders"},
                            "to_mapping_iri": {"definition_ref": "table-work-orders"},
                            "from_role": "work-order",
                            "to_role": "status",
                            "from_columns": ["status_code"],
                            "to_columns": ["status_code"],
                        }
                    ],
                    "schema_source": "schema-v1",
                    "mapping_definition": {
                        "step_semantics": [
                            {
                                "step_index": 0,
                                "join_type": "left",
                                "cardinality": "many_to_one",
                            }
                        ]
                    },
                },
            },
            {
                "item_id": "enum-status-open",
                "item_kind": "enum_meaning",
                "semantic": {
                    "enum_meaning_id": "em-status-open",
                    "name": "Open status",
                    "property_ref": {"definition_ref": "property-status"},
                    "enum_value": "OPEN",
                    "business_meaning": "The work order is open.",
                    "table_mapping_ref": {"definition_ref": "table-work-orders"},
                    "column": "status_code",
                    "schema_source": "schema-v1",
                },
            },
            {
                "item_id": "metric-work-orders",
                "item_kind": "metric_definition",
                "semantic": {
                    "metric_id": "metric-work-orders",
                    "name": "Work order count",
                    "grain": ["work order"],
                    "time_field": {"definition_ref": "property-status"},
                    "aggregation": "count",
                    "null_value_rule": "unknown",
                    "denominator_rule": "not applicable",
                    "mapping_definition": {
                        "contexts": [
                            {
                                "context_key": "service",
                                "base_mapping_iri": {"definition_ref": "table-work-orders"},
                                "base_role": "work-order",
                                "join_mapping_iris": [{"definition_ref": "join-work-status"}],
                                "property_bindings": [
                                    {
                                        "property_iri": {"definition_ref": "property-status"},
                                        "table_mapping_iri": {"definition_ref": "table-work-orders"},
                                        "role": "work-order",
                                        "column": "status_code",
                                    }
                                ],
                                "counted_identity": None,
                                "conversion_rule_iris": [],
                            }
                        ]
                    },
                },
            },
            {
                "item_id": "relation-work-status",
                "item_kind": "relation",
                "semantic": {
                    "predicate": "hasStatus",
                    "subject": {"definition_ref": "table-work-orders"},
                    "object": {"definition_ref": "enum-status-open"},
                },
            },
        ],
    }


def _active_protocol_facade():
    root = Path(__file__).parents[2]
    path = root / "modeling_team" / "protocol_retrieval_mcp.py"
    spec = importlib.util.spec_from_file_location("r4010_protocol_retrieval_mcp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_mapping_candidate_translation_is_recursive_and_topologically_ordered():
    plan = translate_candidate_to_batches(_neutral_mapping_candidate())

    assert plan["conflicts"] == []
    assert plan["stage_order"] == [
        "class",
        "property",
        "entity",
        "table_mapping",
        "join_mapping",
        "enum_meaning",
        "metric_definition",
        "relation",
    ]
    stages = [batch["stage_kind"] for batch in plan["batches"]]
    assert stages.index("table_mapping") < stages.index("join_mapping")
    assert stages.index("join_mapping") < stages.index("enum_meaning")
    assert stages.index("enum_meaning") < stages.index("metric_definition")
    assert stages.index("metric_definition") < stages.index("relation")
    metric = next(
        item
        for batch in plan["batches"]
        if batch["stage_kind"] == "metric_definition"
        for item in batch["items"]
    )
    contexts = metric["payload"]["mapping_definition"]["contexts"]
    assert contexts[0]["base_mapping_iri"].endswith("/table-mapping/tm-work-orders")
    assert contexts[0]["join_mapping_iris"] == [
        "http://ontology-platform.local/semantic/join-mapping/jm-work-status"
    ]
    assert all(
        "definition_ref" not in str(item)
        for batch in plan["batches"]
        for item in batch["items"]
    )
    assert {entry["resource_kind"] for entry in plan["resource_identities"]} == {
        "table_mapping",
        "join_mapping",
        "enum_meaning",
        "metric",
    }


def test_active_protocol_tool_advertises_and_executes_r4010_translation():
    wrapper = _active_protocol_facade()
    listed = wrapper.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    tools = listed["result"]["tools"]
    translate_tool = next(
        tool for tool in tools if tool["name"] == wrapper.TRANSLATE_CANDIDATE_TOOL_NAME
    )
    assert translate_tool["inputSchema"]["properties"]["requirement_id"]["enum"] == [
        "R2.3-003",
        "R4.0-010",
    ]
    response = wrapper.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": wrapper.TRANSLATE_CANDIDATE_TOOL_NAME,
                "arguments": {"candidate": _neutral_mapping_candidate()},
            },
        }
    )
    assert response is not None
    assert "error" not in response
    plan = response["result"]["structuredContent"]
    assert [batch["stage_kind"] for batch in plan["batches"]] == [
        "class",
        "property",
        "table_mapping",
        "join_mapping",
        "enum_meaning",
        "metric_definition",
        "relation",
    ]


def test_active_translation_uses_host_namespace_for_resource_refs():
    wrapper = _active_protocol_facade()
    base = "https://isolated.example/semantic/"
    response = wrapper.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": wrapper.TRANSLATE_CANDIDATE_TOOL_NAME,
                "arguments": {
                    "candidate": _neutral_mapping_candidate(),
                    "semantic_base_iri": base,
                },
            },
        }
    )
    assert response is not None and "error" not in response
    plan = response["result"]["structuredContent"]
    assert all(
        identity["resource_iri"].startswith(base)
        for identity in plan["resource_identities"]
    )
    table = next(
        item
        for batch in plan["batches"]
        if batch["stage_kind"] == "table_mapping"
        for item in batch["items"]
    )
    assert table["payload"]["mapped_definition_iri"].startswith(base + "class/")


def test_unified_candidate_accepts_mapping_kinds_and_checks_recursive_refs():
    candidate = {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario",
        "candidate_id": "candidate",
        "revision": 1,
        "items": [
            {
                "item_id": "tm",
                "item_kind": "table_mapping",
                "business_meaning": "table mapping",
                "value": {"mapping_definition": {"base": {"definition_ref": "tm"}}},
                "relation_endpoints": None,
                "slice_ids": ["slice"],
                "shared_scope": None,
                "unknowns": [],
            }
        ],
        "explicit_unknowns": [],
    }
    assert validate_unified_candidate(candidate) == ()
    broken = deepcopy(candidate)
    broken["items"][0]["value"]["mapping_definition"]["base"] = {
        "definition_ref": "missing"
    }
    issues = validate_unified_candidate(broken)
    assert issues[0].reason_code == "missing_candidate_reference"


def test_resource_binding_receipt_preserves_kind_and_scope():
    candidate = {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": 1,
        "scope": "mapping",
        "constraints": [],
        "items": [
            {
                "item_id": "existing-table",
                "item_kind": "existing_resource_ref",
                "semantic": {"semantic_id": "tm-old", "resource_kind": "table_mapping"},
            }
        ],
    }
    read_model = {
        "resources": [
            {
                "semantic_id": "tm-old",
                "resource_kind": "table_mapping",
                "resource_iri": "https://platform.test/table-mapping/tm-old",
                "read_evidence": {"source": "governed-read"},
                "project_id": "project",
                "ontology_id": "ontology",
                "model_revision": 1,
            }
        ]
    }
    receipt = build_unified_resource_binding_receipt(
        candidate,
        read_model,
        project_id="project",
        ontology_id="ontology",
        model_revision=1,
    )
    assert receipt["bindings"][0]["resource_kind"] == "table_mapping"
    assert validate_unified_resource_binding_receipt(candidate, receipt) == receipt
    tampered = deepcopy(receipt)
    tampered["bindings"][0]["resource_kind"] = "entity"
    with pytest.raises(ProtocolRetrievalFallbackError):
        validate_unified_resource_binding_receipt(candidate, tampered)


def test_active_resource_binding_tool_adapts_governed_read_envelope():
    candidate = {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": 1,
        "scope": "mapping",
        "constraints": [],
        "items": [
            {
                "item_id": "existing-table",
                "item_kind": "existing_resource_ref",
                "semantic": {"semantic_id": "tm-old", "resource_kind": "table_mapping"},
            }
        ],
    }
    wrapper = _active_protocol_facade()
    iri = "https://platform.test/table-mapping/tm-old"
    response = wrapper.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": wrapper.RESOURCE_BINDING_RECEIPT_TOOL_NAME,
                "arguments": {
                    "candidate": candidate,
                    "read_envelope": {
                        "iri": iri,
                        "label": "Existing table mapping",
                        "ontology_id": "ontology",
                        "model_revision": 1,
                        "assertion_kind": "asserted",
                        "properties": {"mapping_definition": {}},
                    },
                    "scope": {
                        "project_id": "project",
                        "ontology_id": "ontology",
                        "model_revision": 1,
                    },
                },
            },
        }
    )
    assert response is not None and "error" not in response
    receipt = response["result"]["structuredContent"]
    assert receipt["bindings"] == [
        {
            "semantic_id": "tm-old",
            "resource_kind": "table_mapping",
            "resource_iri": iri,
            "read_evidence": {
                "assertion_kind": "asserted",
                "envelope_digest": receipt["bindings"][0]["read_evidence"]["envelope_digest"],
                "model_revision": 1,
            },
            "project_id": "project",
            "ontology_id": "ontology",
            "model_revision": 1,
        }
    ]
    assert validate_unified_resource_binding_receipt(candidate, receipt) == receipt


def test_mapping_identity_binding_is_approval_checked_without_entity_assumption():
    candidate = {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario",
        "candidate_id": "candidate",
        "revision": 1,
        "items": [
            {
                "item_id": "tm",
                "item_kind": "table_mapping",
                "business_meaning": "table",
                "value": {},
                "relation_endpoints": None,
                "slice_ids": ["slice"],
                "shared_scope": None,
                "unknowns": [],
            }
        ],
        "explicit_unknowns": [],
    }
    projection = build_approval_projection(
        task_id="r4-0-010",
        scenario_id="scenario",
        session_id="session",
        client_batch_id="batch",
        ontology_id="ontology",
        candidate_id="candidate",
        candidate_revision=1,
        candidate_digest=candidate_items_digest(candidate["items"]),
        items=[
            {
                "client_item_id": "tm",
                "command_kind": "create_table_mapping",
                "payload": {"table_mapping_id": "tm"},
            }
        ],
        decision_bindings=[
            build_decision_binding(
                command_index=0,
                client_item_id="tm",
                candidate_item_ids=["tm"],
                candidate_revision=1,
                candidate_content_digests={"tm": candidate_item_digest(candidate["items"][0])},
                decision_ids=[],
            )
        ],
        identity_bindings=[
            build_identity_binding(
                candidate_item_id="tm",
                receipt_ref="receipt-1",
                resource_kind="table_mapping",
            )
        ],
    )
    assert unified_identity_issue(
        projection,
        {"tm": candidate["items"][0]},
    ) is None


def test_archival_p2a_snapshot_keeps_mapping_resource_kind():
    detail = {
        "batch_id": "batch",
        "items": [
            {
                "client_item_id": "tm-item",
                "command_kind": "create_table_mapping",
                "payload": {"table_mapping_id": "tm"},
                "resource_outputs": {
                    "resource_id": "tm",
                    "resource_iri": "https://example.test/table-mapping/tm",
                },
            },
            {
                "client_item_id": "metric-item",
                "command_kind": "create_metric_definition",
                "payload": {"metric_id": "metric"},
                "resource_outputs": {
                    "resource_id": "metric",
                    "resource_iri": "https://example.test/metric/metric",
                },
            },
        ],
        "attempts": [],
    }
    snapshot = _batch_safe_snapshot(detail)
    assert snapshot["resource_bindings"] == [
        {
            "client_item_id": "metric-item",
            "resource_id": "metric",
            "resource_kind": "metric",
            "resource_iri": "https://example.test/metric/metric",
        },
        {
            "client_item_id": "tm-item",
            "resource_id": "tm",
            "resource_kind": "table_mapping",
            "resource_iri": "https://example.test/table-mapping/tm",
        },
    ]
    bad = deepcopy(detail)
    bad["items"][0]["resource_outputs"]["resource_kind"] = "entity"
    with pytest.raises(P2AProtocolDriverError, match="resource kind drifted"):
        _batch_safe_snapshot(bad)


class _MappingScopeClient:
    def __init__(self):
        self.calls = []
        self.ontology_ids = ["ontology-a", "ontology-b", "ontology-unrelated"]
        self.references = {}

    def __call__(self, method, path, body, _key):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/api/projects/project/ontologies":
            return 200, [{"id": oid} for oid in self.ontology_ids]
        if method == "PATCH" and path.startswith("/api/ontologies/"):
            ontology_id = path.split("/")[-1]
            self.references[ontology_id] = body["reference_ontology_ids"]
            return 200, {"id": ontology_id, **body}
        raise AssertionError(f"unexpected scope request {method} {path}")


def test_platform_scope_activates_only_selected_mapping_dependencies_and_reuses_scope():
    client = _MappingScopeClient()
    scope = PlatformScope(
        "http://example",
        "mapping-run",
        lambda: ("admin", "admin-id"),
        lambda _key: True,
        client,
    )
    scope.admin_key = "admin"
    scope.project_id = "project"
    scope.ontology_ids = ["ontology-a", "ontology-b", "ontology-unrelated"]
    plan = [
        {"name": "A", "slice_ids": ["slice-a"]},
        {"name": "B", "slice_ids": ["slice-b"]},
        {"name": "Unrelated", "slice_ids": ["slice-unrelated"]},
    ]
    scenario_map = {
        "cross_slice_dependencies": [
            {
                "from_slice": "slice-a",
                "to_slice": "slice-b",
                "direction": "S1 depends on S2",
                "connection_points": ["shared-definition"],
            }
        ]
    }
    selected = scope.apply_mapping_reference_ontologies(
        scenario_map,
        plan,
        dependent_direction="from_slice_depends_on_to_slice",
    )
    assert selected == {"ontology-a": "ontology-a"}
    assert client.references == {"ontology-a": ["ontology-b"]}
    assert scope.apply_mapping_reference_ontologies(
        scenario_map, plan, dependent_direction="from_slice_depends_on_to_slice",
    ) == selected
    assert client.references == {"ontology-a": ["ontology-b"]}
    assert all(method in {"GET", "PATCH"} for method, _, _ in client.calls)
