"""R3.0-003 relational schema mapping command compiler unit tests.

Compile-level checks for the 12 new commands: exact quad shapes, canonical
JSON literals (``json.dumps(..., ensure_ascii=False)``, never the Python
repr path), the compile-time gates G1 (payload shape) / G4 (business_key) /
G7 (DSN/URL rejection), and the secret-scan entry hook.
"""

from __future__ import annotations

import json

import pytest
from rdflib import URIRef
from rdflib.term import Literal

from app.core.config import Settings
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command

BASE = "http://op.local/ns/"
GRAPH = "http://op.local/graph/"
OP = f"{BASE}vocab/"
ONTOLOGY_ID = "ont-1"
ONTOLOGY_GRAPH = f"{GRAPH}ontology/{ONTOLOGY_ID}"
RDF_JSON = "http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON"

SETTINGS = Settings(semantic_base_iri=BASE, semantic_graph_iri_prefix=GRAPH)


def _json_literal(value) -> str:
    return Literal(json.dumps(value, ensure_ascii=False), datatype=URIRef(RDF_JSON)).n3()


def _quads(compiled):
    return compiled.delta.inserts


TABLE_PAYLOAD = {
    "ontology_id": ONTOLOGY_ID,
    "table_mapping_id": "tm-1",
    "name": "工单表映射",
    "mapped_class_iri": f"{BASE}class/WorkOrder",
    "table_name": "service.work_orders",
    "column_mappings": [
        {
            "property_iri": f"{BASE}property/workOrderNo",
            "column": "work_order_no",
            "role": "business_key",
        },
        {"property_iri": f"{BASE}property/status", "column": "status"},
    ],
    "schema_source": "schema-dump-2026-08-22",
    "semantic_version": "v1",
}

JOIN_PAYLOAD = {
    "ontology_id": ONTOLOGY_ID,
    "join_mapping_id": "jm-1",
    "name": "工单关联备件",
    "relation_type_iri": f"{BASE}relation-type/consumes",
    "join_direction": "forward",
    "join_path": [
        {
            "from_table": "service.work_orders",
            "to_table": "service.work_order_parts",
            "from_columns": ["work_order_no"],
            "to_columns": ["work_order_no"],
        },
    ],
    "schema_source": "schema-dump-2026-08-22",
}

ENUM_PAYLOAD = {
    "ontology_id": ONTOLOGY_ID,
    "enum_meaning_id": "em-1",
    "name": "status OPEN",
    "property_iri": f"{BASE}property/status",
    "enum_value": "OPEN",
    "business_meaning": "工单已创建，等待派工",
    "schema_source": "schema-dump-2026-08-22",
}

METRIC_PAYLOAD = {
    "ontology_id": ONTOLOGY_ID,
    "metric_id": "metric-1",
    "name": "MTTR",
    "grain": [f"{BASE}property/workOrderNo"],
    "time_field": f"{BASE}property/reportedAt",
    "measure_property_iri": f"{BASE}property/repairDuration",
    "value_expression": "repairDuration = resolvedAt - reportedAt（小时）",
    "aggregation": "avg",
    "filters": [
        {"field": f"{BASE}property/status", "operator": "eq", "value": "已关闭"}
    ],
    "null_value_rule": "未确认，按 0 处理",
    "denominator_rule": "分母口径未与业务确认，暂按全部工单计",
    "schema_source": "schema-dump-2026-08-22",
}


# ---------------------------------------------------------------------------
# create_* exact quad shapes
# ---------------------------------------------------------------------------


def test_create_table_mapping_exact_quads_and_canonical_json():
    compiled = compile_command("create_table_mapping", TABLE_PAYLOAD, SETTINGS)
    subject = f"<{BASE}table-mapping/tm-1>"
    expected_columns = [
        {
            "property_iri": f"{BASE}property/workOrderNo",
            "column": "work_order_no",
            "role": "business_key",
        },
        {"property_iri": f"{BASE}property/status", "column": "status", "role": "value"},
    ]
    expected = {
        (subject, "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>", f"<{OP}TableMapping>"),
        (subject, f"<{OP}id>", '"tm-1"'),
        (subject, f"<{OP}ontology>", f"<{BASE}ontology/{ONTOLOGY_ID}>"),
        (subject, "<http://www.w3.org/2000/01/rdf-schema#label>", '"工单表映射"'),
        (subject, f"<{OP}schemaSource>", '"schema-dump-2026-08-22"'),
        (subject, f"<{OP}semanticVersion>", '"v1"'),
        (subject, f"<{OP}mappedClass>", f"<{BASE}class/WorkOrder>"),
        (subject, f"<{OP}tableName>", '"service.work_orders"'),
        (subject, f"<{OP}columnMappings>", _json_literal(expected_columns)),
    }
    assert {(s, p, o) for s, p, o, g in _quads(compiled)} == expected
    assert {g for _s, _p, _o, g in _quads(compiled)} == {ONTOLOGY_GRAPH}
    assert compiled.metadata["table_mapping_iri"] == f"{BASE}table-mapping/tm-1"
    assert compiled.object_kind == "table_mapping"


def test_create_join_mapping_exact_quads_and_canonical_json():
    compiled = compile_command("create_join_mapping", JOIN_PAYLOAD, SETTINGS)
    subject = f"<{BASE}join-mapping/jm-1>"
    triples = {(s, p, o) for s, p, o, _g in _quads(compiled)}
    assert (subject, f"<{OP}mappedRelationType>", f"<{BASE}relation-type/consumes>") in triples
    assert (subject, f"<{OP}joinDirection>", '"forward"') in triples
    expected_path = [
        {
            "from_table": "service.work_orders",
            "to_table": "service.work_order_parts",
            "from_columns": ["work_order_no"],
            "to_columns": ["work_order_no"],
        }
    ]
    assert (subject, f"<{OP}joinPath>", _json_literal(expected_path)) in triples
    assert compiled.metadata["join_mapping_iri"] == f"{BASE}join-mapping/jm-1"


def test_create_enum_meaning_exact_quads_preserves_chinese():
    compiled = compile_command("create_enum_meaning", ENUM_PAYLOAD, SETTINGS)
    subject = f"<{BASE}enum-meaning/em-1>"
    triples = {(s, p, o) for s, p, o, _g in _quads(compiled)}
    assert (subject, f"<{OP}mappedProperty>", f"<{BASE}property/status>") in triples
    assert (subject, f"<{OP}enumValue>", '"OPEN"') in triples
    assert (subject, f"<{OP}businessMeaning>", '"工单已创建，等待派工"') in triples
    assert compiled.metadata["enum_meaning_iri"] == f"{BASE}enum-meaning/em-1"


def test_create_metric_definition_exact_quads_and_json_literals():
    compiled = compile_command("create_metric_definition", METRIC_PAYLOAD, SETTINGS)
    subject = f"<{BASE}metric/metric-1>"
    triples = {(s, p, o) for s, p, o, _g in _quads(compiled)}
    assert (subject, f"<{OP}metricGrain>", _json_literal([f"{BASE}property/workOrderNo"])) in triples
    assert (subject, f"<{OP}metricTimeField>", f"<{BASE}property/reportedAt>") in triples
    assert (subject, f"<{OP}metricMeasure>", f"<{BASE}property/repairDuration>") in triples
    assert (subject, f"<{OP}metricAggregation>", '"avg"') in triples
    assert (subject, f"<{OP}nullValueRule>", '"未确认，按 0 处理"') in triples
    assert (
        subject,
        f"<{OP}denominatorRule>",
        '"分母口径未与业务确认，暂按全部工单计"',
    ) in triples
    filters_literal = _json_literal(
        [{"field": f"{BASE}property/status", "operator": "eq", "value": "已关闭"}]
    )
    assert (subject, f"<{OP}metricFilters>", filters_literal) in triples
    # ensure_ascii=False: the raw Chinese characters, not \u escapes, must be
    # stored so the authorization JSON reference extraction stays possible.
    assert "已关闭" in filters_literal and "\\u" not in filters_literal


def test_metric_count_aggregation_allows_missing_measure():
    payload = dict(METRIC_PAYLOAD)
    payload.pop("measure_property_iri")
    payload.pop("value_expression")
    payload["aggregation"] = "count"
    compiled = compile_command("create_metric_definition", payload, SETTINGS)
    triples = {(s, p, o) for s, p, o, _g in _quads(compiled)}
    assert not any(p == f"<{OP}metricMeasure>" for _s, p, _o in triples)
    assert any(o == '"count"' for _s, _p, o in triples)


# ---------------------------------------------------------------------------
# update_* / delete_* shapes
# ---------------------------------------------------------------------------


def test_update_table_mapping_per_predicate_delete_and_insert():
    payload = {
        "ontology_id": ONTOLOGY_ID,
        "table_mapping_id": "tm-1",
        "table_name": "service.renamed",
        "column_mappings": TABLE_PAYLOAD["column_mappings"],
    }
    compiled = compile_command("update_table_mapping", payload, SETTINGS)
    subject = f"<{BASE}table-mapping/tm-1>"
    deletes = {(s, p, o) for s, p, o, _g in compiled.delta.deletes}
    inserts = {(s, p, o) for s, p, o, _g in compiled.delta.inserts}
    assert (subject, f"<{OP}tableName>", "?o") in deletes
    assert (subject, f"<{OP}columnMappings>", "?o") in deletes
    assert (subject, f"<{OP}tableName>", '"service.renamed"') in inserts
    # Only touched predicates produce deletes; untouched ones stay absent.
    assert (subject, f"<{OP}mappedClass>", "?o") not in deletes


def test_update_metric_by_iri_locator():
    payload = {
        "ontology_id": ONTOLOGY_ID,
        "metric_iri": f"{BASE}metric/metric-1",
        "aggregation": "max",
        # Fail-closed: switching to a measure-required aggregation demands
        # the measure reference in the same update payload.
        "measure_property_iri": f"{BASE}property/repairDuration",
        "null_value_rule": "空值按 0 处理，已与业务确认",
        "denominator_rule": "分母口径已确认",
    }
    compiled = compile_command("update_metric_definition", payload, SETTINGS)
    subject = f"<{BASE}metric/metric-1>"
    inserts = {(s, p, o) for s, p, o, _g in compiled.delta.inserts}
    assert (subject, f"<{OP}metricAggregation>", '"max"') in inserts
    assert compiled.metadata["metric_iri"] == f"{BASE}metric/metric-1"


def test_update_metric_empty_rules_rejected_and_measure_required():
    with pytest.raises(InvalidCommandPayload, match="null_value_rule"):
        compile_command(
            "update_metric_definition",
            {"ontology_id": ONTOLOGY_ID, "metric_id": "metric-1", "null_value_rule": ""},
            SETTINGS,
        )
    with pytest.raises(InvalidCommandPayload, match="measure_property_iri"):
        compile_command(
            "update_metric_definition",
            {"ontology_id": ONTOLOGY_ID, "metric_id": "metric-1", "aggregation": "sum"},
            SETTINGS,
        )


def test_delete_commands_by_id_and_iri():
    compiled = compile_command(
        "delete_table_mapping",
        {"ontology_id": ONTOLOGY_ID, "table_mapping_id": "tm-1"},
        SETTINGS,
    )
    assert compiled.delta.deletes == [
        (f"<{BASE}table-mapping/tm-1>", "?p", "?o", ONTOLOGY_GRAPH)
    ]
    compiled = compile_command(
        "delete_join_mapping",
        {"ontology_id": ONTOLOGY_ID, "join_mapping_iri": f"{BASE}join-mapping/jm-9"},
        SETTINGS,
    )
    assert compiled.delta.deletes == [
        (f"<{BASE}join-mapping/jm-9>", "?p", "?o", ONTOLOGY_GRAPH)
    ]
    compiled = compile_command(
        "delete_enum_meaning",
        {"ontology_id": ONTOLOGY_ID, "enum_meaning_id": "em-1"},
        SETTINGS,
    )
    assert compiled.delta.deletes == [
        (f"<{BASE}enum-meaning/em-1>", "?p", "?o", ONTOLOGY_GRAPH)
    ]
    compiled = compile_command(
        "delete_metric_definition",
        {"ontology_id": ONTOLOGY_ID, "metric_id": "metric-1"},
        SETTINGS,
    )
    assert compiled.delta.deletes == [(f"<{BASE}metric/metric-1>", "?p", "?o", ONTOLOGY_GRAPH)]


def test_delete_requires_locator():
    with pytest.raises(InvalidCommandPayload, match="table_mapping_id or"):
        compile_command("delete_table_mapping", {"ontology_id": ONTOLOGY_ID}, SETTINGS)


# ---------------------------------------------------------------------------
# G1: payload shape gates
# ---------------------------------------------------------------------------


def test_g1_bad_join_direction_rejected():
    payload = dict(JOIN_PAYLOAD)
    payload["join_direction"] = "both"
    with pytest.raises(InvalidCommandPayload, match="join_direction"):
        compile_command("create_join_mapping", payload, SETTINGS)


def test_g1_join_path_adjacency_and_closed_schema():
    payload = dict(JOIN_PAYLOAD)
    payload["join_path"] = [
        {
            "from_table": "service.work_orders",
            "to_table": "service.work_order_parts",
            "from_columns": ["work_order_no"],
            "to_columns": ["work_order_no"],
        },
        {
            "from_table": "service.spare_parts",  # not adjacent
            "to_table": "service.other",
            "from_columns": ["id"],
            "to_columns": ["id"],
        },
    ]
    with pytest.raises(InvalidCommandPayload, match="not adjacent"):
        compile_command("create_join_mapping", payload, SETTINGS)

    payload["join_path"] = [
        {
            "from_table": "service.work_orders",
            "to_table": "service.work_order_parts",
            "from_columns": ["work_order_no", "tenant_id"],
            "to_columns": ["work_order_no"],
        }
    ]
    with pytest.raises(InvalidCommandPayload, match="equal length"):
        compile_command("create_join_mapping", payload, SETTINGS)

    payload["join_path"] = [
        {
            "from_table": "service.work_orders",
            "to_table": "service.work_order_parts",
            "from_columns": ["work_order_no"],
            "to_columns": ["work_order_no"],
            "extra": 1,
        }
    ]
    with pytest.raises(InvalidCommandPayload, match="exactly from_table"):
        compile_command("create_join_mapping", payload, SETTINGS)


def test_g1_identifier_regex():
    payload = dict(TABLE_PAYLOAD)
    payload["table_name"] = "service work orders"
    with pytest.raises(InvalidCommandPayload, match="table_name must match"):
        compile_command("create_table_mapping", payload, SETTINGS)

    payload = dict(TABLE_PAYLOAD)
    payload["column_mappings"] = [
        {
            "property_iri": f"{BASE}property/workOrderNo",
            "column": "wo-no!",
            "role": "business_key",
        }
    ]
    with pytest.raises(InvalidCommandPayload, match=r"column_mappings\[0\].column"):
        compile_command("create_table_mapping", payload, SETTINGS)


def test_g1_metric_aggregation_and_references():
    payload = dict(METRIC_PAYLOAD)
    payload["aggregation"] = "median"
    with pytest.raises(InvalidCommandPayload, match="aggregation must be one of"):
        compile_command("create_metric_definition", payload, SETTINGS)

    payload = dict(METRIC_PAYLOAD)
    payload.pop("measure_property_iri")
    payload["aggregation"] = "sum"
    with pytest.raises(InvalidCommandPayload, match="measure_property_iri is required"):
        compile_command("create_metric_definition", payload, SETTINGS)

    # Raw "table.column" grain entries are rejected: grain holds property IRIs.
    payload = dict(METRIC_PAYLOAD)
    payload["grain"] = ["service.work_orders.work_order_no"]
    with pytest.raises(InvalidCommandPayload, match=r"grain\[0\]"):
        compile_command("create_metric_definition", payload, SETTINGS)

    payload = dict(METRIC_PAYLOAD)
    payload["filters"] = [
        {"field": "service.work_orders.status", "operator": "eq", "value": "OPEN"}
    ]
    with pytest.raises(InvalidCommandPayload, match=r"filters\[0\].field"):
        compile_command("create_metric_definition", payload, SETTINGS)

    payload = dict(METRIC_PAYLOAD)
    payload["filters"] = [{"field": f"{BASE}property/status", "operator": "eq"}]
    with pytest.raises(InvalidCommandPayload, match="exactly field, operator, value"):
        compile_command("create_metric_definition", payload, SETTINGS)


# ---------------------------------------------------------------------------
# G4: business_key presence
# ---------------------------------------------------------------------------


def test_g4_business_key_required():
    payload = dict(TABLE_PAYLOAD)
    payload["column_mappings"] = [
        {"property_iri": f"{BASE}property/status", "column": "status"}
    ]
    with pytest.raises(InvalidCommandPayload, match="business_key"):
        compile_command("create_table_mapping", payload, SETTINGS)

    payload["column_mappings"] = [
        {
            "property_iri": f"{BASE}property/workOrderNo",
            "column": "work_order_no",
            "role": "primary",
        }
    ]
    with pytest.raises(InvalidCommandPayload, match="role"):
        compile_command("create_table_mapping", payload, SETTINGS)


# ---------------------------------------------------------------------------
# G7: DSN/URL rejection and exemptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("name", "postgres://db.internal:5432/prod 连接", "must not contain a URL/DSN"),
        ("schema_source", "ftp:schema-dump", "scheme-prefixed connection string"),
        (
            "description",
            "备份说明 mysql:root:pw@dbhost 另见",
            None,
        ),
    ],
)
def test_g7_dsn_strings_rejected(field, value, fragment):
    payload = dict(TABLE_PAYLOAD)
    payload[field] = value
    if fragment is None:
        # description carries userinfo-style credentials
        with pytest.raises(InvalidCommandPayload):
            compile_command("create_table_mapping", payload, SETTINGS)
    else:
        with pytest.raises(InvalidCommandPayload, match=fragment):
            compile_command("create_table_mapping", payload, SETTINGS)


def test_g7_dsn_in_enum_and_metric_payloads_rejected():
    payload = dict(ENUM_PAYLOAD)
    payload["business_meaning"] = "postgres://db:5432/x 已创建"
    with pytest.raises(InvalidCommandPayload):
        compile_command("create_enum_meaning", payload, SETTINGS)

    payload = dict(METRIC_PAYLOAD)
    payload["filters"] = [
        {"field": f"{BASE}property/status", "operator": "eq", "value": "备注 user:secret@dbhost"}
    ]
    with pytest.raises(InvalidCommandPayload, match="embedded credentials"):
        compile_command("create_metric_definition", payload, SETTINGS)


def test_g7_legitimate_iri_references_not_rejected():
    # mapped_class_iri and other reference/locator fields are exempt.
    compiled = compile_command("create_table_mapping", TABLE_PAYLOAD, SETTINGS)
    assert compiled.delta.inserts
    compiled = compile_command(
        "delete_table_mapping",
        {"ontology_id": ONTOLOGY_ID, "table_mapping_iri": "http://other.host/tm/1"},
        SETTINGS,
    )
    assert compiled.delta.deletes
    payload = dict(METRIC_PAYLOAD)
    payload["grain"] = [f"{BASE}property/workOrderNo", f"{BASE}property/tenantId"]
    payload["filters"] = [
        {"field": f"{BASE}property/status", "operator": "eq", "value": "CLOSED"}
    ]
    compiled = compile_command("create_metric_definition", payload, SETTINGS)
    assert compiled.delta.inserts


def test_secret_scan_rejects_credential_fields_at_compile_entry():
    payload = dict(TABLE_PAYLOAD)
    payload["password"] = "super-secret-value"
    with pytest.raises(InvalidCommandPayload, match="secret scanning"):
        compile_command("create_table_mapping", payload, SETTINGS)


def test_missing_schema_source_rejected_on_create():
    payload = dict(TABLE_PAYLOAD)
    del payload["schema_source"]
    with pytest.raises(InvalidCommandPayload, match="schema_source"):
        compile_command("create_table_mapping", payload, SETTINGS)
