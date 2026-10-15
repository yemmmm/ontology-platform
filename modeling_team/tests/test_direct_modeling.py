"""Focused contracts for the R4.3-025 deterministic unified-graph compiler."""

from __future__ import annotations

from copy import deepcopy

import pytest

from modeling_team.direct_modeling import (
    ModelChangeCompilationError,
    compile_model_changes,
)


def _item(
    item_id: str,
    item_kind: str,
    value,
    *,
    endpoints=None,
    meaning: str = "declared meaning",
    unknowns: list[str] | None = None,
    **optional,
):
    item = {
        "item_id": item_id,
        "item_kind": item_kind,
        "business_meaning": meaning,
        "value": value,
        "relation_endpoints": endpoints,
        "slice_ids": ["slice-1"],
        "shared_scope": None,
        "unknowns": list(unknowns or []),
    }
    item.update(optional)
    return item


def _candidate(items: list[dict]) -> dict:
    return {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario-1",
        "candidate_id": "candidate-1",
        "revision": 3,
        "items": items,
        "explicit_unknowns": [],
    }


def _change(change_id: str, action: str, resource_kind: str, item_id=None, *, target_ref=None, fields=None):
    return {
        "change_id": change_id,
        "action": action,
        "resource_kind": resource_kind,
        "item_id": item_id,
        "target_ref": target_ref,
        "fields": fields,
    }


def _request(changes: list[dict], *, candidate_ref: str | None = "candidate.json") -> dict:
    return {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": candidate_ref,
        "changes": changes,
    }


def test_compiles_current_candidate_in_stable_dependency_order_and_maps_sources():
    candidate = _candidate(
        [
            _item("entity-a", "entity", {"label": "A"}),
            _item("entity-b", "entity", {"label": "B"}),
            _item("property-p", "property", {"name": "connects", "predicate_kind": "relation"}),
            _item(
                "relation-r",
                "relation",
                {"predicate": {"definition_ref": "property-p"}},
                endpoints={"from_item_id": "entity-a", "to_item_id": "entity-b"},
                meaning="relation meaning is retained by the explicit predicate and endpoints",
            ),
        ]
    )
    request = _request(
        [
            _change("r-change", "create", "relation", "relation-r"),
            _change("p-change", "create", "property", "property-p"),
            _change("b-change", "create", "entity", "entity-b"),
            _change("a-change", "create", "entity", "entity-a"),
        ]
    )

    batches, source_map = compile_model_changes(
        request,
        candidate=candidate,
        ontology_by_item={item_id: "ontology-1" for item_id in ("entity-a", "entity-b", "property-p", "relation-r")},
        resolve_binding=lambda _ref: None,
    )

    assert [set(batch) for batch in batches] == [{"ontology_id", "items"}]
    assert [item["client_item_id"] for item in batches[0]["items"]] == [
        "property-p",
        "entity-b",
        "entity-a",
        "relation-r",
    ]
    relation = batches[0]["items"][-1]
    assert relation["depends_on"] == ["entity-a", "entity-b", "property-p"]
    assert relation["payload"] == {
        "source_entity_iri": {"item_ref": {"client_item_id": "entity-a", "output": "resource_iri"}},
        "relation_type_iri": {"item_ref": {"client_item_id": "property-p", "output": "resource_iri"}},
        "target_entity_iri": {"item_ref": {"client_item_id": "entity-b", "output": "resource_iri"}},
    }
    relation_source = source_map["0"]["relation-r"]
    assert relation_source["change_id"] == "r-change"
    assert relation_source["candidate_path"] == "/items/3"
    assert relation_source["field_map"]["/payload/relation_type_iri"] == [
        "/items/3/value/predicate"
    ]
    assert relation_source["commands"][0]["batch_index"] == 0


def test_merges_declared_semantics_without_inventing_a_role_and_maps_all_sources():
    candidate = _candidate(
        [
            _item(
                "entity-a",
                "entity",
                {"label": "A", "semantic_definition": {"business_meaning": "value meaning"}},
                meaning="value meaning",
                unknowns=["class membership is still unknown"],
                semantic_definition={"unknowns": ["class membership is still unknown"]},
            )
        ]
    )
    batches, source_map = compile_model_changes(
        _request([_change("create-a", "create", "entity", "entity-a")]),
        candidate=candidate,
        ontology_by_item={"entity-a": "ontology-1"},
        resolve_binding=lambda _ref: None,
    )

    payload = batches[0]["items"][0]["payload"]
    assert payload["semantic_definition"] == {
        "business_meaning": "value meaning",
        "unknowns": ["class membership is still unknown"],
    }
    semantic_sources = source_map["0"]["entity-a"]["field_map"]["/payload/semantic_definition"]
    assert semantic_sources == [
        "/items/0/semantic_definition",
        "/items/0/business_meaning",
        "/items/0/unknowns",
        "/items/0/value/semantic_definition",
    ]
    assert "semantic_role" not in payload["semantic_definition"]


def test_fields_only_update_uses_verified_target_and_change_scope():
    target_ref = {"artifact_ref": "receipts/applied.json", "path": "/resources/0"}
    seen_refs = []

    def resolve_binding(ref):
        seen_refs.append(deepcopy(ref))
        return {
            "resource_iri": "https://example.test/class/real-class",
            "resource_kind": "class",
            "ontology_id": "ontology-2",
            "model_revision": 9,
        }

    batches, source_map = compile_model_changes(
        _request(
            [_change("rename-class", "update", "class", target_ref=target_ref, fields={"name": "Renamed"})],
            candidate_ref=None,
        ),
        candidate=None,
        ontology_by_item={"rename-class": "ontology-2"},
        resolve_binding=resolve_binding,
    )

    assert seen_refs == [target_ref]
    assert batches == [
        {
            "ontology_id": "ontology-2",
            "items": [
                {
                    "client_item_id": "rename-class",
                    "change_id": "rename-class",
                    "resource_kind": "class",
                    "command_kind": "update_class",
                    "payload": {
                        "name": "Renamed",
                        "class_iri": "https://example.test/class/real-class",
                    },
                    "depends_on": [],
                    "rationale": None,
                    "competency_question_ids": [],
                }
            ],
        }
    ]
    source = source_map["0"]["rename-class"]
    assert source["artifact_ref"] is None
    assert source["json_pointer"] == "/changes/0"
    assert source["field_map"] == {
        "/payload/name": ["/changes/0/fields/name"],
        "/payload/class_iri": ["/changes/0/target_ref"],
    }


def test_mapping_alias_is_normalized_only_at_the_command_boundary():
    candidate = _candidate(
        [
            _item("definition", "entity", {"label": "Definition"}),
            _item(
                "table",
                "table_mapping",
                {
                    "name": "Table",
                    "mapped_definition": {"definition_ref": "definition"},
                    "table_name": "table_a",
                    "column_mappings": [{"column": "id"}],
                    "schema_source": "approved schema snapshot",
                },
            ),
        ]
    )
    batches, source_map = compile_model_changes(
        _request(
            [
                _change("table-change", "create", "table_mapping", "table"),
                _change("definition-change", "create", "entity", "definition"),
            ]
        ),
        candidate=candidate,
        ontology_by_item={"definition": "ontology-1", "table": "ontology-1"},
        resolve_binding=lambda _ref: None,
    )

    assert [item["client_item_id"] for item in batches[0]["items"]] == ["definition", "table"]
    mapping = batches[0]["items"][1]
    assert mapping["payload"]["mapped_definition_iri"] == {
        "item_ref": {"client_item_id": "definition", "output": "resource_iri"}
    }
    assert source_map["0"]["table"]["field_map"]["/payload/mapped_definition_iri"] == [
        "/items/1/value/mapped_definition"
    ]


def test_repeated_candidate_identity_is_disambiguated_by_batch_index():
    candidate = _candidate([_item("entity-a", "entity", {"label": "A"})])
    target_ref = {"artifact_ref": "receipts/entity.json", "path": "/items/0"}

    batches, source_map = compile_model_changes(
        _request(
            [
                _change("create-a", "create", "entity", "entity-a"),
                _change("update-a", "update", "entity", "entity-a", target_ref=target_ref),
            ]
        ),
        candidate=candidate,
        ontology_by_item={"entity-a": "ontology-1", "create-a": "ontology-1", "update-a": "ontology-1"},
        resolve_binding=lambda _ref: {
            "resource_id": "entity-1",
            "resource_iri": "https://example.test/entity/1",
            "resource_kind": "entity",
            "ontology_id": "ontology-1",
        },
        batch_max_items=1,
    )

    assert [batch["items"][0]["client_item_id"] for batch in batches] == ["entity-a", "entity-a"]
    assert source_map["0"]["entity-a"]["change_id"] == "create-a"
    assert source_map["1"]["entity-a"]["change_id"] == "update-a"
    assert source_map["1"]["entity-a"]["field_map"]["/payload/entity_iri"] == [
        "/changes/1/target_ref"
    ]


@pytest.mark.parametrize(
    "literal",
    [
        {"definition_ref": "entity-a"},
        {"item_ref": {"client_item_id": "entity-a", "output": "resource_iri"}},
    ],
)
def test_property_literal_object_does_not_become_a_reference(literal):
    property_ref = {"artifact_ref": "reads/property.json", "path": "/items/0"}
    candidate = _candidate(
        [
            _item(
                "entity-a",
                "entity",
                {
                    "label": "A",
                    "properties": [
                        {
                            "property_ref": {"existing_resource_ref": property_ref},
                            "value": literal,
                        }
                    ],
                },
                meaning="https://example.test/meaning",
            )
        ]
    )

    batches, _source_map = compile_model_changes(
        _request([_change("create-a", "create", "entity", "entity-a")]),
        candidate=candidate,
        ontology_by_item={"entity-a": "ontology-1"},
        resolve_binding=lambda _ref: {
            "resource_iri": "https://example.test/property/status",
            "resource_kind": "property",
            "ontology_id": "ontology-1",
        },
    )

    item = batches[0]["items"][0]
    assert item["depends_on"] == []
    assert item["payload"]["properties"] == {
        "https://example.test/property/status": literal
    }
    assert item["payload"]["semantic_definition"]["business_meaning"] == "https://example.test/meaning"


def test_fact_replacement_uses_observed_old_value_and_explicit_new_value():
    target_ref = {"artifact_ref": "reads/facts.json", "path": "/facts/0"}
    binding = {
        "resource_id": "fact-1",
        "resource_iri": "https://example.test/fact/1",
        "resource_kind": "fact",
        "ontology_id": "ontology-1",
        "subject_iri": "https://example.test/entity/1",
        "predicate_iri": "https://example.test/property/status",
        "old_object_value": "pending",
        "old_object_is_iri": False,
    }
    batches, source_map = compile_model_changes(
        _request(
            [
                _change(
                    "set-status",
                    "set_fact",
                    "fact",
                    target_ref=target_ref,
                    fields={"new_object_value": "ready", "new_object_is_iri": False},
                )
            ],
            candidate_ref=None,
        ),
        candidate=None,
        ontology_by_item={"set-status": "ontology-1"},
        resolve_binding=lambda ref: binding,
    )

    item = batches[0]["items"][0]
    assert item["command_kind"] == "update_fact"
    assert item["payload"] == {
        "subject_iri": binding["subject_iri"],
        "predicate_iri": binding["predicate_iri"],
        "old_object_value": "pending",
        "old_object_is_iri": False,
        "new_object_value": "ready",
        "new_object_is_iri": False,
    }
    assert source_map["0"]["set-status"]["field_map"]["/payload/new_object_value"] == [
        "/changes/0/fields/new_object_value"
    ]


def test_capacity_split_keeps_cross_batch_dependencies_in_source_map():
    candidate = _candidate(
        [
            _item("entity-a", "entity", {"label": "A"}),
            _item("entity-b", "entity", {"label": "B"}),
            _item("property-p", "property", {"name": "connects", "predicate_kind": "relation"}),
            _item(
                "relation-r",
                "relation",
                {"predicate": {"definition_ref": "property-p"}},
                endpoints={"from_item_id": "entity-a", "to_item_id": "entity-b"},
                meaning="",
            ),
        ]
    )
    changes = [
        _change("a-change", "create", "entity", "entity-a"),
        _change("b-change", "create", "entity", "entity-b"),
        _change("p-change", "create", "property", "property-p"),
        _change("r-change", "create", "relation", "relation-r"),
    ]
    batches, source_map = compile_model_changes(
        _request(changes),
        candidate=candidate,
        ontology_by_item={item_id: "ontology-1" for item_id in ("entity-a", "entity-b", "property-p", "relation-r")},
        resolve_binding=lambda _ref: None,
        batch_max_items=2,
    )

    assert [len(batch["items"]) for batch in batches] == [2, 2]
    assert batches[1]["items"][1]["depends_on"] == ["property-p"]
    relation_source = source_map["1"]["relation-r"]
    assert relation_source["cross_batch_dependencies"] == [
        {"batch_index": 1, "client_item_id": "relation-r", "depends_on": "entity-a", "depends_on_batch": 0},
        {"batch_index": 1, "client_item_id": "relation-r", "depends_on": "entity-b", "depends_on_batch": 0},
    ]


def test_rejects_ambiguous_string_value_and_points_to_candidate_field():
    candidate = _candidate([_item("entity-a", "entity", "A string is not a complete entity value")])

    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            _request([_change("create-a", "create", "entity", "entity-a")]),
            candidate=candidate,
            ontology_by_item={"entity-a": "ontology-1"},
            resolve_binding=lambda _ref: None,
        )

    error = next(error for error in caught.value.errors if error["code"] == "fields_object_required")
    assert error["change_id"] == "create-a"
    assert error["item_id"] == "entity-a"
    assert error["candidate_path"] == "/items/0/value"
    assert error["path"] == "/changes/0/value"


def test_rejects_empty_entity_label_before_platform_execution():
    candidate = _candidate([_item("entity-a", "entity", {"label": ""})])

    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            _request([_change("create-a", "create", "entity", "entity-a")]),
            candidate=candidate,
            ontology_by_item={"entity-a": "ontology-1"},
            resolve_binding=lambda _ref: None,
        )

    error = next(error for error in caught.value.errors if error["field"] == "value.label")
    assert error["code"] == "invalid_field"
    assert error["candidate_path"] == "/items/0/value/label"
    assert error["path"] == "/changes/0/value/label"


def test_fields_update_reports_empty_label_at_request_field():
    target_ref = {"artifact_ref": "reads/entity.json", "path": "/resources/0"}

    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            _request(
                [
                    _change(
                        "rename-entity",
                        "update",
                        "entity",
                        target_ref=target_ref,
                        fields={"label": ""},
                    )
                ],
                candidate_ref=None,
            ),
            candidate=None,
            ontology_by_item={"rename-entity": "ontology-1"},
            resolve_binding=lambda _ref: {
                "resource_iri": "https://example.test/entity/1",
                "resource_kind": "entity",
                "ontology_id": "ontology-1",
            },
        )

    error = next(error for error in caught.value.errors if error["field"] == "fields.label")
    assert error["path"] == "/changes/0/fields/label"
    assert error["candidate_path"] is None


def test_rejects_untrusted_target_alias_and_reports_original_change():
    request = _request(
        [
            _change(
                "rename-class",
                "update",
                "class",
                target_ref="https://example.test/class/guessed",
                fields={"name": "Renamed"},
            )
        ],
        candidate_ref=None,
    )

    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            request,
            candidate=None,
            ontology_by_item={"rename-class": "ontology-2"},
            resolve_binding=lambda _ref: pytest.fail("invalid raw target must not be resolved"),
        )

    error = caught.value.errors[0]
    assert error["code"] == "target_ref_invalid"
    assert error["change_id"] == "rename-class"
    assert error["path"] == "/changes/0/target_ref"



@pytest.mark.parametrize(("kind", "value", "expected_field"), [
    ("join_mapping", {"name": "Join", "relation_type_iri": {"existing_resource_ref": {"artifact_ref": "read.json", "path": "/items/0"}},
                      "join_direction": "forward", "join_path": [{"from_table": "a", "to_table": "b", "from_columns": ["b_id"], "to_columns": ["id"]}],
                      "schema_source": None}, "relation_type_iri"),
    ("enum_meaning", {"name": "Closed", "property_iri": {"existing_resource_ref": {"artifact_ref": "read.json", "path": "/items/0"}},
                      "enum_value": "C", "business_meaning": "Closed after confirmation", "schema_source": None}, "property_iri"),
    ("metric_definition", {"name": "Count", "grain": [], "time_field": {"existing_resource_ref": {"artifact_ref": "read.json", "path": "/items/0"}},
                           "filters": [], "aggregation": "count", "null_value_rule": "exclude unknown time", "denominator_rule": "not a ratio",
                           "schema_source": None}, "time_field"),
])
def test_remaining_mapping_kinds_keep_explicit_nullable_schema_source(kind, value, expected_field):
    candidate = _candidate([_item("mapping", kind, value, unknowns=["Source is not yet confirmed"])])
    batches, source_map = compile_model_changes(
        _request([_change("create-mapping", "create", kind, "mapping")]), candidate=candidate,
        ontology_by_item={"mapping": "ontology-1"},
        resolve_binding=lambda ref: {"ontology_id": "ontology-1", "resource_iri": "https://example.test/actual/resource", "resource_id": "actual"},
    )
    item = batches[0]["items"][0]
    assert item["command_kind"] == "create_" + kind
    assert item["payload"][expected_field] == "https://example.test/actual/resource"
    assert item["payload"]["schema_source"] is None
    assert item["payload"]["semantic_definition"]["unknowns"] == ["Source is not yet confirmed"]
    assert source_map["0"]["mapping"]["field_map"]["/payload/schema_source"] == ["/items/0/value/schema_source"]


def test_mapping_reference_slots_and_nested_source_map_are_exact():
    candidate = _candidate(
        [
            _item("definition", "entity", {"label": "Definition"}),
            _item(
                "property-p",
                "property",
                {"name": "status", "predicate_kind": "fact", "datatype": "string"},
            ),
            _item(
                "table",
                "table_mapping",
                {
                    "name": "Table",
                    "mapped_definition": {"definition_ref": "definition"},
                    "table_name": "records",
                    "column_mappings": [
                        {
                            "column": "status",
                            "property_iri": {"definition_ref": "property-p"},
                        }
                    ],
                    "schema_source": "approved schema",
                    "mapping_definition": {
                        "source_key": "records",
                        "identifiers": [
                            {
                                "columns": ["status"],
                                "kind": "business",
                                "property_iri": {"definition_ref": "property-p"},
                            }
                        ],
                    },
                },
            ),
        ]
    )
    batches, source_map = compile_model_changes(
        _request(
            [
                _change("table-change", "create", "table_mapping", "table"),
                _change("property-change", "create", "property", "property-p"),
                _change("definition-change", "create", "entity", "definition"),
            ]
        ),
        candidate=candidate,
        ontology_by_item={item_id: "ontology-1" for item_id in ("table", "property-p", "definition")},
        resolve_binding=lambda _ref: None,
    )

    table = batches[0]["items"][-1]
    assert table["payload"]["column_mappings"][0]["property_iri"]["item_ref"]["client_item_id"] == "property-p"
    assert source_map["0"]["table"]["reference_slots"] == {
        "/payload/column_mappings/0/property_iri": {
            "depends_on": "property-p",
            "output": "resource_iri",
        },
        "/payload/mapped_definition_iri": {
            "depends_on": "definition",
            "output": "resource_iri",
        },
        "/payload/mapping_definition/identifiers/0/property_iri": {
            "depends_on": "property-p",
            "output": "resource_iri",
        },
    }
    assert source_map["0"]["table"]["field_map"]["/payload/mapping_definition/identifiers/0/property_iri"] == [
        "/items/2/value/mapping_definition/identifiers/0/property_iri"
    ]


def test_mapping_bare_iri_is_rejected_at_the_original_candidate_field():
    candidate = _candidate(
        [
            _item(
                "table",
                "table_mapping",
                {
                    "name": "Table",
                    "mapped_definition": "https://example.test/guessed-definition",
                    "table_name": "records",
                    "column_mappings": [{"column": "id"}],
                    "schema_source": "approved schema",
                },
            )
        ]
    )

    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            _request([_change("table-change", "create", "table_mapping", "table")]),
            candidate=candidate,
            ontology_by_item={"table": "ontology-1"},
            resolve_binding=lambda _ref: None,
        )

    error = next(error for error in caught.value.errors if error["code"] == "reference_wrapper_required")
    assert error["path"] == "/changes/0/value/mapped_definition"
    assert error["candidate_path"] == "/items/0/value/mapped_definition"


def test_mapping_filter_value_shape_remains_a_literal_and_maps_nested_field():
    target_ref = {"artifact_ref": "reads/metric.json", "path": "/resources/0"}
    field_ref = {"artifact_ref": "reads/property.json", "path": "/resources/0"}
    batches, source_map = compile_model_changes(
        _request(
            [
                _change(
                    "update-metric",
                    "update",
                    "metric_definition",
                    target_ref=target_ref,
                    fields={
                        "filters": [
                            {
                                "field": {"existing_resource_ref": field_ref},
                                "operator": "eq",
                                "value": {"definition_ref": "literal-text"},
                            }
                        ]
                    },
                )
            ],
            candidate_ref=None,
        ),
        candidate=None,
        ontology_by_item={"update-metric": "ontology-1"},
        resolve_binding=lambda ref: (
            {
                "resource_iri": "https://example.test/property/status",
                "resource_kind": "property",
                "ontology_id": "ontology-1",
            }
            if ref == field_ref
            else {
                "resource_iri": "https://example.test/metric/1",
                "resource_kind": "metric_definition",
                "ontology_id": "ontology-1",
            }
        ),
    )

    payload = batches[0]["items"][0]["payload"]
    assert payload["filters"][0]["field"] == "https://example.test/property/status"
    assert payload["filters"][0]["value"] == {"definition_ref": "literal-text"}
    assert source_map["0"]["update-metric"]["field_map"]["/payload/filters/0/field"] == [
        "/changes/0/fields/filters/0/field"
    ]
    assert source_map["0"]["update-metric"]["reference_slots"] == {}


def test_entity_property_created_in_same_submission_uses_deferred_key_binding():
    candidate = _candidate(
        [
            _item(
                "entity-a",
                "entity",
                {
                    "label": "A",
                    "properties": [
                        {
                            "property_ref": {"definition_ref": "property-p"},
                            "value": {"definition_ref": "property-p"},
                        }
                    ],
                },
            ),
            _item(
                "property-p",
                "property",
                {"name": "status", "predicate_kind": "fact", "datatype": "string"},
            ),
        ]
    )
    batches, source_map = compile_model_changes(
        _request(
            [
                _change("create-entity", "create", "entity", "entity-a"),
                _change("create-property", "create", "property", "property-p"),
            ]
        ),
        candidate=candidate,
        ontology_by_item={"entity-a": "ontology-1", "property-p": "ontology-1"},
        resolve_binding=lambda _ref: None,
    )

    assert [batch["items"][0]["client_item_id"] for batch in batches] == ["property-p", "entity-a"]
    assert batches[1]["items"][0]["payload"]["properties"] == {}
    deferred = source_map["1"]["entity-a"]["deferred_property_keys"]
    assert deferred == [
        {
            "payload_path": "/payload/properties",
            "property_ref": {
                "item_ref": {"client_item_id": "property-p", "output": "resource_iri"}
            },
            "value": {"definition_ref": "property-p"},
            "property_ref_source": "/items/0/value/properties/0/property_ref",
            "value_source": "/items/0/value/properties/0/value",
        }
    ]


def test_entity_delete_requires_runner_owned_impact_receipt():
    target_ref = {"artifact_ref": "receipts/entity.json", "path": "/resources/0"}
    with pytest.raises(ModelChangeCompilationError) as caught:
        compile_model_changes(
            _request(
                [_change("delete-entity", "delete", "entity", target_ref=target_ref)],
                candidate_ref=None,
            ),
            candidate=None,
            ontology_by_item={"delete-entity": "ontology-1"},
            resolve_binding=lambda _ref: {
                "resource_iri": "https://example.test/entity/1",
                "resource_kind": "entity",
                "ontology_id": "ontology-1",
            },
        )

    error = caught.value.errors[0]
    assert error["code"] == "delete_impact_receipt_required"
    assert error["path"] == "/changes/0/target_ref"


@pytest.mark.parametrize(("kind", "fields"), [
    ("property", {"name": "Renamed", "description": None}),
    ("entity", {"label": None, "aliases": [], "properties": None}),
])
def test_fields_only_patch_keeps_existing_nullable_and_omitted_semantics(kind, fields):
    ref = {"artifact_ref": "observed.json", "path": "/items/0"}
    batches, _ = compile_model_changes(
        _request([_change("patch", "update", kind, target_ref=ref, fields=fields)], candidate_ref=None),
        candidate=None, ontology_by_item={"patch": "ontology-1"},
        resolve_binding=lambda ref: {"ontology_id": "ontology-1", "resource_kind": kind,
                                     "resource_iri": "https://example.test/actual/target", "resource_id": "target"},
    )
    assert batches[0]["items"][0]["payload"] == {**fields, kind + "_iri": "https://example.test/actual/target"}


def test_known_mapping_enum_error_rejects_the_whole_submission_before_execution():
    candidate = _candidate([
        _item("predicate", "property", {"name": "Links", "predicate_kind": "relation"}),
        _item("join", "join_mapping", {"name": "Join", "relation_type_iri": {"definition_ref": "predicate"},
                                      "join_direction": "sideways", "join_path": [{"from_table": "a", "to_table": "b", "from_columns": ["id"], "to_columns": ["a_id"]}],
                                      "schema_source": None}),
    ])
    with pytest.raises(ModelChangeCompilationError) as failure:
        compile_model_changes(_request([_change("create-p", "create", "property", "predicate"),
                                        _change("create-j", "create", "join_mapping", "join")]),
                              candidate=candidate, ontology_by_item={"predicate": "ontology-1", "join": "ontology-2"},
                              resolve_binding=lambda ref: None)
    assert any(error["code"] == "invalid_field" and error["candidate_path"] == "/items/1/value/join_direction"
               for error in failure.value.errors)
