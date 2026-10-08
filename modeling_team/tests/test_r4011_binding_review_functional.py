"""Opt-in real read-only role reports over the existing isolated API fixture.

Collect raw Consumer/Coordinator decisions; independent review in the existing
test record decides the functional result. Never calls an external business API.
"""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from backend.tests.subject_access_support import create_api_key as create_reader_key
from modeling_team.__main__ import (
    _CQ_PLATFORM_ROLE_INSTRUCTIONS,
    _cq_observe_model_binding,
    _cq_platform_read_persistence,
)
from modeling_team.acceptance_runtime import McpReadForwarder, build_platform_batch_packet
from modeling_team.competency_questions import CQ_BATCH_REPORT_SCHEMA, content_digest
from modeling_team.contracts import repository_root
from modeling_team.model_routing import load_team_model_profile
from modeling_team.protocol_mechanics import translate_candidate_to_batches
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.staged_decisions import canonical_json_digest
from modeling_team.tests.test_r4011_api_mapping_contract import candidate

ROOT = repository_root()


@pytest.mark.skipif(
    os.environ.get("R4011_LIVE_BINDING_REVIEW") != "1",
    reason="explicit controlled live roles and isolated platform opt-in",
)
def test_live_binding_consumer_and_coordinator_raw_reports():
    case = os.getenv("R4011_BINDING_CASE", "full")
    assert case in {"full", "renamed"}
    evidence = Path(os.getenv(
        "R4011_EVIDENCE_DIR", ROOT / "workspaces/r4011-binding-functional/round-1"
    ))
    evidence.mkdir(parents=True, exist_ok=False)

    def save(path, value):
        (evidence / path).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    coordinator = (ROOT / "modeling_team/agent-packages/coordinator/instructions.md").read_text()
    contract = json.loads((ROOT / "modeling_team/references/r4-0-011-api-mapping-contract.json")
                          .read_text())
    _, active_consumer, active_skill = CodexRuntimeAdapter._child_package_assets(
        "platform", ROOT, v3_batch=True
    )
    save("prompt-snapshot.json", {
        "coordinator_instructions": coordinator,
        "consumer_instructions": _CQ_PLATFORM_ROLE_INSTRUCTIONS,
        "interface_rules": contract["rules"],
        "active_consumer_path": str(active_consumer.relative_to(ROOT)),
        "active_consumer_text": active_consumer.read_text(),
        "active_skill_path": str(active_skill.relative_to(ROOT)),
        "active_skill_text": active_skill.read_text(),
        "proxy_presence": {name: bool(os.environ.get(name))
                           for name in ("http_proxy", "https_proxy", "no_proxy")},
        "profile": "openai-sol-medium",
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    })
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id = ontology_id = reader_user = None
    graphs, key_ids = [], []
    try:
        with factory() as session:
            record, key = create_api_key(
                session, name="r4011-review-" + token, project_id=None,
                scopes=["admin"], bootstrap=True,
            )
            key_ids.append(record.id)
        with httpx.Client(
            base_url="http://127.0.0.1:8001", headers={"Authorization": "Bearer " + key},
            timeout=120,
        ) as client:
            def post(path, value, status=200):
                response = client.post("/api" + path, json=value)
                assert response.status_code == status, response.text
                return response.json()

            def context():
                response = client.get(f"/api/ontologies/{ontology_id}/modeling-context")
                assert response.status_code == 200, response.text
                return response.json()

            project_id = post("/projects", {"name": "R4011 review " + token}, 201)["id"]
            ontology = post(f"/projects/{project_id}/ontologies", {
                "name": "Controlled catalog binding review"
            }, 201)
            ontology_id = ontology["id"]
            graphs.extend(row["graph_iri"] for row in ontology["workspace"]["members"])
            build = post(f"/projects/{project_id}/build-sessions", {
                "client_session_id": token
            }, 201)
            base = context()["semantic_base_iri"]
            value = candidate()
            kept = {"p-bindingId", "p-usesBinding", "p-forOperation", "reserve-api", "binding",
                    "catalog-class", "reserve-operation", "edge-52", "edge-53"}
            value["items"] = [row for row in value["items"] if row["item_id"] in kept]
            for row in value["items"]:
                semantic = row["semantic"]
                for field in ("entity_id", "class_id", "operation_id", "target_class", "predicate"):
                    if field in semantic:
                        semantic[field] = token + "-" + semantic[field]
            original = deepcopy(value)
            old_digest = canonical_json_digest(original)
            save("candidate-r1.json", original)

            def apply(items, name):
                request = {
                    "client_batch_id": token + "-" + name, "ontology_id": ontology_id,
                    "mode": "dry_run", "idempotency_key": token + "-dry-" + name,
                    "expected_model_revision": context()["workspace"]["model_revision"],
                    "items": items,
                }
                path = f"/build-sessions/{build['id']}/modeling-batches"
                dry = post(path, request)
                save(name + "-dry-run.json", dry)
                assert dry["attempt_status"] == "validated", dry
                session_response = client.get(f"/api/build-sessions/{build['id']}")
                assert session_response.status_code == 200, session_response.text
                lease = post(
                    f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                    {"client_request_id": token + "-lease-" + name,
                     "expected_session_revision": session_response.json()["session"]["revision"]},
                )
                save(name + "-lease.json", {
                    "lease_revision": lease["lease_revision"], "state": lease["state"],
                    "expires_at": lease["expires_at"],
                })
                request.update(mode="apply_atomic", idempotency_key=token + "-apply-" + name,
                               lease_token=lease["lease_token"])
                result = post(path, request)
                save(name + "-apply.json", result)
                assert result["attempt_status"] == "applied", result
                return result

            receipts = {}
            plan = translate_candidate_to_batches(value, semantic_base_iri=base)
            assert not plan["conflicts"], plan
            for index, batch in enumerate(plan["batches"]):
                applied = apply(batch["items"], "initial-" + str(index))
                receipts.update({row["client_item_id"]: row["resource_outputs"]["resource_iri"]
                                 for row in applied["items"]
                                 if "resource_iri" in row["resource_outputs"]})
            save("resource-receipts.json", receipts)
            # Read-only project key is the only key allowed into the canonical MCP forwarder.
            with factory() as session:
                record, read_key = create_reader_key(
                    session, name="r4011-read-" + token, project_id=project_id, scopes=["read"],
                )
                key_ids.append(record.id)
                reader_user = record.user_id
            forwarder = McpReadForwarder(
                repository_root=ROOT, read_key=read_key,
                expected_tools=["get_ontology_workspace_context", "query_semantic_context"],
            )
            forwarder.start()
            try:
                def collect(role, variant, question):
                    target = evidence / (variant + "-" + role)
                    target.mkdir()
                    batch = "r4011-" + variant + "-" + role
                    freeze = content_digest(question)
                    binding = {
                        "schema_version": "r3-0-011-model-binding/v1", "batch_id": batch,
                        "freeze_digest": freeze, "bound_at": datetime.now(timezone.utc).isoformat(),
                        "ontologies": [{"project_id": project_id, "ontology_id": ontology_id,
                                        "workspace_state": {"state_digest": "host-observation"},
                                        "model_version_state": {"state_digest": "host-observation"},
                                        "authorized_read_tools": ["query_semantic_context"]}],
                    }
                    observed, graph_sets = _cq_observe_model_binding(
                        forwarder.forward, read_key, binding
                    )
                    packet = build_platform_batch_packet(
                        run_id="controlled-functional-no-semantic-start-" + token,
                        batch_id=batch, freeze_digest=freeze,
                        questions=[{"question_id": "B-01", "content_version": 1,
                                    "question": question,
                                    "scope": {"kind": "panorama", "slice_ids": []}}],
                        authorized_scope=[ontology_id], model_binding=observed,
                        authorized_read_tools=["query_semantic_context"],
                        report_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
                        session={"mode": "single-continuous-batch", "ordered": True},
                    )
                    instructions = _CQ_PLATFORM_ROLE_INSTRUCTIONS
                    if role == "coordinator":
                        instructions += (
                            "\nControlled functional Coordinator reference-review task. "
                            "Use the following current Coordinator instructions for your review "
                            "judgment. The read-only child/report transport replaces Team messaging "
                            "in this fixture; do not write a map, terminal, or platform resource. "
                            "Provide the actual review conclusion in answer, including the candidate "
                            "revision/digest, affected scope and next responsible action.\n" + coordinator
                        )
                    instructions += "\nCurrent interface mapping conventions:\n" + json.dumps(
                        contract["rules"], ensure_ascii=False
                    )
                    save(str(target.relative_to(evidence) / "packet.json"), packet.to_dict())
                    save(str(target.relative_to(evidence) / "role-instructions.json"), instructions)
                    adapter = CodexRuntimeAdapter(repository_root=ROOT)
                    adapter._run_root = target
                    adapter.bind_acceptance_model_profile(
                        load_team_model_profile(ROOT, "openai-sol-medium")
                    )
                    reports, teardown, observables = [], {}, {}
                    try:
                        adapter.run_v3_acceptance_child(
                            packet, role_instructions=instructions, reports=reports,
                            read_key=read_key, platform_forwarder=forwarder.forward,
                            ontology_ids=graph_sets, timeout_seconds=300,
                            response_persistence=_cq_platform_read_persistence(target),
                            examiner_observables=observables, teardown=teardown,
                        )
                        assert len(reports) == 1
                    except Exception as exc:
                        save(str(target.relative_to(evidence) / "error.json"), {
                            "type": type(exc).__name__, "message": str(exc),
                            "typed": exc.as_dict() if callable(getattr(exc, "as_dict", None)) else None,
                        })
                        raise
                    finally:
                        observables["receipts"] = [
                            asdict(receipt) for receipt in observables.get("receipts", [])
                        ]
                        for name, payload in (("reports", reports), ("teardown", teardown),
                                              ("observables", observables),
                                              ("runtime-failures", adapter.consume_runtime_failures())):
                            save(str(target.relative_to(evidence) / (name + ".json")), payload)
                    return reports[0]

                consumer_question = (
                    f"在获准 Ontology {ontology_id} 内，接口 {receipts['reserve-api']} 当前指定"
                    "哪个具体 Tool Binding？请读取该接口的绑定节点普通属性／关系及关联 Operation "
                    "受控投影，说明对应系统、接口标识和版本，当前是否足以确认指定的接口定位。"
                    "只报告当前模型支持的含义与缺口。"
                )
                if case == "full":
                    baseline = collect("consumer", "baseline", consumer_question)
                    assert baseline["status"] == "completed", (
                        "Baseline location question is unresolved; stop negative calls and "
                        "independently review the raw report before repairing or retrying."
                    )
                operation = next(row["semantic"] for row in value["items"]
                                 if row["item_id"] == "reserve-operation")
                revisions = [(2, "deleted"), (3, "renamed")] if case == "full" else [(3, "renamed")]
                for revision, variant in revisions:
                    changed = deepcopy(original)
                    changed["candidate_revision"] = revision
                    bindings = deepcopy(operation["tool_bindings"])
                    if variant == "deleted":
                        bindings.pop(1)
                    else:
                        bindings[1]["binding_id"] = "reserve-v2-renamed"
                    next(row["semantic"] for row in changed["items"]
                         if row["item_id"] == "reserve-operation")["tool_bindings"] = bindings
                    save("candidate-r" + str(revision) + ".json", changed)
                    apply([{
                        "client_item_id": "drift-" + variant, "command_kind": "update_operation",
                        "payload": {"operation_iri": receipts["reserve-operation"],
                                    "tool_bindings": bindings},
                    }], variant)
                    collect("consumer", variant, consumer_question)
                    collect("coordinator", variant,
                            f"对获准 Ontology {ontology_id} 的新完整候选作一次实际引用重审。"
                            f"旧批准仅绑定 revision=1, candidate_digest={old_digest}。"
                            f"当前候选 revision={revision}, candidate_digest="
                            f"{canonical_json_digest(changed)}。完整候选 JSON="
                            + json.dumps(changed, ensure_ascii=False)
                            + "。实际平台 IRI 回执=" + json.dumps(receipts)
                            + "。请通过获准读取核对当前绑定及直接引用，记录重审结论、"
                            "实际已覆盖范围、未知或受影响引用与下一步；不得代替平台执行修改。")
            finally:
                forwarder.stop()
    finally:
        with factory() as session:
            if ontology_id:
                sets = list(session.scalars(select(m.SemanticGraphSetModel.id).where(
                    m.SemanticGraphSetModel.scope_type == "ontology",
                    m.SemanticGraphSetModel.scope_id == ontology_id,
                )))
                session.execute(delete(m.SemanticGraphSetModel).where(
                    m.SemanticGraphSetModel.id.in_(sets)
                ))
            if project_id:
                session.execute(delete(m.ProjectModel).where(m.ProjectModel.id == project_id))
            session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id.in_(key_ids)))
            if reader_user:
                session.execute(delete(m.UserModel).where(m.UserModel.id == reader_user))
            for model in (m.SemanticGraphRegistryModel, m.SemanticGraphRevisionModel):
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            session.commit()
        for iri in graphs:
            store.drop_named_graph(iri)
            assert not store.graph_exists(iri)
        with factory() as session:
            assert not project_id or session.get(m.ProjectModel, project_id) is None
            assert not list(session.scalars(select(m.ApiKeyModel.id).where(
                m.ApiKeyModel.id.in_(key_ids)
            )))
            assert not reader_user or session.get(m.UserModel, reader_user) is None
        save("cleanup.json", {"project_removed": True, "keys_removed": True,
                              "graphs_dropped": graphs, "semantic_starts": 0,
                              "external_business_api_calls": 0})
