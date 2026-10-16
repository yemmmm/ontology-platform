"""Real capability edge cases for the R4.3-025 direct Modeling path.

These tests reuse the native in-memory database/RDF fixture from the primary
integration test.  They exercise the outer capability instead of substituting
compiler or apply results.
"""

from __future__ import annotations

import json

from rdflib import URIRef

from backend.tests.test_direct_modeling_team_integration import (
    _write_json,
    call,
    direct_run,  # noqa: F401 - imported so pytest registers the shared fixture
    request_for,
)


def _item(
    item_id: str,
    item_kind: str = "entity",
    value: object | None = None,
    *,
    endpoints: dict[str, str] | None = None,
    meaning: str = "declared meaning",
    unknowns: list[str] | None = None,
    **optional: object,
) -> dict[str, object]:
    item: dict[str, object] = {
        "item_id": item_id,
        "item_kind": item_kind,
        "business_meaning": meaning,
        "value": value if value is not None else {"label": item_id},
        "relation_endpoints": endpoints,
        "slice_ids": ["slice-1"],
        "shared_scope": None,
        "unknowns": list(unknowns or []),
    }
    item.update(optional)
    return item


def _change(
    change_id: str,
    action: str,
    resource_kind: str,
    item_id: str | None = None,
    *,
    target_ref: dict[str, str] | None = None,
    fields: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "change_id": change_id,
        "action": action,
        "resource_kind": resource_kind,
        "item_id": item_id,
        "target_ref": target_ref,
        "fields": fields,
    }


def _candidate_request(run, reference: str, items: list[dict[str, object]], changes: list[dict[str, object]]):
    candidate = {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "direct-edges",
        "candidate_id": "direct-edges",
        "revision": 1,
        "explicit_unknowns": [],
        "items": items,
    }
    _write_json(run.staged.run_root / reference, candidate)
    return {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": reference,
        "changes": changes,
    }


def _all_submitted_items(run):
    return [item for batch in run.calls for item in batch["items"]]


def test_real_cross_batch_relation_binds_applied_outputs_and_reads_direction(
    direct_run,  # noqa: F811 - pytest resolves the imported shared fixture
):
    run = direct_run
    fillers = [
        _item(f"filler-{index:03d}", value={"label": f"Filler {index}"})
        for index in range(97)
    ]
    items = [
        _item(
            "relation-r",
            "relation",
            {"predicate": {"definition_ref": "property-p"}},
            endpoints={"from_item_id": "entity-a", "to_item_id": "entity-b"},
            meaning="A connects B",
        ),
        _item("entity-a", value={"label": "A"}),
        _item("property-p", "property", {"name": "connects", "predicate_kind": "relation"}),
        *fillers,
        _item("entity-b", value={"label": "B"}),
    ]
    changes = [
        _change("create-property", "create", "property", "property-p"),
        _change("create-entity-b", "create", "entity", "entity-b"),
        *[
            _change(f"create-filler-{index:03d}", "create", "entity", f"filler-{index:03d}")
            for index in range(97)
        ],
        _change("create-entity-a", "create", "entity", "entity-a"),
        _change("create-relation", "create", "relation", "relation-r"),
    ]
    request = _candidate_request(
        run,
        "stage3-neutral-graph/candidates/direct-edges-r1.json",
        items,
        changes,
    )

    result = call(run, request)
    assert result["status"] == "completed", json.dumps(result, ensure_ascii=False, default=str)
    assert len(result["batches"]) == 2, result
    assert len(run.calls) == 2
    assert result["batches"][1]["change_ids"] == ["create-relation"]

    bindings = {
        row["item_id"]: row
        for batch in result["batches"]
        for row in batch["resource_bindings"]
        if row.get("resource_iri")
    }
    relation_item = next(item for item in _all_submitted_items(run) if item["client_item_id"] == "relation-r")
    relation_payload = relation_item["payload"]
    assert relation_payload == {
        "source_entity_iri": bindings["entity-a"]["resource_iri"],
        "relation_type_iri": bindings["property-p"]["resource_iri"],
        "target_entity_iri": bindings["entity-b"]["resource_iri"],
    }
    assert all("item_ref" not in json.dumps(value) for value in relation_payload.values())
    assert all(local_id not in json.dumps(relation_payload) for local_id in ("entity-a", "entity-b", "property-p"))

    read = run.read(
        "query_semantic_context",
        {
            "project_id": "direct-p",
            "scope_mode": "ontologies",
            "ontology_ids": ["direct-o"],
            "query": bindings["entity-a"]["resource_iri"],
            "depth": 1,
            "context_limit": 100,
            "context_detail": "full",
        },
    )
    assert read["ok"] is True, read
    data = read["data"]
    assert any(row["iri"] == bindings["entity-a"]["resource_iri"] for row in data["primary_matches"])
    assert any(
        row.get("data", {}).get("subject") == bindings["entity-a"]["resource_iri"]
        and row.get("data", {}).get("object") == bindings["entity-b"]["resource_iri"]
        for row in data["related_context"]
    ), data["related_context"]


def test_receipt_pointer_update_preserves_identity_rejects_stale_read_and_allows_correction(
    direct_run,  # noqa: F811 - pytest resolves the imported shared fixture
):
    run = direct_run
    created = call(run, request_for(run, label="Initial work order"))
    assert created["status"] == "completed", created
    create_row = created["batches"][0]
    resource_iri = create_row["resource_bindings"][0]["resource_iri"]
    receipt_ref = create_row["receipt_ref"]
    target_ref = {"artifact_ref": receipt_ref, "path": "/structuredContent/data/items/0"}
    observed = run.runner._direct_platform_read("get_ontology_read_model", {
        "ontology_id": "direct-o", "model_name": "entity-list", "field_set": "full",
    })
    position = next(index for index, item in enumerate(observed["data"]["items"])
                    if item["iri"] == resource_iri)
    read_target_ref = {
        "artifact_ref": observed["platform_ref"]["artifact_path"],
        "path": f"/structuredContent/data/items/{position}",
    }

    invalid = call(
        run,
        {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                _change(
                    "rename-work-order-invalid",
                    "update",
                    "entity",
                    target_ref=target_ref,
                    fields={"label": ""},
                )
            ],
        },
    )
    assert invalid["status"] == "not_written", invalid
    assert invalid["errors"][0]["path"] == "/changes/0/fields/label"
    assert len(run.calls) == 1

    update_request = {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                _change(
                    "rename-work-order",
                    "update",
                    "entity",
                    target_ref=target_ref,
                    fields={"label": "Updated work order"},
                )
            ],
    }
    updated = call(run, update_request)
    assert updated["status"] == "completed", updated
    assert len(run.calls) == 2
    assert call(run, update_request)["status"] == "completed"
    assert len(run.calls) == 2
    update_item = run.calls[-1]["items"][0]
    assert update_item["payload"]["entity_iri"] == resource_iri
    assert update_item["payload"]["label"] == "Updated work order"
    assert updated["batches"][0]["resource_bindings"][0]["resource_kind"] == "entity"
    assert updated["batches"][0]["receipt_ref"]
    assert any(
        subject == URIRef(resource_iri) and str(obj) == "Updated work order"
        for subject, _, obj, _ in run.store.dataset.quads((None, None, None, None))
    )

    stale = call(
        run,
        {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                _change(
                    "rename-work-order-stale",
                    "update",
                    "entity",
                    target_ref=read_target_ref,
                    fields={"label": "Must not write"},
                )
            ],
        },
    )
    assert stale["status"] == "not_written", stale
    assert stale["errors"][0]["code"] == "resource_revision_conflict"
    assert len(run.calls) == 2
    assert not any(str(obj) == "Must not write" for _, _, obj, _ in run.store.dataset.quads((None, None, None, None)))

    # Applied receipts remain identity anchors across revisions; governed read
    # snapshots above must instead be refreshed before a new change can use them.
    correction_request = {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": None,
        "changes": [
            _change(
                "correct-work-order",
                "update",
                "entity",
                target_ref=target_ref,
                fields={"label": "Corrected work order"},
            )
        ],
    }
    corrected = call(run, correction_request)
    assert corrected["status"] == "completed", corrected
    assert len(run.calls) == 3
    assert run.calls[-1]["items"][0]["payload"]["entity_iri"] == resource_iri
    assert any(
        subject == URIRef(resource_iri) and str(obj) == "Corrected work order"
        for subject, _, obj, _ in run.store.dataset.quads((None, None, None, None))
    )
    assert call(run, correction_request)["status"] == "completed"
    assert len(run.calls) == 3


def test_forged_and_out_of_scope_references_are_rejected_without_write(monkeypatch, direct_run):  # noqa: F811
    run = direct_run
    forged = call(
        run,
        {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                _change(
                    "forged-target",
                    "update",
                    "entity",
                    target_ref={"artifact_ref": "evidence/platform-responses/forged.json", "path": "/structuredContent/data/items/0"},
                    fields={"label": "Should never write"},
                )
            ],
        },
    )
    assert forged["status"] == "not_written", forged
    assert forged["errors"][0]["code"] == "resource_reference_not_observed"
    assert run.calls == []
    assert run.store.writes == []

    created = call(run, request_for(run, label="Scoped baseline"))
    assert created["status"] == "completed", created
    receipt_ref = created["batches"][0]["receipt_ref"]
    old_scope = list(run.runner.scope.ontology_ids)
    monkeypatch.setattr(run.runner.scope, "ontology_ids", ["foreign-o"])
    try:
        forbidden = call(
            run,
            {
                "schema_version": "r4-3-025-model-changes/v1",
                "candidate_ref": None,
                "changes": [
                    _change(
                        "foreign-target",
                        "update",
                        "entity",
                        target_ref={"artifact_ref": receipt_ref, "path": "/structuredContent/data/items/0"},
                        fields={"label": "Foreign write"},
                    )
                ],
            },
        )
    finally:
        monkeypatch.setattr(run.runner.scope, "ontology_ids", old_scope)
    assert forbidden["status"] == "not_written", forbidden
    assert forbidden["errors"][0]["code"] == "forbidden_scope"
    assert len(run.calls) == 1
    assert len(run.store.writes) == 1


def test_backend_finding_rejects_entire_final_batch_without_partial_rdf_write(direct_run):  # noqa: F811
    run = direct_run
    request = _candidate_request(
        run,
        "stage3-neutral-graph/candidates/direct-invalid-batch-r1.json",
        [
            _item("good", value={"label": "Good"}),
            _item(
                "bad",
                value={"label": "Bad", "semantic_definition": {"unsupported_field": "reject"}},
            ),
        ],
        [
            _change("create-good", "create", "entity", "good"),
            _change("create-bad", "create", "entity", "bad"),
        ],
    )

    result = call(run, request)
    assert result["status"] == "not_written", json.dumps(result, ensure_ascii=False, default=str)
    assert len(run.calls) == 1
    assert result["batches"][0]["attempt_status"] in {"validation_failed", "failed", "rejected"}
    assert result["batches"][0]["write_state"] == "not_written"
    assert result["errors"] or result["batches"][0]["errors"]
    error = (result["errors"] or result["batches"][0]["errors"])[0]
    assert error["code"] == "invalid_command_payload"
    assert error["change_id"] == "create-bad"
    assert error["path"] == "/items/1/payload"
    assert error["platform_ref"]
    assert run.store.writes == []
    assert not any(str(obj) in {"Good", "Bad"} for _, _, obj, _ in run.store.dataset.quads((None, None, None, None)))


def test_all_seven_unified_kinds_apply_through_native_capability(direct_run):  # noqa: F811
    run = direct_run
    def ref(item):
        return {"definition_ref": item}
    items = [
        _item("order", value={"label": "Work order"}),
        _item("fault", value={"label": "Fault"}),
        _item("links", "property", {"name": "Links fault", "predicate_kind": "relation"}),
        _item("status", "property", {"name": "Status", "predicate_kind": "fact", "datatype": "http://www.w3.org/2001/XMLSchema#string"}),
        _item("opened", "property", {"name": "Opened at", "predicate_kind": "fact", "datatype": "http://www.w3.org/2001/XMLSchema#dateTime"}),
        _item("relation", "relation", {"predicate": ref("links")}, endpoints={"from_item_id": "order", "to_item_id": "fault"}),
        _item("table", "table_mapping", {"name": "Orders", "mapped_definition": ref("order"), "table_name": "orders",
                                           "column_mappings": [{"column": "status", "property_iri": ref("status")}, {"column": "fault_id"}], "schema_source": None}),
        _item("fault-table", "table_mapping", {"name": "Faults", "mapped_definition": ref("fault"), "table_name": "faults",
                                                 "column_mappings": [{"column": "id"}], "schema_source": None}),
        _item("join", "join_mapping", {"name": "Order fault", "relation_type_iri": ref("links"), "join_direction": "forward",
                                        "join_path": [{"from_table": "orders", "to_table": "faults", "from_columns": ["fault_id"], "to_columns": ["id"]}], "schema_source": None}),
        _item("enum", "enum_meaning", {"name": "Open", "property_iri": ref("status"), "enum_value": "OPEN",
                                        "business_meaning": "Work is open", "table_mapping_iri": ref("table"), "column": "status", "schema_source": None}),
        _item("metric", "metric_definition", {"name": "Work order count", "grain": [], "time_field": ref("opened"),
                                               "filters": [], "aggregation": "count", "null_value_rule": "exclude unknown opened time",
                                               "denominator_rule": "not a ratio", "schema_source": None}),
    ]
    # The generic item meaning must agree with an explicitly provided field.
    items[-2]["business_meaning"] = "Work is open"
    request = _candidate_request(run, "stage3-neutral-graph/candidates/seven-kinds-r1.json", items,
                                 [_change("create-" + item["item_id"], "create", item["item_kind"], item["item_id"]) for item in reversed(items)])
    path = run.staged.run_root / request["candidate_ref"]
    valid_candidate = json.loads(path.read_text())
    invalid_candidate = json.loads(path.read_text())
    table = next(item for item in invalid_candidate["items"] if item["item_id"] == "table")
    table["value"]["column_mappings"].pop()  # fault_id is not mapped.
    _write_json(path, invalid_candidate)
    rejected = call(run, request)
    assert rejected["status"] == "not_written", rejected
    join_index = next(index for index, item in enumerate(items) if item["item_id"] == "join")
    assert any(error["code"] == "join_path_not_mapped" and
               error["path"] == f"/items/{join_index}/value/join_path/0/from_columns/0"
               for error in rejected["errors"]), rejected["errors"]
    assert not run.store.writes
    valid_candidate["revision"] = 2
    request["candidate_ref"] = "stage3-neutral-graph/candidates/seven-kinds-r2.json"
    _write_json(run.staged.run_root / request["candidate_ref"], valid_candidate)
    result = call(run, request)
    assert result["status"] == "completed", json.dumps({"status": result["status"], "errors": result["errors"]}, ensure_ascii=False)
    assert {entry["resource_kind"] for batch in result["batches"] for entry in batch["resource_bindings"]} == {
        "entity", "property", "relation", "table_mapping", "join_mapping", "enum_meaning", "metric_definition",
    }
    assert all(batch["mode"] == "apply_atomic" for batch in run.calls)
    assert len(run.calls[-1]["items"]) == len(items)
    assert call(run, request)["status"] == "completed"
    assert len(run.calls) == 2  # One rejected Attempt, then one successful atomic apply.
