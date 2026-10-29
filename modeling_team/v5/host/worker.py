"""Host-only provider and deterministic platform capabilities in the backend environment."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
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

            def resolve(ref):
                if ref.get("artifact_ref") == "applied-bindings.json":
                    return bindings.get(ref.get("path", "").removeprefix("/"))
                return None

            changes = intent["changes"]
            raw_changes = changes.get("changes", []) if isinstance(changes, dict) else []
            raw_changes = raw_changes if isinstance(raw_changes, list) else []
            ontology_by_item = {
                item.get("item_id") or item.get("change_id"): scope.ontology_id
                for item in raw_changes
                if isinstance(item, dict)
            }
            try:
                batches, source_map = compile_model_changes(
                    changes,
                    candidate=intent["candidate"],
                    ontology_by_item=ontology_by_item,
                    resolve_binding=resolve,
                )
            except ModelChangeCompilationError as error:
                return {"status": "not_written", "errors": error.errors}
            plan = {"intent_digest": digest(intent), "batches": batches, "source_map": source_map}
            write_json(plan_path, plan)
        forwarder = self.forwarder(scope)
        try:
            executor = self.executor(scope, root, forwarder, allow_submit=not reconcile)
            result = execute_bound_model_changes(executor, plan["batches"], plan["source_map"])
            write_json(root / "result.json", result)
            bindings_path = self.root / "applied-bindings.json"
            bindings = json.loads(bindings_path.read_text()) if bindings_path.exists() else {}
            for batch in result.get("batches", []):
                for binding in batch.get("resource_bindings", []):
                    if binding.get("change_id"):
                        bindings[binding["change_id"]] = {
                            **binding,
                            "ontology_id": scope.ontology_id,
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

    def finalize(self) -> dict:
        scope = self.scope()
        forwarder = self.forwarder(scope)
        try:
            for root in sorted((self.root / "operations").glob("*")):
                if not (root / "compiled.json").exists():
                    continue
                if not (root / "result.json").exists():
                    raise FrameworkError("application_outcome_unknown")
                result = json.loads((root / "result.json").read_text())
                if result.get("status") != "completed":
                    raise FrameworkError("application_incomplete")
                closed = self.executor(scope, root, forwarder, allow_submit=False).close_session()
                write_json(root / "session-completion.json", closed)
                if not closed["closed"]:
                    raise FrameworkError("session_close_unconfirmed")
                if closed.get("session_id"):
                    scope.completed_session_id = closed["session_id"]
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
    from ontoweave_modeling.team import TEAM_TOOLS

    allowed_tools = {"read_material", "query_semantic_context"}
    if role == "modeling" and binding.data.get("collaboration"):
        allowed_tools.update(TEAM_TOOLS)
    if role == "modeling" and binding.data.get("shared_memory"):
        allowed_tools.update(MEMORY_TOOLS)
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
            worker = PlatformWorker(binding)
            if args.operation == "prepare_scope":
                worker.scope(prepare=True)
                result = worker.snapshot()
            elif args.operation in {"apply", "reconcile"}:
                result = worker.apply(payload, reconcile=args.operation == "reconcile")
            elif args.operation == "read_config":
                result = worker.read_config(payload)
            else:
                result = getattr(worker, args.operation)()
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
