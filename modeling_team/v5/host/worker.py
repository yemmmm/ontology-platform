"""Host-only provider and deterministic platform capabilities in the backend environment."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
from dataclasses import fields
from pathlib import Path

from ontoweave_modeling.contracts import (
    FrameworkError,
    TaskBinding,
    digest,
    outbound_tool_names,
    safe_id,
    write_json,
)

ROOT = Path(__file__).resolve().parents[3]
READ_TOOLS = (
    "get_modeling_context",
    "get_modeling_batch",
    "list_session_modeling_batches",
    "query_semantic_context",
    "get_entity_statement_context",
)


def model_tool_projection(items):
    """Expose the configured MCP tools, without Codex's unused generic resource facade."""
    result = []
    for item in items:
        if item.get("type") == "namespace":
            nested = model_tool_projection(item["tools"])
            if nested:
                result.append({**item, "tools": nested})
        elif item.get("name") not in {
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
        }:
            result.append(item)
    return result


class PlatformWorker:
    def __init__(self, binding: TaskBinding):
        self.binding = binding
        self.root = binding.root / "host"
        self.root.mkdir(exist_ok=True, mode=0o700)

    def scope(self, *, prepare: bool = False):
        from modeling_team.platform_bootstrap import bootstrap_helpers
        from modeling_team.platform_scope import PlatformScope

        create, revoke = bootstrap_helpers(ROOT)
        path = self.root / "scope-private.json"
        if path.exists():
            values = json.loads(path.read_text())
            values["owned_session_ids"] = set(values.get("owned_session_ids", []))
            return PlatformScope(**values, bootstrap_admin=create, revoke_admin=revoke)
        if not prepare:
            raise FrameworkError("platform_scope_not_prepared")
        intent = self.root / "scope-intent.json"
        if intent.exists():
            raise FrameworkError("scope_reconciliation_required")
        write_json(
            intent, {"scope": self.binding.data["scope"], "run_id": self.binding.data["run_id"]}
        )
        scope = PlatformScope(
            self.binding.data["scope"]["base_url"], self.binding.data["run_id"], create, revoke
        )
        scope.prepare(
            {key: value for key, value in self.binding.data["scope"].items() if key != "base_url"}
        )
        self.save_scope(scope)
        return scope

    def save_scope(self, scope):
        values = {}
        for field in fields(scope):
            value = getattr(scope, field.name)
            if not callable(value):
                values[field.name] = sorted(value) if isinstance(value, set) else value
        write_json(self.root / "scope-private.json", values)

    def read_binding(self, scope, reference):
        """Resolve an exact authorized native read, never infer identity from a label or IRI."""
        from urllib.parse import quote

        parts = reference.get("artifact_ref", "").split(":", 2)
        kinds = {
            "class-detail": "class",
            "property-list": "property",
            "relation-type-list": "relation_type",
            "entity-detail": "entity",
        }
        if len(parts) != 3 or parts[0] != "model-read" or parts[1] not in kinds:
            return None
        family, ontology_id = parts[1:]
        if ontology_id not in (scope.ontology_ids or [scope.ontology_id]):
            raise FrameworkError("reference_scope_forbidden")
        iri = reference["path"].removeprefix("/")
        envelope = scope._ok(
            "GET",
            "/api/semantic/ontologies/"
            + ontology_id
            + "/read-models/"
            + family
            + "?entity="
            + quote(iri, safe="")
            + "&field_set=detail",
        )
        item = next((row for row in envelope["items"] if row["iri"] == iri), None)
        if item is None:
            return None
        resource_id = item.get("resource_id")
        if not resource_id and item.get("id") != iri:
            resource_id = item.get("id")
        if not resource_id:
            # semantic-read-v2 uses the RDF IRI as id. Use retained application
            # or captured-fork identities; never encode that IRI as a native ID.
            receipts = self.root / "applied-bindings.json"
            applied = json.loads(receipts.read_text()) if receipts.exists() else {}
            resource_id = next(
                (
                    row["resource_id"]
                    for row in applied.values()
                    if row.get("ontology_id") == ontology_id
                    and row.get("resource_kind") == kinds[family]
                    and row.get("resource_iri") == iri
                    and row.get("resource_id")
                ),
                None,
            )
        binding = {
            "ontology_id": ontology_id,
            "resource_kind": kinds[family],
            "resource_iri": item["iri"],
            "resource_id": resource_id,
            "model_revision": envelope["model_revision"],
        }
        write_json(
            self.root / "verified-reads" / (digest(reference) + ".json"),
            {"reference": reference, "binding": binding, "response": envelope},
        )
        return binding

    def checkpoint_data(self, action, payload):
        from modeling_team.checkpoint_data import platform_data_request

        scope = self.scope()
        key, key_id = scope.bootstrap_admin()
        record = self.root / "checkpoint-credentials" / (uuid.uuid4().hex + ".json")
        receipt = {"key_id": key_id, "action": action, "revoked": False}
        write_json(record, receipt)
        try:
            result = platform_data_request(scope.base_url, key, action, payload)
        finally:
            receipt["revoked"] = scope.revoke_admin(key_id)
            write_json(record, receipt)
            if not receipt["revoked"]:
                raise FrameworkError("checkpoint_credential_revocation_unconfirmed", key_id=key_id)
        return {"data": result, "credential": receipt}

    def capture_data(self, payload):
        scope = self.scope()
        return self.checkpoint_data(
            "capture",
            {
                "project_id": scope.project_id,
                "ontology_ids": scope.ontology_ids or [scope.ontology_id],
            },
        )

    def fork_data(self, payload):
        from app.core.config import Settings
        from app.services.semantic_export import namespace_from_settings
        from rdflib import Graph, Literal
        from rdflib.namespace import OWL, RDF, RDFS

        # Read explicit IDs from the captured model before making a copy. The
        # platform fork preserves these RDF statements, while remapping owners.
        snapshot = payload["snapshot"]
        ns = namespace_from_settings(Settings())
        resources = []
        for ontology in snapshot["tables"]["ontologies"]:
            graph = Graph().parse(
                data=snapshot["graphs"][ontology["model_graph_iri"]], format="turtle"
            )
            for subject in set(graph.subjects(ns.vocab.id, None)):
                ids = list(graph.objects(subject, ns.vocab.id))
                if len(ids) != 1 or not isinstance(ids[0], Literal) or not str(ids[0]):
                    continue
                native_id = str(ids[0])
                types = set(graph.objects(subject, RDF.type))
                kinds = set()
                if types & {OWL.Class, RDFS.Class}:
                    kinds.add("class")
                if OWL.DatatypeProperty in types:
                    kinds.add("property")
                if OWL.NamedIndividual in types:
                    kinds.add("entity")
                if OWL.ObjectProperty in types:
                    # Both object-valued properties and relation types use OWL
                    # ObjectProperty. Classify their native namespace using the
                    # explicit ID, never recover an ID from the IRI suffix.
                    for native_kind, kind in (
                        ("property", "property"),
                        ("relation-type", "relation_type"),
                    ):
                        if subject == ns.resource(native_kind, native_id):
                            kinds.add(kind)
                if len(kinds) == 1:
                    resources.append(
                        {
                            "ontology_id": ontology["id"],
                            "resource_kind": kinds.pop(),
                            "resource_id": native_id,
                            "resource_iri": str(subject),
                        }
                    )
        result = self.checkpoint_data("fork", payload)
        mapping = result["data"]["identity_mapping"]
        result["resource_bindings"] = {
            "fork-" + digest(resource)[:24]: {
                **resource,
                "ontology_id": mapping[resource["ontology_id"]],
                "binding_source": "captured-fork-data",
                "source_snapshot_digest": snapshot["digest"],
            }
            for resource in resources
        }
        return result

    def forwarder(self, scope):
        from modeling_team.acceptance_runtime import McpReadForwarder

        return McpReadForwarder(
            repository_root=ROOT, read_key=scope.protocol_key, expected_tools=READ_TOOLS
        ).start()

    def executor(self, scope, operation_root, forwarder, *, allow_submit=True):
        from modeling_team.direct_execution import DirectModelExecutor
        from modeling_team.staged_batch_write_forwarder import (
            StagedBatchForwardError,
            forward_staged_modeling_batch,
        )

        def submit(batch):
            if not allow_submit:
                raise StagedBatchForwardError("reconcile_only: no new submission admitted")
            return forward_staged_modeling_batch(
                batch, repository_root=ROOT, protocol_key=scope.protocol_key
            )

        return DirectModelExecutor(
            scope,
            operation_root / "execution",
            scope.run_id,
            operation_root.name,
            submit,
            lambda tool, args: forwarder.forward(tool, args, scope.protocol_key),
        )

    def apply(self, payload: dict, *, reconcile: bool = False) -> dict:
        from modeling_team.direct_binding import execute_bound_model_changes
        from modeling_team.direct_modeling import ModelChangeCompilationError, compile_model_changes

        operation_id = safe_id(payload["operation_id"])
        root = self.root / "operations" / operation_id
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        intent = {key: payload[key] for key in ("candidate", "changes")}
        if payload.get("ontology_targets"):
            intent["ontology_targets"] = payload["ontology_targets"]
        frozen = root / "intent.json"
        if frozen.exists():
            if json.loads(frozen.read_text()) != intent:
                raise FrameworkError("operation_intent_conflict")
        elif reconcile:
            raise FrameworkError("operation_not_found")
        else:
            write_json(frozen, intent)
        scope = self.scope()
        plan_path = root / "compiled.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            if plan["intent_digest"] != digest(intent):
                raise FrameworkError("operation_intent_conflict")
        else:
            bindings_path = self.root / "applied-bindings.json"
            bindings = json.loads(bindings_path.read_text()) if bindings_path.exists() else {}
            resolved = {}

            def resolve(ref):
                key = digest(ref)
                if key not in resolved:
                    resolved[key] = (
                        bindings.get(ref.get("path", "").removeprefix("/"))
                        if ref.get("artifact_ref") == "applied-bindings.json"
                        else self.read_binding(scope, ref)
                    )
                return resolved[key]

            changes = intent["changes"]
            raw_changes = changes.get("changes", []) if isinstance(changes, dict) else []
            raw_changes = raw_changes if isinstance(raw_changes, list) else []
            authorized = getattr(scope, "ontology_ids", []) or [scope.ontology_id]
            targets = intent.get("ontology_targets", {})
            outside = set(targets.values()) - set(authorized)
            if outside:
                return {
                    "status": "not_written",
                    "errors": [
                        {
                            "code": "ontology_target_forbidden",
                            "path": "/ontology_targets",
                            "message": "Choose from actual authorized ontology_ids",
                            "authorized_ids": authorized,
                        }
                    ],
                }
            ontology_by_item, target_bindings = {}, {}
            for item in raw_changes:
                if not isinstance(item, dict):
                    continue
                change_id = item.get("change_id")
                target = resolve(item["target_ref"]) if item.get("target_ref") else None
                if target:
                    target_bindings[change_id] = target
                    if targets.get(change_id) not in {None, target.get("ontology_id")}:
                        return {
                            "status": "not_written",
                            "errors": [
                                {
                                    "code": "ontology_target_conflict",
                                    "path": "/ontology_targets/" + change_id,
                                    "message": "An existing resource stays in its verified target Ontology",
                                }
                            ],
                        }
                ontology_id = targets.get(change_id) or (target or {}).get("ontology_id")
                if ontology_id is None and len(authorized) == 1:
                    ontology_id = authorized[0]
                if ontology_id:
                    ontology_by_item[change_id] = ontology_id
            try:
                batches, source_map = compile_model_changes(
                    changes,
                    candidate=intent["candidate"],
                    ontology_by_item=ontology_by_item,
                    resolve_binding=resolve,
                )
            except ModelChangeCompilationError as error:
                return {"status": "not_written", "errors": error.errors}
            plan = {
                "intent_digest": digest(intent),
                "batches": batches,
                "source_map": source_map,
                "target_bindings": target_bindings,
            }
            write_json(plan_path, plan)
        forwarder = self.forwarder(scope)
        try:
            self._close_applied_sessions(scope, forwarder, current=root)
            executor = self.executor(scope, root, forwarder, allow_submit=not reconcile)
            result = execute_bound_model_changes(executor, plan["batches"], plan["source_map"])
            write_json(root / "result.json", result)
            bindings_path = self.root / "applied-bindings.json"
            bindings = json.loads(bindings_path.read_text()) if bindings_path.exists() else {}
            for batch in result.get("batches", []):
                for binding in batch.get("resource_bindings", []):
                    if binding.get("change_id"):
                        bindings[binding["change_id"]] = {
                            **plan.get("target_bindings", {}).get(binding["change_id"], {}),
                            **binding,
                            "ontology_id": batch.get("ontology_id", scope.ontology_id),
                        }
            write_json(bindings_path, bindings)
            return result
        finally:
            self.save_scope(scope)
            forwarder.stop()

    def snapshot(self) -> dict:
        scope = self.scope()
        forwarder = self.forwarder(scope)
        try:
            ids = scope.ontology_ids or [scope.ontology_id]
            contexts = {
                oid: forwarder.forward(
                    "get_modeling_context", {"ontology_id": oid}, scope.protocol_key
                )
                for oid in ids
            }
            versions = {
                oid: value["data"]["workspace"]["model_revision"] for oid, value in contexts.items()
            }
            bindings_path = self.root / "applied-bindings.json"
            bindings = json.loads(bindings_path.read_text()) if bindings_path.exists() else {}
            return {
                "project_id": scope.project_id,
                "ontology_ids": ids,
                "model_revisions": versions,
                "resource_bindings": bindings,
                "resource_refs": {
                    identity: {"artifact_ref": "applied-bindings.json", "path": "/" + identity}
                    for identity in bindings
                },
            }
        finally:
            forwarder.stop()

    def read_config(self, payload) -> dict:
        role = payload["role"]
        if role not in {"modeling", "acceptance"}:
            raise FrameworkError("role_not_allowed")
        scope = self.scope()
        path = self.root / f"{role}-read-private.json"
        expected = payload.get("model_revisions")
        if expected is not None and self.snapshot()["model_revisions"] != expected:
            raise FrameworkError("frozen_target_changed")
        if not path.exists():
            intent = self.root / f"{role}-read-intent.json"
            if intent.exists():
                raise FrameworkError("read_key_reconciliation_required")
            write_json(intent, {"role": role})
            key = scope._ok(
                "POST",
                "/api/api-keys",
                {
                    "name": scope.run_id + "-v5-" + role,
                    "project_id": scope.project_id,
                    "user_id": scope.key_user_id,
                    "scopes": ["read"],
                },
                statuses={201},
            )
            write_json(
                path,
                {
                    "base_url": scope.base_url,
                    "project_id": scope.project_id,
                    "ontology_ids": scope.ontology_ids or [scope.ontology_id],
                    "read_key": key["plaintext_key"],
                    "read_key_id": key["id"],
                },
            )
        config = json.loads(path.read_text())
        if expected is not None:
            config["model_revisions"] = expected
        else:
            config.pop("model_revisions", None)
        write_json(path, config)
        return {"config_ref": str(path)}

    def _close_applied_sessions(self, scope, forwarder, *, current=None):
        for root in sorted((self.root / "operations").glob("*")):
            if root == current or not (root / "compiled.json").exists():
                continue
            if not (root / "result.json").exists():
                raise FrameworkError("application_outcome_unknown")
            result = json.loads((root / "result.json").read_text())
            if result.get("status") == "not_written":
                continue
            if result.get("status") != "completed":
                raise FrameworkError("application_incomplete")
            completion = root / "session-completion.json"
            if completion.exists() and json.loads(completion.read_text())["closed"]:
                continue
            executor = self.executor(scope, root, forwarder, allow_submit=False)
            intents, _ = executor._load_records()
            for intent in intents:
                snapshot = executor._load_snapshot(intent)
                if snapshot is not None:
                    executor._adopt_snapshot_context(snapshot, snapshot["batch"]["ontology_id"])
            if executor.session_id:
                executor._refresh_session_revision()
            closed = executor.close_session()
            write_json(completion, closed)
            if not closed["closed"]:
                raise FrameworkError("session_close_unconfirmed")
            if closed.get("session_id"):
                scope.completed_session_id = closed["session_id"]

    def finalize(self) -> dict:
        scope = self.scope()
        forwarder = self.forwarder(scope)
        try:
            self._close_applied_sessions(scope, forwarder)
            self.save_scope(scope)
        finally:
            forwarder.stop()
        return self.snapshot()

    def cleanup(self) -> dict:
        scope = self.scope()
        for path in self.root.glob("*-read-private.json"):
            config = json.loads(path.read_text())
            result = scope._ok("POST", f"/api/api-keys/{config['read_key_id']}:revoke")
            if not result.get("revoked_at"):
                raise FrameworkError("read_key_revocation_unconfirmed")
        scope.retain_nonempty = True
        result = scope.cleanup()
        if result.get("scope_disposition") == "failed-written-retained":
            # Legacy cleanup infers producer outcome from old Runner terminal_results.
            # v5 records its task/evaluation outcome separately from resource disposition.
            result["legacy_scope_disposition"] = result["scope_disposition"]
            result["scope_disposition"] = "written-retained"
            scope.scope_disposition = "written-retained"
        write_json(self.root / "cleanup.json", result)
        self.save_scope(scope)
        return result


def provider(binding, payload):
    from modeling_team.deepseek_provider_proxy import (
        GLM_UPSTREAM_URL,
        ResponsesProviderSession,
        preflight_glm_credential,
        read_glm_credential,
    )
    from modeling_team.usage_capture import NumericReceiptWriter

    role, execution_id = payload["role"], safe_id(payload["execution_id"])
    if role not in {"modeling", "acceptance"}:
        raise FrameworkError("role_not_allowed")
    model = binding.data["models"][role]
    if model["provider"] != "glm-direct":
        raise FrameworkError("provider_route_not_implemented")
    tools = set(payload["tools"])
    from ontoweave_modeling.memory import MEMORY_TOOLS
    from ontoweave_modeling.semantic_workspace import WORKSPACE_TOOLS
    from ontoweave_modeling.team import TEAM_TOOLS
    from ontoweave_modeling.work_plan import WORK_TOOLS

    allowed_tools = {"read_material", "query_semantic_context", "read_model_resource"}
    if role == "modeling" and (
        binding.data.get("collaboration")
        or binding.data.get("work_units")
        or binding.data.get("work_management")
    ):
        allowed_tools.update(TEAM_TOOLS)
    if role == "modeling" and (
        binding.data.get("work_units") or binding.data.get("work_management")
    ):
        allowed_tools.update(WORK_TOOLS)
    if role == "modeling" and binding.data.get("shared_memory"):
        allowed_tools.update(MEMORY_TOOLS)
    if role == "modeling" and binding.data.get("semantic_workspace"):
        allowed_tools.update(WORKSPACE_TOOLS)
    if not tools.issubset(allowed_tools):
        raise FrameworkError("tool_not_allowed")
    credential = preflight_glm_credential()
    usage = NumericReceiptWriter(
        binding.root / "executions" / execution_id / "provider-usage.jsonl",
        {
            "task_ref": binding.data["task_ref"],
            "run_id": binding.data["run_id"],
            "authorization_ref": binding.data["authorization"]["reference"],
            "agent_id": execution_id,
            "role": role,
            "phase": "P1.1",
            "provider": model["provider"],
            "requested_model": model["model"],
            "requested_effort": model["effort"],
            "runtime": "codex",
            "key_ref": credential.key_ref,
        },
    )

    class BoundProvider(ResponsesProviderSession):
        def forward(self, body):
            request = json.loads(body)
            request["tools"] = model_tool_projection(request.get("tools", []))
            return super().forward(json.dumps(request).encode())

        def admit_attempt(self, receipt, *, request=None):
            allowed = {"mcp__workspace__" + tool for tool in tools} | {
                "list_mcp_resources",
                "list_mcp_resource_templates",
                "read_mcp_resource",
            }
            request = request or {}
            if (
                request.get("model") != model["model"]
                or (request.get("reasoning") or {}).get("effort") != model["effort"]
                or not set(outbound_tool_names(request.get("tools", []))).issubset(allowed)
            ):
                self.record_attempt({**receipt, "event": "attempt_end", "status": "not_admitted"})
                return False
            return super().admit_attempt(receipt, request=request)

    session = BoundProvider(
        read_glm_credential(credential),
        provider_id=model["provider"],
        upstream_url=GLM_UPSTREAM_URL,
        on_attempt=usage,
        max_upstream_attempts=1,
    )
    try:
        session.start()
        print(json.dumps({"ok": True, "result": {"base_url": session.base_url}}), flush=True)
        sys.stdin.read()
    finally:
        session.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "operation",
        choices=[
            "inspect",
            "prepare_scope",
            "apply",
            "reconcile",
            "snapshot",
            "finalize",
            "read_config",
            "cleanup",
            "provider",
            "budget",
            "capture_data",
            "fork_data",
        ],
    )
    args = parser.parse_args()
    try:
        if args.operation == "inspect":
            from modeling_team.direct_execution import DirectModelExecutor
            from modeling_team.direct_modeling import compile_model_changes
            from modeling_team.platform_bootstrap import bootstrap_helpers

            result = {
                "runner_loaded": "modeling_team.runner" in sys.modules,
                "compiler": compile_model_changes.__name__,
                "executor": DirectModelExecutor.__name__,
                "bootstrap": bootstrap_helpers.__name__,
            }
        else:
            binding = TaskBinding.load(args.run_dir)
            payload = json.loads(sys.stdin.readline())
            if args.operation == "provider":
                provider(binding, payload)
                return
            if args.operation == "budget":
                from modeling_team.v5.host.budget import amount_state

                result = amount_state(binding, payload.get("addition"), payload.get("role"))
            elif args.operation == "prepare_scope":
                worker = PlatformWorker(binding)
                worker.scope(prepare=True)
                result = worker.snapshot()
            elif args.operation in {"apply", "reconcile"}:
                result = PlatformWorker(binding).apply(
                    payload, reconcile=args.operation == "reconcile"
                )
            elif args.operation == "read_config":
                result = PlatformWorker(binding).read_config(payload)
            elif args.operation in {"capture_data", "fork_data"}:
                result = getattr(PlatformWorker(binding), args.operation)(payload)
            else:
                result = getattr(PlatformWorker(binding), args.operation)()
        print(json.dumps({"ok": True, "result": result}), flush=True)
    except Exception as error:  # noqa: BLE001 - RPC boundary retains traceback privately, returns no secrets
        args.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (args.run_dir / "host-error.log").open("a") as stream:
            traceback.print_exc(file=stream)
        detail = (
            error.as_dict()
            if isinstance(error, FrameworkError)
            else {
                "code": "host_operation_failed",
                "layer": "runtime/infrastructure",
            }
        )
        print(json.dumps({"ok": False, "error": detail}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
