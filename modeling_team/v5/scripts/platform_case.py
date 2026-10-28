"""Host-only P0 platform probe, executed with the existing backend environment.

Reuses the accepted compiler, executor, lifecycle and canonical MCP forwarders.
Faults affect only this probe's client boundary and owned test resources.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from modeling_team.__main__ import _bootstrap_helpers
from modeling_team.acceptance_runtime import McpReadForwarder
from modeling_team.direct_execution import DirectModelExecutor
from modeling_team.direct_modeling import compile_model_changes
from modeling_team.platform_scope import PlatformScope
from modeling_team.staged_batch_write_forwarder import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    forward_staged_modeling_batch,
)

SCOPE_FIELDS = (
    "base_url",
    "run_id",
    "admin_key",
    "admin_key_id",
    "protocol_key",
    "protocol_key_id",
    "project_id",
    "ontology_id",
    "mode",
    "owned",
    "key_user_id",
)
READ_TOOLS = (
    "get_modeling_context",
    "get_modeling_batch",
    "list_session_modeling_batches",
    "query_semantic_context",
    "get_entity_statement_context",
)


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_scope(root: Path):
    create, revoke = _bootstrap_helpers(ROOT)
    path = root / "scope-private.json"
    if path.exists():
        values = json.loads(path.read_text())
        owned_sessions = values.pop("owned_session_ids", [])
        scope = PlatformScope(**values, bootstrap_admin=create, revoke_admin=revoke)
        scope.owned_session_ids = set(owned_sessions)
        return scope
    run_id = str(root.relative_to(ROOT / "workspaces")).replace("/", ":")
    scope = PlatformScope("http://127.0.0.1:8001", run_id, create, revoke)
    scope.prepare({"mode": "create"})
    save_scope(root, scope)
    return scope


def save_scope(root: Path, scope):
    write(
        root / "scope-private.json",
        {
            **{key: getattr(scope, key) for key in SCOPE_FIELDS},
            "owned_session_ids": sorted(scope.owned_session_ids),
        },
    )
    (root / "scope-private.json").chmod(0o600)


def apply(root: Path, scope, plan: dict, *, fault: str):
    readback = McpReadForwarder(
        repository_root=ROOT, read_key=scope.protocol_key, expected_tools=READ_TOOLS
    ).start()
    blocked_reads = False
    submits = 0
    operation_log = root / "platform-calls.jsonl"

    def record(event, **extra):
        with operation_log.open("a") as stream:
            stream.write(json.dumps({"event": event, "fault": fault, **extra}) + "\n")

    def read(tool, arguments):
        if blocked_reads:
            raise TimeoutError("P0 controlled unavailable read after uncertain dispatch")
        result = readback.forward(tool, arguments, scope.protocol_key)
        record("read", tool=tool)
        return result

    def submit(batch):
        nonlocal blocked_reads, submits
        submits += 1
        record(
            "submit_enter",
            client_batch_id=batch["client_batch_id"],
            idempotency_key=batch["idempotency_key"],
        )
        if fault == "partial" and submits == 2:
            record("definite_no_dispatch")
            raise StagedBatchForwardError("P0 controlled second-batch pre-dispatch rejection")
        if fault == "not_written":
            blocked_reads = True
            record("transport_unknown_no_dispatch")
            # The executor cannot know that this client-side transport loss
            # preceded dispatch. A later authoritative listing establishes it.
            raise ConnectionError("P0 controlled lost transport before dispatch")
        result = forward_staged_modeling_batch(
            batch, repository_root=ROOT, protocol_key=scope.protocol_key
        )
        record(
            "platform_applied",
            batch_id=result.get("batch_id"),
            attempt_id=result.get("attempt_id"),
            attempt_status=result.get("attempt_status"),
        )
        if fault == "response_loss":
            blocked_reads = True
            raise StagedBatchForwardUnknown("P0 controlled response loss after actual application")
        return result

    executor = DirectModelExecutor(
        scope, root / "execution", scope.run_id, "definitions", submit, read
    )
    try:
        changes = [
            {
                "change_id": item["key"],
                "action": "create",
                "resource_kind": "class",
                "item_id": None,
                "target_ref": None,
                "fields": {
                    key: item[key] for key in ("name", "description", "semantic_definition")
                },
            }
            for item in plan["concepts"]
        ]
        request = {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": changes,
        }
        compiled_path = root / "compiled-definitions.json"
        if compiled_path.exists():
            compiled = json.loads(compiled_path.read_text())
            if compiled["request"] != request:
                raise ValueError(
                    "frozen definition intent changed; submit an explicit new revision"
                )
            batches, source_map = compiled["batches"], compiled["source_map"]
        else:
            batches, source_map = compile_model_changes(
                request,
                candidate=None,
                ontology_by_item={item["change_id"]: scope.ontology_id for item in changes},
                resolve_binding=lambda _: None,
                batch_max_items=1 if fault == "partial" else 100,
            )
            write(compiled_path, {"request": request, "batches": batches, "source_map": source_map})
        result = executor.execute(batches, source_map)
        write(root / f"definitions-{fault}.json", result)
        save_scope(root, scope)
        if result["status"] != "completed" or fault != "normal":
            return {"status": result["status"], "submits": submits, "result": result}
        bindings = {
            binding["change_id"]: {**binding, "ontology_id": scope.ontology_id}
            for batch in result["batches"]
            for binding in batch["resource_bindings"]
        }
        write(root / "definition-bindings.json", bindings)
        relations = []
        for item in plan["relationships"]:
            fields = {key: item[key] for key in ("name", "description", "semantic_definition")}
            for field, key in (
                ("source_class_id", "source_key"),
                ("target_class_id", "target_key"),
            ):
                fields[field] = {
                    "existing_resource_ref": {
                        "artifact_ref": "definition-bindings.json",
                        "path": "/" + item[key],
                    }
                }
            relations.append(
                {
                    "change_id": item["key"],
                    "action": "create",
                    "item_id": None,
                    "target_ref": None,
                    "resource_kind": "relation_type",
                    "fields": fields,
                }
            )
        if relations:
            relation_request = {**request, "changes": relations}
            batches, source_map = compile_model_changes(
                relation_request,
                candidate=None,
                ontology_by_item={item["change_id"]: scope.ontology_id for item in relations},
                resolve_binding=lambda ref: bindings.get(ref["path"][1:]),
            )
            relation_result = executor.execute(batches, source_map)
            write(root / "relations.json", relation_result)
            if relation_result["status"] != "completed":
                return {
                    "status": relation_result["status"],
                    "submits": submits,
                    "result": relation_result,
                }
        completion = executor.close_session()
        write(root / "session-completion.json", completion)
        context = read("get_modeling_context", {"ontology_id": scope.ontology_id})
        governed = read(
            "query_semantic_context",
            {
                "project_id": scope.project_id,
                "scope_mode": "ontologies",
                "ontology_ids": [scope.ontology_id],
                "queries": [item["name"] for item in plan["concepts"]],
                "search_mode": "lexical",
                "context_detail": "full",
                "limit": 20,
                "context_limit": 100,
            },
        )
        write(root / "governed-readback.json", governed)
        assert governed.get("ok") is True, governed
        write(root / "modeling-context.json", context)
        write(
            root / "public-target.json",
            {
                "project_id": scope.project_id,
                "ontology_id": scope.ontology_id,
                "modeling_context": context,
                "semantic_acceptance": "unverified",
            },
        )
        return {
            "status": "completed",
            "submits": submits,
            "project_id": scope.project_id,
            "ontology_id": scope.ontology_id,
            "session_closed": completion["closed"],
        }
    finally:
        save_scope(root, scope)
        readback.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("apply", "cleanup", "acceptance-config", "revoke-acceptance")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument(
        "--fault",
        choices=("normal", "checkpoint_loss", "response_loss", "not_written", "partial"),
        default="normal",
    )
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    scope = load_scope(root)
    if args.action == "acceptance-config":
        path = root / "acceptance-private.json"
        if path.exists():
            raise RuntimeError("acceptance credential already exists; reuse its bound identity")
        key = scope._ok(
            "POST",
            "/api/api-keys",
            {
                "name": scope.run_id + "-independent-read",
                "project_id": scope.project_id,
                "user_id": scope.key_user_id,
                "scopes": ["read"],
            },
            statuses={201},
        )
        write(
            path,
            {
                "base_url": scope.base_url,
                "project_id": scope.project_id,
                "ontology_ids": [scope.ontology_id],
                "read_key": key["plaintext_key"],
                "read_key_id": key["id"],
            },
        )
        path.chmod(0o600)
        result = {"read_key_id": key["id"], "scope": "read", "project_id": scope.project_id}
    elif args.action == "revoke-acceptance":
        config = json.loads((root / "acceptance-private.json").read_text())
        revoked = scope._ok("POST", f"/api/api-keys/{config['read_key_id']}:revoke")
        result = {"read_key_id": config["read_key_id"], "revoked": bool(revoked.get("revoked_at"))}
        assert result["revoked"], "acceptance credential revocation is unconfirmed"
        write(root / "acceptance-key-revocation.json", result)
    elif args.action == "cleanup":
        summary_path = root / "summary-normal.json"
        if summary_path.exists():
            scope.terminal_results = {"probe": json.loads(summary_path.read_text())}
        scope.retain_nonempty = True
        completion = root / "session-completion.json"
        if completion.exists():
            scope.completed_session_id = json.loads(completion.read_text())["session_id"]
        result = scope.cleanup()
        write(root / "cleanup.json", result)
        save_scope(root, scope)
    else:
        result = apply(root, scope, json.loads(args.plan.read_text()), fault=args.fault)
        write(root / f"summary-{args.fault}.json", result)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "result"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
