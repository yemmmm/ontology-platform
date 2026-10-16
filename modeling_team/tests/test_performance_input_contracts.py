"""Regressions for the invalid input loops observed in the E-group run."""

from copy import deepcopy

import pytest

from modeling_team.acceptance_runtime import (
    ChildRuntimeError,
    examiner_proxy_schemas,
    validate_examiner_proxy_arguments,
)
from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS, _matches_schema
from modeling_team.read_proxy_mcp import _modeling_tool_schema


RESOURCE_TYPES = ["concept", "instance", "relation", "fact", "operation", "mapping", "metric"]


def test_query_catalogs_expose_current_resource_types_and_search_modes():
    from app.services.semantic_context_query import RESOURCE_TYPE_ORDER

    assert RESOURCE_TYPES == list(RESOURCE_TYPE_ORDER)
    catalogs = [
        examiner_proxy_schemas(["query_semantic_context"])["query_semantic_context"],
        _modeling_tool_schema("query_semantic_context")["inputSchema"],
    ]
    for schema in catalogs:
        props = schema["properties"]
        assert props["resource_types"]["items"]["enum"] == RESOURCE_TYPES
        assert props["search_mode"]["enum"] == ["hybrid", "lexical"]


def test_omitted_resource_filter_keeps_concept_definitions_queryable():
    schema = examiner_proxy_schemas(["query_semantic_context"])["query_semantic_context"]
    scope = dict(project_id="p", ontology_id="o", ticket_digest="a" * 64,
                 model_state_digest="b" * 64)
    args = dict(scope, scope_mode="ontologies", ontology_ids=["o"], query="business term")
    normalized = validate_examiner_proxy_arguments(
        "query_semantic_context", args, schema, scope=scope,
    )
    assert normalized["resource_types"] == RESOURCE_TYPES
    assert normalized["search_mode"] == "hybrid"
    for field, value in [("resource_types", ["rule"]), ("search_mode", "semantic")]:
        with pytest.raises(ChildRuntimeError, match=field):
            validate_examiner_proxy_arguments(
                "query_semantic_context", dict(args, **{field: value}), schema, scope=scope,
            )


def test_ontology_read_catalog_does_not_advertise_retired_rules():
    schemas = [
        examiner_proxy_schemas(["get_ontology_read_model"])["get_ontology_read_model"],
        _modeling_tool_schema("get_ontology_read_model")["inputSchema"],
    ]
    for schema in schemas:
        assert schema["properties"]["model_name"]["enum"] == ["classes", "entities", "facts"]


def test_change_tool_exposes_six_fixed_fields_and_rejects_observed_wrong_shapes():
    schema = CAPABILITY_TOOL_SCHEMAS["modeling_submit_model_changes"]
    item_schema = schema["properties"]["request"]["properties"]["changes"]["items"]
    assert set(item_schema["required"]) == {
        "change_id", "action", "resource_kind", "item_id", "target_ref", "fields",
    }
    change = dict(change_id="define-object", action="create", resource_kind="class",
                  item_id=None, target_ref=None,
                  fields={"name": "Business object", "semantic_definition": {
                      "business_meaning": "A kind of business object.", "unknowns": [],
                  }})
    request = dict(modeling_id="modeling", request=dict(
        schema_version="r4-3-025-model-changes/v1", candidate_ref=None, changes=[change],
    ))
    assert _matches_schema(request, schema)
    for field in ["item_id", "target_ref"]:
        wrong = deepcopy(request)
        del wrong["request"]["changes"][0][field]
        assert not _matches_schema(wrong, schema)
    wrong = deepcopy(request)
    wrong["request"]["changes"][0]["action"] = "invent"
    assert not _matches_schema(wrong, schema)


def test_change_fields_schema_explains_semantics_without_allowing_envelope_fields():
    schema = CAPABILITY_TOOL_SCHEMAS["modeling_submit_model_changes"]
    fields = schema["properties"]["request"]["properties"]["changes"]["items"]["properties"]["fields"]
    assert "semantic_definition" in fields["properties"]
    assert "business_meaning" in fields["properties"]["semantic_definition"]["properties"]
    assert _matches_schema({"name": "Object"}, fields)
    assert not _matches_schema({"name": "Object", "item_id": None}, fields)
    assert not _matches_schema({"semantic_definition": {"exclusions": ["guess"]}}, fields)


def test_published_fields_only_example_compiles_with_the_advertised_schema():
    import json
    from pathlib import Path
    from modeling_team.direct_modeling import compile_model_changes

    contract = json.loads((Path(__file__).parents[1] / "references/r4-3-025-direct-modeling-contract.json").read_text())
    request = contract["fields_only_example"]["request"]
    assert _matches_schema({"modeling_id": "modeling", "request": request},
                           CAPABILITY_TOOL_SCHEMAS["modeling_submit_model_changes"])
    batches, _ = compile_model_changes(
        request, candidate=None, ontology_by_item={"define-object": "ontology-1"},
        resolve_binding=lambda _: None,
    )
    assert batches[0]["items"][0]["command_kind"] == "create_class"


def test_unsupported_semantic_field_is_located_before_a_batch_can_be_written():
    from modeling_team.direct_modeling import ModelChangeCompilationError, compile_model_changes

    request = {"schema_version": "r4-3-025-model-changes/v1", "candidate_ref": None,
               "changes": [{"change_id": "definition", "action": "create", "resource_kind": "class",
                            "item_id": None, "target_ref": None, "fields": {
                                "name": "Object", "semantic_definition": {"exclusions": ["unsupported"]},
                            }}]}
    with pytest.raises(ModelChangeCompilationError) as error:
        compile_model_changes(request, candidate=None, ontology_by_item={"definition": "ontology-1"},
                              resolve_binding=lambda _: None)
    finding = next(e for e in error.value.errors if e["code"] == "unsupported_semantic_field")
    assert finding["path"] == "/changes/0/fields/semantic_definition/exclusions"
    assert "business_meaning" in finding["message"]


def test_inner_change_error_reaches_compiler_instead_of_opaque_broker_denial(tmp_path):
    from modeling_team.capability_mcp import RunnerCapabilityEndpoint
    from modeling_team.direct_modeling import ModelChangeCompilationError, compile_model_changes

    def dispatch(role, operation, arguments):
        try:
            compile_model_changes(arguments["request"], candidate=None,
                                  ontology_by_item={}, resolve_binding=lambda _: None)
        except ModelChangeCompilationError as exc:
            return {"status": "not_written", "errors": exc.errors}
        raise AssertionError("malformed change was not rejected")

    endpoint = RunnerCapabilityEndpoint(
        role="modeling", socket_path=tmp_path / "cap.sock", token="test-token",
        dispatch=dispatch, operations=("modeling_submit_model_changes",),
    )
    reply = endpoint.handle({"id": 1, "token": "test-token", "method": "tools/call",
                             "params": {"name": "modeling_submit_model_changes", "arguments": {
                                 "modeling_id": "modeling", "request": {
                                     "schema_version": "r4-3-025-model-changes/v1",
                                     "candidate_ref": None, "changes": [{"change_id": "broken"}],
                                 },
                             }}})
    assert "error" not in reply
    result = reply["result"]["structuredContent"]["data"]
    assert result["status"] == "not_written"
    assert result["errors"][0]["path"] == "/request/changes/0"
    assert "missing=" in result["errors"][0]["message"]


def test_read_bridge_receives_valid_reply_after_old_five_second_cutoff():
    import json
    import socket
    import tempfile
    import threading
    from pathlib import Path
    from modeling_team.read_proxy_mcp import _proxy_call

    # Real local socket: no platform, credentials or LLM. A valid read may
    # outlast the old bridge cutoff while still being inside the Host's 30s wait.
    with tempfile.TemporaryDirectory(prefix="cq-read-") as directory:
        path = str(Path(directory) / "proxy.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen(1)

            def respond():
                with server.accept()[0] as connection:
                    connection.recv(4096)
                    threading.Event().wait(5.1)
                    try:
                        connection.sendall(json.dumps({"ok": True, "data": "bounded reply"}).encode() + b"\n")
                    except BrokenPipeError:
                        pass

            worker = threading.Thread(target=respond)
            worker.start()
            try:
                assert _proxy_call(path, {"operation": "read"}) == {"ok": True, "data": "bounded reply"}
            finally:
                worker.join(timeout=6)
