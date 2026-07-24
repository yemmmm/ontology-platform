#!/usr/bin/env python3
"""Run the reviewed R2.1-001 M2 candidate through public REST contracts only.

The operator, not this script, owns isolated-backend lifecycle.  No credential,
lease token, cookie, or Authorization header is serialized or printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PACKAGE = Path(__file__).resolve().parent
RUNTIME_DIR = PACKAGE / "runtime"
RUNTIME_RECORD = RUNTIME_DIR / "runtime-record.json"
LOG = PACKAGE / "rehearsal-log.md"
API_KEY_ENV = "ONTOLOGY_M2_API_KEY"
OBJECT_PROPERTIES = {
    "has_version": ("workflow", "workflow_version"),
    "version_of": ("workflow_version", "workflow"),
    "active_latest_version": ("workflow", "workflow_version"),
    "has_invocation": ("workflow_version", "tool_invocation"),
    "invokes_tool": ("tool_invocation", "workflow_tool"),
    "tool_targets_version": ("workflow_tool", "workflow_version"),
    "binding_at_invocation": ("tool_invocation", "variable_binding"),
    "binding_source": ("variable_binding", "variable"),
    "binding_target": ("variable_binding", "variable"),
    "has_use": ("workflow_version", "variable_use"),
    "uses_variable": ("variable_use", "variable"),
    "produces_variable": ("variable_use", "variable"),
    "derived_from_variable": ("variable", "variable"),
    "declared_by_version": ("variable", "workflow_version"),
    "change_applies_to_version": ("change_set", "workflow_version"),
    "deletes_variable": ("change_set", "variable"),
    "previous_version": ("change_set", "workflow_version"),
}
DATATYPE_PROPERTIES = (
    "publication_state",
    "completeness",
    "unknown_detail",
    "variable_name",
    "data_type",
    "variable_role",
    "use_kind",
    "call_site_id",
    "call_site_location",
    "source_kind",
)


class RehearsalError(RuntimeError):
    """A contract failure that must stop the candidate without a bypass."""


@dataclass
class PublicApi:
    base_url: str
    api_key: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 -- supplied isolated URL
                content = response.read().decode("utf-8")
                result = json.loads(content) if content else None
                self.calls.append({"method": method, "path": path, "status": response.status})
                return result
        except HTTPError as exc:
            content = exc.read().decode("utf-8", errors="replace")
            self.calls.append({"method": method, "path": path, "status": exc.code})
            raise RehearsalError(f"{method} {path} failed ({exc.code}): {content[:2000]}") from exc
        except (URLError, json.JSONDecodeError) as exc:
            raise RehearsalError(f"{method} {path} failed: {exc}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload)


def item(
    client_item_id: str,
    command_kind: str,
    payload: dict[str, Any],
    evidence_reference_ids: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "client_item_id": client_item_id,
        "command_kind": command_kind,
        "payload": payload,
        "evidence_reference_ids": evidence_reference_ids,
        "rationale": rationale,
    }


def ref(client_item_id: str, output: str = "resource_id") -> dict[str, dict[str, str]]:
    return {"item_ref": {"client_item_id": client_item_id, "output": output}}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalError(message)


def _expected_status(response: dict[str, Any], expected: str, label: str) -> None:
    _assert(response.get("attempt_status") == expected, f"{label}: expected {expected}, got {response}")


def _output_iris(response: dict[str, Any]) -> dict[str, str]:
    return {
        entry["client_item_id"]: entry["resource_outputs"]["resource_iri"]
        for entry in response["items"]
        if entry.get("resource_outputs", {}).get("resource_iri")
    }


def _workspace_version(client: PublicApi, ontology_id: str) -> str:
    context = client.get(f"/api/ontologies/{ontology_id}/modeling-context")
    version = context.get("workspace", {}).get("workspace_version")
    _assert(isinstance(version, str) and version, "modeling context did not return a workspace version")
    return version


def _submit(
    client: PublicApi,
    session_id: str,
    ontology_id: str,
    run_tag: str,
    label: str,
    mode: str,
    expected_workspace_version: str,
    items: list[dict[str, Any]],
    lease_token: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "client_batch_id": f"m2-{run_tag}-{label}",
        "ontology_id": ontology_id,
        "idempotency_key": f"m2-{run_tag}-{label}-{mode}",
        "mode": mode,
        "expected_workspace_version": expected_workspace_version,
        "items": items,
    }
    if lease_token is not None:
        payload["lease_token"] = lease_token
    return client.post(f"/api/build-sessions/{session_id}/modeling-batches", payload)


def _dry_run_then_apply(
    client: PublicApi,
    session_id: str,
    ontology_id: str,
    run_tag: str,
    label: str,
    items: list[dict[str, Any]],
    lease_token: str,
    on_response: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = _workspace_version(client, ontology_id)
    dry_run = _submit(
        client, session_id, ontology_id, run_tag, label, "dry_run", before, items
    )
    if on_response:
        on_response("dry_run", dry_run)
    _expected_status(dry_run, "validated", f"{label} dry-run")
    fresh = _workspace_version(client, ontology_id)
    applied = _submit(
        client, session_id, ontology_id, run_tag, label, "apply_atomic", fresh, items, lease_token
    )
    if on_response:
        on_response("apply", applied)
    _expected_status(applied, "applied", f"{label} apply")
    _assert(
        applied.get("workspace", {}).get("after_version") not in {None, fresh},
        f"{label} apply did not advance workspace version",
    )
    return dry_run, applied


def bad_shape_items(evidence_ids: list[str]) -> list[dict[str, Any]]:
    """A deliberately invalid candidate: Shape + target entity missing invokesTool."""
    return [
        item("bad-invocation", "create_class", {"name": "ToolInvocation"}, evidence_ids, "test target"),
        item("bad-tool", "create_class", {"name": "WorkflowTool"}, evidence_ids, "test range"),
        item(
            "bad-invokes-tool",
            "create_property",
            {"name": "invokesTool", "class_id": ref("bad-invocation"), "object_class_id": ref("bad-tool")},
            evidence_ids,
            "object predicate required by the candidate Shape",
        ),
        item(
            "bad-invocation-shape",
            "create_shape",
            {
                "target_class_id": ref("bad-invocation"),
                "constraints": [{"path_id": ref("bad-invokes-tool"), "min_count": 1}],
            },
            evidence_ids,
            "deliberately exposes the missing invocation target",
        ),
        item(
            "bad-invocation-instance",
            "create_entity",
            {"entity_id": "invalid-invocation", "class_iri_or_legacy_id": ref("bad-invocation", "resource_iri"), "label": "Invalid invocation"},
            evidence_ids,
            "the candidate must be rejected before application",
        ),
    ]


def tbox_and_shapes_items(evidence_ids: list[str]) -> list[dict[str, Any]]:
    classes = {
        "modeled_component": ("ModeledComponent", []),
        "publication_state_bearing": ("PublicationStateBearing", ["modeled_component"]),
        "workflow": ("Workflow", ["modeled_component"]),
        "workflow_version": ("WorkflowVersion", ["publication_state_bearing"]),
        "published_workflow_version": ("PublishedWorkflowVersion", ["workflow_version"]),
        "workflow_tool": ("WorkflowTool", ["modeled_component"]),
        "tool_invocation": ("ToolInvocation", ["modeled_component"]),
        "variable": ("Variable", ["modeled_component"]),
        "variable_binding": ("VariableBinding", ["modeled_component"]),
        "variable_use": ("VariableUse", ["modeled_component"]),
        "change_set": ("ChangeSet", ["publication_state_bearing"]),
        "explicit_gap_component": ("ExplicitGapComponent", ["modeled_component"]),
    }
    result = [
        item(
            key,
            "create_class",
            {"name": label, "parent_class_ids": [ref(parent) for parent in parents]},
            evidence_ids,
            "M1 semantic boundary expressed through a generic class",
        )
        for key, (label, parents) in classes.items()
    ]
    for key, (domain, target) in OBJECT_PROPERTIES.items():
        result.append(
            item(
                key,
                "create_property",
                {"name": "".join(part.title() if index else part for index, part in enumerate(key.split("_"))), "class_id": ref(domain), "object_class_id": ref(target)},
                evidence_ids,
                "constrained relationship emitted as an OWL ObjectProperty",
            )
        )
    for key in DATATYPE_PROPERTIES:
        result.append(
            item(
                key,
                "create_property",
                {"name": "".join(part.title() if index else part for index, part in enumerate(key.split("_"))), "class_id": ref("modeled_component"), "datatype": "string"},
                evidence_ids,
                "literal semantic detail retained as explicit modeled data",
            )
        )

    def shape(name: str, target: str, constraints: list[dict[str, Any]]) -> None:
        result.append(item(name, "create_shape", {"target_class_id": ref(target), "constraints": constraints}, evidence_ids, "minimum M1 structure and explicit completeness"))

    complete = {"path_id": ref("completeness"), "min_count": 1, "max_count": 1, "pattern": "^(complete|explicit-gap)$"}
    shape("workflow-version-shape", "workflow_version", [complete, {"path_id": ref("publication_state"), "min_count": 1, "max_count": 1, "pattern": "^(latest|superseded|current-draft)$"}, {"path_id": ref("version_of"), "min_count": 1, "max_count": 1}])
    shape("published-version-shape", "published_workflow_version", [complete, {"path_id": ref("publication_state"), "min_count": 1, "max_count": 1, "pattern": "^latest$"}, {"path_id": ref("version_of"), "min_count": 1, "max_count": 1}])
    shape("invocation-shape", "tool_invocation", [complete, {"path_id": ref("invokes_tool"), "min_count": 1, "max_count": 1}, {"path_id": ref("call_site_id"), "min_count": 1, "max_count": 1, "pattern": ".+"}, {"path_id": ref("call_site_location"), "min_count": 1, "max_count": 1, "pattern": ".+"}])
    shape("binding-shape", "variable_binding", [complete, {"path_id": ref("binding_source"), "min_count": 1, "max_count": 1}, {"path_id": ref("binding_target"), "min_count": 1, "max_count": 1}])
    shape("use-shape", "variable_use", [complete, {"path_id": ref("uses_variable"), "min_count": 1, "max_count": 1}, {"path_id": ref("use_kind"), "min_count": 1, "max_count": 1, "pattern": ".+"}])
    shape("change-shape", "change_set", [complete, {"path_id": ref("publication_state"), "min_count": 1, "max_count": 1, "pattern": "^(latest|current-draft)$"}, {"path_id": ref("change_applies_to_version"), "min_count": 1, "max_count": 1}, {"path_id": ref("previous_version"), "min_count": 1, "max_count": 1}, {"path_id": ref("deletes_variable"), "min_count": 1, "max_count": 1}])
    shape("explicit-gap-shape", "explicit_gap_component", [{"path_id": ref("completeness"), "min_count": 1, "max_count": 1, "pattern": "^explicit-gap$"}, {"path_id": ref("unknown_detail"), "min_count": 1, "max_count": 1, "pattern": ".+"}])
    return result


def _entity(
    entity_id: str, class_key: str, label: str, properties: dict[str, str], iris: dict[str, str], evidence_ids: list[str]
) -> dict[str, Any]:
    return item(
        entity_id,
        "create_entity",
        {"entity_id": entity_id, "class_iri_or_legacy_id": iris[class_key], "label": label, "properties": {iris[key]: value for key, value in properties.items()}},
        evidence_ids,
        "synthetic M1 fixture fact, not a claim about a built-in Dify application",
    )


def _relation(
    source: str,
    predicate: str,
    target: str,
    iris: dict[str, str],
    evidence_ids: list[str],
    existing_entity_iris: dict[str, str] | None = None,
) -> dict[str, Any]:
    existing_entity_iris = existing_entity_iris or {}
    source_value: str | dict[str, dict[str, str]] = existing_entity_iris.get(
        source, ref(source, "resource_iri")
    )
    target_value: str | dict[str, dict[str, str]] = existing_entity_iris.get(
        target, ref(target, "resource_iri")
    )
    return item(
        f"rel-{source}-{predicate}-{target}",
        "create_relation",
        {"source_entity_iri": source_value, "relation_type_iri": iris[predicate], "target_entity_iri": target_value},
        evidence_ids,
        "synthetic fixture topology uses the matching generated property IRI",
    )


def published_fixture_items(iris: dict[str, str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    entities = [
        ("c", "workflow", "Content Quality Scoring Workflow", {"completeness": "complete"}),
        ("b", "workflow", "Content Generation Workflow", {"completeness": "complete"}),
        ("a", "workflow", "Campaign Publication Workflow", {"completeness": "complete"}),
        ("c-v1", "workflow_version", "C version 1", {"completeness": "complete", "publication_state": "superseded"}),
        ("c-v2", "published_workflow_version", "C version 2", {"completeness": "complete", "publication_state": "latest"}),
        ("b-v1", "workflow_version", "B version 1", {"completeness": "complete", "publication_state": "latest"}),
        ("a-v1", "workflow_version", "A version 1", {"completeness": "complete", "publication_state": "latest"}),
        ("tool-c", "workflow_tool", "C as workflow tool", {"completeness": "complete"}),
        ("tool-b", "workflow_tool", "B as workflow tool", {"completeness": "complete"}),
        ("b-c-invocation", "tool_invocation", "B invokes C", {"completeness": "complete", "call_site_id": "b-v1.node.tool-c", "call_site_location": "B Tool node C"}),
        ("a-b-invocation", "tool_invocation", "A invokes B", {"completeness": "complete", "call_site_id": "a-v1.node.tool-b", "call_site_location": "A Tool node B"}),
        ("c-content", "variable", "C content", {"completeness": "complete", "variable_name": "content", "data_type": "string", "variable_role": "input"}),
        ("c-quality-score", "variable", "C quality score", {"completeness": "complete", "variable_name": "quality_score", "data_type": "number", "variable_role": "output"}),
        ("b-content-source", "variable", "B content source", {"completeness": "complete", "variable_name": "content", "data_type": "string", "variable_role": "input"}),
        ("b-quality-score", "variable", "B quality score", {"completeness": "complete", "variable_name": "quality_score", "data_type": "number", "variable_role": "local"}),
        ("b-approved-content", "variable", "B approved content", {"completeness": "complete", "variable_name": "approved_content", "data_type": "string", "variable_role": "output"}),
        ("a-publish-content", "variable", "A publish content", {"completeness": "complete", "variable_name": "publish_content", "data_type": "string", "variable_role": "input"}),
        ("b-content-binding", "variable_binding", "B content binding", {"completeness": "complete"}),
        ("b-quality-binding", "variable_binding", "B quality binding", {"completeness": "complete"}),
        ("a-approved-binding", "variable_binding", "A approved binding", {"completeness": "complete"}),
        ("b-if-use", "variable_use", "B IF/ELSE use", {"completeness": "complete", "use_kind": "if-else"}),
        ("a-publish-use", "variable_use", "A publication use", {"completeness": "complete", "use_kind": "output"}),
        ("published-delete-quality", "change_set", "Published deletion of quality_score", {"completeness": "complete", "publication_state": "latest", "source_kind": "synthetic-fixture"}),
    ]
    result = [_entity(*entry, iris, evidence_ids) for entry in entities]
    relations = [
        ("c", "has_version", "c-v1"), ("c", "has_version", "c-v2"), ("c-v1", "version_of", "c"), ("c-v2", "version_of", "c"), ("c", "active_latest_version", "c-v2"),
        ("b", "has_version", "b-v1"), ("b-v1", "version_of", "b"), ("b", "active_latest_version", "b-v1"), ("a", "has_version", "a-v1"), ("a-v1", "version_of", "a"), ("a", "active_latest_version", "a-v1"),
        ("tool-c", "tool_targets_version", "c-v2"), ("tool-b", "tool_targets_version", "b-v1"), ("b-v1", "has_invocation", "b-c-invocation"), ("b-c-invocation", "invokes_tool", "tool-c"), ("a-v1", "has_invocation", "a-b-invocation"), ("a-b-invocation", "invokes_tool", "tool-b"),
        ("b-c-invocation", "binding_at_invocation", "b-content-binding"), ("b-c-invocation", "binding_at_invocation", "b-quality-binding"), ("b-content-binding", "binding_source", "b-content-source"), ("b-content-binding", "binding_target", "c-content"), ("b-quality-binding", "binding_source", "c-quality-score"), ("b-quality-binding", "binding_target", "b-quality-score"),
        ("b-v1", "has_use", "b-if-use"), ("b-if-use", "uses_variable", "b-quality-score"), ("b-if-use", "produces_variable", "b-approved-content"), ("b-approved-content", "declared_by_version", "b-v1"),
        ("a-b-invocation", "binding_at_invocation", "a-approved-binding"), ("a-approved-binding", "binding_source", "b-approved-content"), ("a-approved-binding", "binding_target", "a-publish-content"), ("a-v1", "has_use", "a-publish-use"), ("a-publish-use", "uses_variable", "a-publish-content"),
        ("c-content", "declared_by_version", "c-v2"), ("c-quality-score", "declared_by_version", "c-v1"), ("published-delete-quality", "change_applies_to_version", "c-v2"), ("published-delete-quality", "previous_version", "c-v1"), ("published-delete-quality", "deletes_variable", "c-quality-score"),
    ]
    result.extend(_relation(*entry, iris, evidence_ids) for entry in relations)
    return result


def draft_fixture_items(
    iris: dict[str, str], evidence_ids: list[str], published_entity_iris: dict[str, str]
) -> list[dict[str, Any]]:
    result = [
        _entity("c-draft", "workflow_version", "C current draft", {"completeness": "complete", "publication_state": "current-draft"}, iris, evidence_ids),
        _entity("draft-delete-quality", "change_set", "Draft deletion of quality_score", {"completeness": "complete", "publication_state": "current-draft", "source_kind": "synthetic-fixture"}, iris, evidence_ids),
    ]
    result.extend(
        _relation(*entry, iris, evidence_ids, published_entity_iris)
        for entry in [
            ("c", "has_version", "c-draft"),
            ("c-draft", "version_of", "c"),
            ("draft-delete-quality", "change_applies_to_version", "c-draft"),
            ("draft-delete-quality", "previous_version", "c-v2"),
            ("draft-delete-quality", "deletes_variable", "c-quality-score"),
        ]
    )
    return result


def explicit_gap_items(iris: dict[str, str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [_entity("unmodeled-node-gap", "explicit_gap_component", "Unmodeled downstream node", {"completeness": "explicit-gap", "unknown_detail": "Downstream node is not modeled in this bounded fixture."}, iris, evidence_ids)]


def invalid_invocation_items(iris: dict[str, str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [_entity("invalid-invocation", "tool_invocation", "Invocation missing target tool", {"completeness": "complete", "call_site_id": "invalid.node.tool", "call_site_location": "negative fixture"}, iris, evidence_ids)]


def _select_bindings(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        return result.get("results", {}).get("bindings", [])
    return []


def scoped_query_texts(iris: dict[str, str], entities: dict[str, str]) -> dict[str, str]:
    """Return the four fixed behavior assertions without executing them."""
    prefixes = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    caller_query = prefixes + f"""SELECT ?caller WHERE {{
      ?caller <{iris['has_version']}>/(<{iris['has_invocation']}>/<{iris['invokes_tool']}>/<{iris['tool_targets_version']}>)+ <{entities['c-v2']}> .
    }} ORDER BY ?caller"""
    context_query = prefixes + f"""SELECT ?change ?cBeforeVersion ?cVersion ?cInput ?bInvocation ?bInputBinding ?bUpstream ?bQualityBinding ?cOutput ?bQuality ?bUse ?bApproved ?aInvocation ?aBinding ?aPublish ?aUse ?bCallSiteId ?bCallSiteLocation ?aCallSiteId ?aCallSiteLocation ?bUseKind ?aUseKind WHERE {{
      ?change <{iris['change_applies_to_version']}> ?cVersion ; <{iris['previous_version']}> ?cBeforeVersion ; <{iris['deletes_variable']}> ?cOutput ; <{iris['publication_state']}> "latest" .
      <{entities['c']}> <{iris['active_latest_version']}> ?cVersion .
      ?cInput <{iris['declared_by_version']}> ?cVersion .
      <{entities['b-v1']}> <{iris['has_invocation']}> ?bInvocation . ?bInvocation <{iris['invokes_tool']}> <{entities['tool-c']}> ; <{iris['binding_at_invocation']}> ?bInputBinding, ?bQualityBinding ; <{iris['call_site_id']}> ?bCallSiteId ; <{iris['call_site_location']}> ?bCallSiteLocation .
      ?bInputBinding <{iris['binding_source']}> ?bUpstream ; <{iris['binding_target']}> ?cInput .
      ?bQualityBinding <{iris['binding_source']}> ?cOutput ; <{iris['binding_target']}> ?bQuality .
      <{entities['b-v1']}> <{iris['has_use']}> ?bUse . ?bUse <{iris['uses_variable']}> ?bQuality ; <{iris['produces_variable']}> ?bApproved ; <{iris['use_kind']}> ?bUseKind .
      <{entities['a-v1']}> <{iris['has_invocation']}> ?aInvocation . ?aInvocation <{iris['invokes_tool']}> <{entities['tool-b']}> ; <{iris['binding_at_invocation']}> ?aBinding ; <{iris['call_site_id']}> ?aCallSiteId ; <{iris['call_site_location']}> ?aCallSiteLocation .
      ?aBinding <{iris['binding_source']}> ?bApproved ; <{iris['binding_target']}> ?aPublish .
      <{entities['a-v1']}> <{iris['has_use']}> ?aUse . ?aUse <{iris['uses_variable']}> ?aPublish ; <{iris['use_kind']}> ?aUseKind .
      VALUES (?change ?cBeforeVersion ?cVersion ?cInput ?bInvocation ?bInputBinding ?bUpstream ?bQualityBinding ?cOutput ?bQuality ?bUse ?bApproved ?aInvocation ?aBinding ?aPublish ?aUse) {{
        (<{entities['published-delete-quality']}> <{entities['c-v1']}> <{entities['c-v2']}> <{entities['c-content']}> <{entities['b-c-invocation']}> <{entities['b-content-binding']}> <{entities['b-content-source']}> <{entities['b-quality-binding']}> <{entities['c-quality-score']}> <{entities['b-quality-score']}> <{entities['b-if-use']}> <{entities['b-approved-content']}> <{entities['a-b-invocation']}> <{entities['a-approved-binding']}> <{entities['a-publish-content']}> <{entities['a-publish-use']}>)
      }}
    }}"""
    draft_query = f"""SELECT ?draftVersion ?activeLatestVersion WHERE {{
      <{entities['c']}> <{iris['has_version']}> ?draftVersion ; <{iris['active_latest_version']}> ?activeLatestVersion .
      ?draftVersion <{iris['publication_state']}> "current-draft" . FILTER(?draftVersion != ?activeLatestVersion)
    }}"""
    gap_query = f"""SELECT ?gap ?detail WHERE {{ ?gap <{iris['completeness']}> "explicit-gap" ; <{iris['unknown_detail']}> ?detail . }}"""
    return {"callers": caller_query, "context": context_query, "draft": draft_query, "gap": gap_query}


def scoped_queries(client: PublicApi, project_id: str, ontology_id: str, iris: dict[str, str], entities: dict[str, str]) -> dict[str, Any]:
    scope = {"project_id": project_id, "scope_mode": "ontologies", "ontology_ids": [ontology_id], "result_limit": 20}
    queries = scoped_query_texts(iris, entities)
    responses = {}
    for name, query in queries.items():
        responses[name] = client.post("/api/semantic/sparql:query", {**scope, "query": query})
    callers = {row["caller"]["value"] for row in _select_bindings(responses["callers"].get("result"))}
    _assert(callers == {entities["a"], entities["b"]}, f"caller assertion failed: {callers}")
    context_rows = _select_bindings(responses["context"].get("result"))
    _assert(len(context_rows) == 1, "expected exactly one full C -> B -> A context row")
    context = context_rows[0]
    expected_context = {
        "change": entities["published-delete-quality"], "cBeforeVersion": entities["c-v1"], "cVersion": entities["c-v2"], "cInput": entities["c-content"], "bInvocation": entities["b-c-invocation"], "bInputBinding": entities["b-content-binding"], "bUpstream": entities["b-content-source"], "bQualityBinding": entities["b-quality-binding"], "cOutput": entities["c-quality-score"], "bQuality": entities["b-quality-score"], "bUse": entities["b-if-use"], "bApproved": entities["b-approved-content"], "aInvocation": entities["a-b-invocation"], "aBinding": entities["a-approved-binding"], "aPublish": entities["a-publish-content"], "aUse": entities["a-publish-use"],
    }
    for name, expected in expected_context.items():
        _assert(context.get(name, {}).get("value") == expected, f"context assertion failed for {name}")
    for name, expected in {"bCallSiteId": "b-v1.node.tool-c", "bCallSiteLocation": "B Tool node C", "aCallSiteId": "a-v1.node.tool-b", "aCallSiteLocation": "A Tool node B", "bUseKind": "if-else", "aUseKind": "output"}.items():
        _assert(context.get(name, {}).get("value") == expected, f"context assertion failed for {name}")
    _assert(len(_select_bindings(responses["draft"].get("result"))) == 1, "draft/latest separation query failed")
    _assert(len(_select_bindings(responses["gap"].get("result"))) == 1, "explicit-gap query failed")
    return responses


def _safe(value: Any) -> Any:
    """Remove secret-shaped keys recursively before any local persistence."""
    if isinstance(value, dict):
        return {key: "[redacted]" if re.search(r"(?:authorization|token|api.?key|cookie)", key, re.I) else _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _append_log(record: dict[str, Any]) -> None:
    lines = [
        f"\n## {record['finished_at']} — {record['run_tag']}",
        f"- Project/Ontology/Build Session: `{record['project_id']}` / `{record['ontology_id']}` / `{record['build_session_id']}`",
        f"- Modes: regular expected `{record['mode_probe']['expected_regular_mode']}`; isolated observed `{record['mode_probe']['isolated_product_write_mode']}`.",
        f"- Bad Shape: `{record['batches']['bad_shape']['attempt_status']}`; invalid Invocation: `{record['batches']['invalid_invocation']['attempt_status']}`.",
        f"- Validation/reasoning: `{record['validation']['run_id']}` / `{record['reasoning']['run_id']}`; Graph Set shapes member `{record['validation']['shape_graph_iri']}`.",
        "- Runtime record: `runtime/runtime-record.json`; secrets deliberately excluded.",
    ]
    if record.get("corrects_run_tag"):
        lines.append(f"- Corrects prior run: `{record['corrects_run_tag']}`.")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_runtime_record(record: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    payload = json.dumps(_safe(record), indent=2, ensure_ascii=False) + "\n"
    RUNTIME_RECORD.write_text(payload, encoding="utf-8")
    (RUNTIME_DIR / f"runtime-record-{record['run_tag']}.json").write_text(payload, encoding="utf-8")


def _batch_trace(record: dict[str, Any]) -> str:
    traces = []
    for label, entry in record.get("batches", {}).items():
        responses = entry.values() if isinstance(entry, dict) and "attempt_status" not in entry else [entry]
        for response in responses:
            if not isinstance(response, dict):
                continue
            codes = ",".join(sorted({str(finding.get("code")) for finding in response.get("findings", [])}))
            traces.append(
                f"{label}: batch={response.get('batch_id')} attempt={response.get('attempt_id')} "
                f"status={response.get('attempt_status')} findings={codes or '-'}"
            )
    return "; ".join(traces) or "no Batch response was received before failure"


def _append_failure_log(record: dict[str, Any]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n".join(
                [
                    f"\n## {record['finished_at']} — {record['run_tag']} (failed)",
                    f"- Last stage: `{record.get('stage', 'unknown')}`.",
                    f"- Project/Ontology/Build Session: `{record.get('project_id')}` / `{record.get('ontology_id')}` / `{record.get('build_session_id')}`.",
                    f"- Batch trace: {_batch_trace(record)}.",
                    *(
                        [f"- Corrects prior run: `{record['corrects_run_tag']}`."]
                        if record.get("corrects_run_tag")
                        else []
                    ),
                    "- Safe partial runtime record retained at `runtime/runtime-record.json`; no credentials or lease tokens were recorded.",
                ]
            )
            + "\n"
        )


def run(base_url: str, api_key: str, corrects_run_tag: str | None = None) -> dict[str, Any]:
    """Persist safe progress after every public stage, including failure paths."""
    record: dict[str, Any] = {
        "schema_version": 1,
        "run_tag": uuid.uuid4().hex[:12],
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "base_url": base_url,
        "corrects_run_tag": corrects_run_tag,
        "stage": "initializing",
        "batches": {},
        "public_calls": [],
    }
    _write_runtime_record(record)
    try:
        result = _run(base_url, api_key, record)
    except Exception as exc:
        record.update({
            "status": "failed",
            "finished_at": datetime.now(UTC).isoformat(),
            "error": str(exc).replace(api_key, "[redacted]"),
        })
        _write_runtime_record(record)
        _append_failure_log(record)
        raise
    record.update({"status": "succeeded", "finished_at": datetime.now(UTC).isoformat()})
    _write_runtime_record(record)
    _append_log(record)
    return result


def _run(base_url: str, api_key: str, record: dict[str, Any]) -> dict[str, Any]:
    client = PublicApi(base_url, api_key)
    run_tag = record["run_tag"]
    health = client.get("/api/health")
    _assert(health is not None, "isolated health endpoint returned no result")
    mode = client.get("/api/semantic/canonical-mode")
    _assert(mode.get("product_write_mode") == "rdf_primary", f"isolated backend must be rdf_primary, got {mode}")
    record.update({"stage": "mode-probed", "mode_probe": {"expected_regular_mode": "legacy_only", "isolated_product_write_mode": mode["product_write_mode"]}, "public_calls": client.calls})
    _write_runtime_record(record)
    project = client.post("/api/projects", {"name": f"M2 controlled rehearsal {run_tag}", "description": "Fresh synthetic R2.1-001 M2 rehearsal workspace."})
    project_id = project["id"]
    record.update({"stage": "project-created", "project_id": project_id, "public_calls": client.calls})
    _write_runtime_record(record)
    ontology = client.post(f"/api/projects/{project_id}/ontologies", {"name": "Workflow-as-Tool impact M2", "description": "Fresh M2 controlled modeling candidate."})
    ontology_id = ontology["id"]
    record.update({"stage": "ontology-created", "ontology_id": ontology_id, "graph_set_id": ontology["workspace"]["default_graph_set_id"], "public_calls": client.calls})
    _write_runtime_record(record)
    session = client.post(f"/api/projects/{project_id}/build-sessions", {"client_session_id": f"m2-{run_tag}"})
    session_id = session["id"]
    record.update({"stage": "build-session-created", "build_session_id": session_id, "public_calls": client.calls})
    _write_runtime_record(record)
    official = client.post(f"/api/projects/{project_id}/evidence-references", {"document_name": "M1 immutable source-pack manifest", "excerpt": "Dify documentation snapshot commit 5396c1a1afbea0dee3d089abfabdf6dac91d30d5; official-source claims only."})
    synthetic = client.post(f"/api/projects/{project_id}/evidence-references", {"document_name": "M2 synthetic C-B-A fixture", "excerpt": "C, B and A workflow names, variables and call topology are synthetic evaluation facts, not official Dify product facts."})
    model_contract = client.post(f"/api/projects/{project_id}/evidence-references", {"document_name": "M2 reviewed model contract", "excerpt": "Reviewed generic Modeling Batch contract: constrained object predicates are ObjectProperties; Shapes enforce structure; the platform returns facts rather than Dify impact conclusions."})
    tbox_evidence_ids = [official["id"], model_contract["id"]]
    fixture_evidence_ids = [synthetic["id"]]
    record.update({"stage": "evidence-created", "evidence_references": {"official": official["id"], "synthetic_fixture": synthetic["id"], "model_contract": model_contract["id"]}, "evidence_bindings": {"bad_shape": [model_contract["id"]], "tbox_shapes": tbox_evidence_ids, "published": fixture_evidence_ids, "draft": fixture_evidence_ids, "explicit_gap": fixture_evidence_ids, "invalid_invocation": fixture_evidence_ids}, "public_calls": client.calls})
    _write_runtime_record(record)
    lease = client.post(f"/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire", {"client_request_id": f"m2-{run_tag}-lease", "expected_session_revision": session["revision"]})
    lease_token = lease["lease_token"]

    def record_batch_response(label: str) -> Callable[[str, dict[str, Any]], None]:
        def persist(phase: str, response: dict[str, Any]) -> None:
            record["batches"].setdefault(label, {})[phase] = response
            record["public_calls"] = client.calls
            _write_runtime_record(record)

        return persist

    record.update({"stage": "bad-shape-dry-run", "public_calls": client.calls})
    _write_runtime_record(record)
    bad = _submit(client, session_id, ontology_id, run_tag, "bad-shape", "dry_run", _workspace_version(client, ontology_id), bad_shape_items([model_contract["id"]]))
    record["batches"]["bad_shape"] = bad
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    _expected_status(bad, "validation_failed", "bad Shape dry-run")
    _assert(any(finding.get("blocking") for finding in bad.get("findings", [])), "bad Shape returned no blocking finding")

    record.update({"stage": "tbox-shapes", "public_calls": client.calls})
    _write_runtime_record(record)
    tbox_dry, tbox_apply = _dry_run_then_apply(client, session_id, ontology_id, run_tag, "tbox-shapes", tbox_and_shapes_items(tbox_evidence_ids), lease_token, record_batch_response("tbox_shapes"))
    record["batches"]["tbox_shapes"] = {"dry_run": tbox_dry, "apply": tbox_apply}
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    iris = _output_iris(tbox_dry)
    _assert(set(OBJECT_PROPERTIES) <= set(iris), "TBox did not emit every object property")
    record.update({"stage": "published-fixture", "public_calls": client.calls})
    _write_runtime_record(record)
    published_dry, published_apply = _dry_run_then_apply(client, session_id, ontology_id, run_tag, "published", published_fixture_items(iris, fixture_evidence_ids), lease_token, record_batch_response("published"))
    record["batches"]["published"] = {"dry_run": published_dry, "apply": published_apply}
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    entities = _output_iris(published_dry)
    record.update({"stage": "draft-fixture", "public_calls": client.calls})
    _write_runtime_record(record)
    draft_dry, draft_apply = _dry_run_then_apply(client, session_id, ontology_id, run_tag, "draft", draft_fixture_items(iris, fixture_evidence_ids, entities), lease_token, record_batch_response("draft"))
    record["batches"]["draft"] = {"dry_run": draft_dry, "apply": draft_apply}
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    entities.update(_output_iris(draft_dry))
    record.update({"stage": "explicit-gap-fixture", "public_calls": client.calls})
    _write_runtime_record(record)
    gap_dry, gap_apply = _dry_run_then_apply(client, session_id, ontology_id, run_tag, "explicit-gap", explicit_gap_items(iris, fixture_evidence_ids), lease_token, record_batch_response("explicit_gap"))
    record["batches"]["explicit_gap"] = {"dry_run": gap_dry, "apply": gap_apply}
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    entities.update(_output_iris(gap_dry))
    record.update({"stage": "invalid-invocation-dry-run", "public_calls": client.calls})
    _write_runtime_record(record)
    invalid = _submit(client, session_id, ontology_id, run_tag, "invalid-invocation", "dry_run", _workspace_version(client, ontology_id), invalid_invocation_items(iris, fixture_evidence_ids))
    record["batches"]["invalid_invocation"] = invalid
    record["public_calls"] = client.calls
    _write_runtime_record(record)
    _expected_status(invalid, "validation_failed", "invalid Invocation dry-run")
    _assert(any(finding.get("blocking") for finding in invalid.get("findings", [])), "invalid Invocation returned no blocking finding")

    graph_set_id = ontology["workspace"]["default_graph_set_id"]
    graph_set = client.get(f"/api/semantic/graph-sets/{graph_set_id}")
    shape_members = [member["graph_iri"] for member in graph_set["members"] if member.get("role") == "shapes"]
    _assert(len(shape_members) == 1, f"expected exactly one Graph Set shapes member, got {shape_members}")
    validation_request = {"shape_graph_iris": shape_members, "validation_scope": "asserted_only", "persist_report_graph": True}
    record.update({"stage": "managed-validation", "graph_set": {"id": graph_set_id, "shapes_member": shape_members[0]}, "public_calls": client.calls})
    _write_runtime_record(record)
    validation = client.post(f"/api/semantic/graph-sets/{graph_set_id}/validation-runs", validation_request)
    record.update({"validation": {"request": validation_request, "run_id": validation["run_id"], "status": validation["status"], "conforms": validation.get("conforms"), "shape_graph_iri": shape_members[0]}, "public_calls": client.calls})
    _write_runtime_record(record)
    _assert(validation.get("status") == "succeeded" and validation.get("conforms") is True, f"managed validation failed: {validation}")
    validation_read = client.get(f"/api/semantic/validation-runs/{validation['run_id']}")
    record.update({"stage": "managed-reasoning", "graph_set": {"id": graph_set_id, "source_signature": validation_read.get("source_signature"), "shapes_member": shape_members[0]}, "public_calls": client.calls})
    _write_runtime_record(record)
    reasoning = client.post(f"/api/semantic/graph-sets/{graph_set_id}/reasoning-runs", {"tasks": ["consistency"], "persist_result_graph": True})
    record.update({"reasoning": {"run_id": reasoning["run_id"], "status": reasoning["status"], "consistent": reasoning.get("consistent"), "result_graph_iri": reasoning.get("result_graph_iri")}, "public_calls": client.calls})
    _write_runtime_record(record)
    _assert(reasoning.get("status") == "succeeded" and reasoning.get("consistent") is True, f"reasoning failed: {reasoning}")
    expected_entailment = {"subject": entities["c-v2"], "predicate": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "object": iris["workflow_version"], "rule": "rdfs:subClassOf"}
    _assert(any(expected_entailment.items() <= entailment.items() for entailment in reasoning.get("entailments", [])), "missing PublishedWorkflowVersion -> WorkflowVersion entailment")
    record.update({"stage": "scoped-query-assertions", "public_calls": client.calls})
    _write_runtime_record(record)
    queries = scoped_queries(client, project_id, ontology_id, iris, entities)
    record.update({"stage": "complete", "query_assertions": queries, "public_calls": client.calls})
    _write_runtime_record(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8012")
    parser.add_argument("--api-key-env", default=API_KEY_ENV)
    parser.add_argument("--corrects-run-tag")
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"{args.api_key_env} must be set in the environment", file=sys.stderr)
        return 2
    try:
        record = run(args.base_url, api_key, args.corrects_run_tag)
    except RehearsalError as exc:
        print(f"M2 rehearsal stopped: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"run_tag": record["run_tag"], "runtime_record": str(RUNTIME_RECORD.relative_to(PACKAGE))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
