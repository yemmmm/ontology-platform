"""Production self-check may finish reads across exact-basis technical corrections."""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy

import pytest
from test_framework_flow import Platform, tool_event

from ontoweave_modeling.contracts import TaskBinding
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow


@pytest.fixture
def read_reuse_binding(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["evaluation"]["model_read_scope"] = "whole_model"
    task_file.write_text(json.dumps(task))
    materials = tmp_path / "sources"
    cq = b"Read the approved public question completely."
    (materials / "public-cq.md").write_bytes(cq)
    manifest_path = materials / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["public-cq"] = {
        "path": "public-cq.md",
        "source_ref": "approved-public-cq/v1",
        "sha256": hashlib.sha256(cq).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest))
    return TaskBinding.prepare(task_file, tmp_path / "read-reuse-run")


class ReadCorrections:
    def __init__(self, binding, platform, *, defect=None):
        self.binding, self.platform, self.defect = binding, platform, defect
        self.calls, self.originals = [], []

    def __call__(self, root, purpose, text, inputs):
        assert purpose == "self_check"
        prompt = json.loads(text)
        self.calls.append(prompt)
        index = len(self.calls)
        material_id = "source" if index == 1 else "public-cq"
        entry = self.binding.data["source_manifest"][material_id]
        content = (self.binding.materials / entry["path"]).read_text()
        if self.defect == "incomplete_source" and index == 1:
            content = content[:4]
        total = len((self.binding.materials / entry["path"]).read_text())
        events = [
            tool_event(
                "read_material",
                {
                    "text": content,
                    "sha256": entry["sha256"],
                    "offset": 0,
                    "total_characters": total,
                },
                {"material_id": material_id},
            )
        ]
        revision = len(self.platform.effects)
        if index == 1:
            for family, items in (
                ("resource-list", [{"iri": "urn:actual:one"}]),
                ("entity-detail", [{"iri": "urn:actual:one", "detail_fields": {"name": "One"}}]),
                ("resource-relations", []),
            ):
                if self.defect == "missing_body" and family == "entity-detail":
                    continue
                events.append(
                    tool_event(
                        "read_model_resource",
                        {"model_revision": revision, "items": items, "paging": {"complete": True}},
                        {"ontology_id": "ontology", "family": family},
                    )
                )
        if index == 1 or self.defect != "no_current_governed_read":
            events.append(
                tool_event(
                    "query_semantic_context",
                    {
                        "scope": {
                            "ontologies": [{"ontology_id": "ontology", "model_revision": revision}]
                        }
                    },
                )
            )
        folder = root / "agent"
        folder.mkdir(exist_ok=True)
        path = folder / "events.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        response = {
            "status": "ready",
            "issues": [],
            "consumed_ids": [item["id"] for item in inputs],
        }
        native = {
            "status": "failed" if self.defect == "failed_execution" and index == 1 else "completed",
            "thread_id": "other-context"
            if self.defect == "changed_thread" and index > 1
            else "same-context",
            "turn_id": root.name,
            "final_response": json.dumps(response),
        }
        self.originals.append((path, path.read_text(), deepcopy(native)))
        return native


def _flow(binding, workspace, defect=None):
    platform = Platform()
    actor = ReadCorrections(binding, platform, defect=defect)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    state = flow.initialize()
    candidate = workspace.put_reference("current-candidate", "candidate", {"review_units": []}, 0)
    flow._save({**state, "activity": "self_check", "round": 7, "candidate_ref": candidate})
    return flow, actor, platform


def _check(flow):
    return flow._self_check(flow.repository.get(flow.work_id)["content"])


def test_root_correction_finishes_source_cq_and_actual_model_reads_across_two_turns(
    read_reuse_binding, workspace
):
    flow, actor, platform = _flow(read_reuse_binding, workspace)
    first = _check(flow)
    assert first["issue"]["code"] == "self_check_needs_correction"
    assert [gap["material_id"] for gap in first["issue"]["coverage"]["materials"]] == ["public-cq"]
    assert not first["issue"]["coverage"]["models"]
    second = _check(flow)
    assert second["activity"] == "handoff", second
    assert second["status"] == "ready"
    assert len(actor.calls) == 2
    assert actor.calls[1]["reusable_read_execution_refs"]
    for path, events, native in actor.originals:
        assert path.read_text() == events
        execution = workspace.get(flow.binding.identity + ":execution:" + native["turn_id"])
        assert execution["content"]["result"] == native
    assert not platform.effects


@pytest.mark.parametrize(
    "changed",
    ["target", "source", "candidate", "round", "generation", "author", "phase"],
)
def test_self_check_read_reuse_rejects_changed_basis_or_execution_owner(
    read_reuse_binding, workspace, changed
):
    flow, _, platform = _flow(read_reuse_binding, workspace)
    first = _check(flow)
    if changed == "target":
        platform.effects["external-change"] = {}
    elif changed == "source":
        flow.binding.data["source_manifest"]["source"]["sha256"] = "b" * 64
    elif changed == "candidate":
        first["candidate_ref"] = workspace.put_reference("new-candidate", "candidate", {}, 0)
    elif changed == "round":
        first["round"] += 1
    elif changed == "generation":
        flow.binding.data["work_generation"] = 1
    else:
        row = workspace.list_kind("execution")[0]
        execution = deepcopy(row["content"])
        execution["intent"]["actor_id" if changed == "author" else "purpose"] = (
            "other-author" if changed == "author" else "modeling"
        )
        replacement = workspace.put_reference(
            row["object_id"], "execution", execution, row["revision"]
        )
        first["self_check_read_execution_refs"] = [replacement]
    flow._save(first)
    second = _check(flow)
    assert second["activity"] == "self_check", second
    assert second["issue"]["code"] == "self_check_needs_correction"
    assert second["issue"]["coverage"]["materials"][0]["material_id"] == "source"


@pytest.mark.parametrize(
    "defect",
    [
        "changed_thread",
        "failed_execution",
        "incomplete_source",
        "missing_body",
        "no_current_governed_read",
    ],
)
def test_self_check_read_reuse_keeps_actual_complete_reads_and_current_governed_gate(
    read_reuse_binding, workspace, defect
):
    flow, _, _ = _flow(read_reuse_binding, workspace, defect)
    first = _check(flow)
    assert first["activity"] == "self_check"
    second = _check(flow)
    assert second["activity"] == "self_check", second
    assert second["issue"]["code"] == "self_check_needs_correction"
    if defect == "no_current_governed_read":
        assert second["issue"]["detail"] == "actual_governed_read_missing"
    elif defect == "missing_body":
        assert second["issue"]["coverage"]["models"][0]["unread_resources"] == ["urn:actual:one"]
    else:
        assert second["issue"]["coverage"]["materials"][0]["material_id"] == "source"


@pytest.fixture
def native_correction(read_reuse_binding, workspace, monkeypatch, tmp_path):
    """Run real CodexInvocation with its transport replaced before any native request."""
    starts = []

    class Bridge(Platform):
        def call(self, action, payload):
            if action == "read_config":
                return {"config_ref": str(tmp_path / "read-config.json")}
            return super().call(action, payload)

        @contextmanager
        def provider(self, execution_id, role, tools):
            yield "http://127.0.0.1:9"

    bridge = Bridge()
    actor = ReadCorrections(read_reuse_binding, bridge)

    class Agent:
        def __init__(self, root, binding, **options):
            self.root = root
            self.resume_from = options.get("resume_from")
            self.observe = options["on_event"]

        def start(self, *, resume=False):
            self.root.mkdir(exist_ok=True)
            self.thread_id = (
                json.loads((self.resume_from / "thread-binding.json").read_text())["thread_id"]
                if resume
                else "fresh-" + self.root.parent.name
            )
            starts.append({"root": self.root, "resume": resume, "resume_from": self.resume_from})

        def run_turn(self, prompt):
            native = actor(self.root.parent, "self_check", prompt.split("\nQueued inputs:")[0], [])
            native["thread_id"] = self.thread_id
            (self.root / "thread-binding.json").write_text(
                json.dumps({"thread_id": self.thread_id})
            )
            self.observe(
                "thread/tokenUsage/updated",
                {
                    "threadId": self.thread_id,
                    "tokenUsage": {"total": {"inputTokens": 100 * len(starts), "outputTokens": 10}},
                },
            )
            if len(starts) == 3:
                with (self.root / "events.jsonl").open("a") as output:
                    output.write(
                        json.dumps(
                            tool_event(
                                "read_model_resource",
                                {
                                    "model_revision": 0,
                                    "items": [
                                        {"iri": "urn:actual:one", "detail_fields": {"name": "One"}}
                                    ],
                                },
                                {"ontology_id": "ontology", "family": "entity-detail"},
                            )
                        )
                        + "\n"
                    )
            return native

        def close(self):
            pass

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Agent)
    flow, _, _ = _flow(read_reuse_binding, workspace)
    flow.bridge = bridge
    flow.invoke = CodexInvocation(read_reuse_binding, bridge, read_only=True)
    return flow, actor, starts


def test_real_invocation_resumes_exact_self_check_and_keeps_cumulative_usage_baseline(
    native_correction,
):
    flow, _, starts = native_correction
    assert _check(flow)["issue"]["code"] == "self_check_needs_correction"
    second = _check(flow)
    assert second["activity"] == "handoff", second
    assert starts[0]["resume"] is False
    assert starts[1]["resume"] is True
    assert starts[1]["resume_from"] == starts[0]["root"]
    baseline = json.loads((starts[1]["root"].parent / "native-usage-baseline.json").read_text())
    assert baseline["thread_id"] == "fresh-self-check-00007-000"
    assert baseline["total"] == {"inputTokens": 100, "outputTokens": 10}
    assert baseline["source_execution"] == "self-check-00007-000"
    assert flow.invoke.resume_from is None


def test_real_invocation_selects_latest_completed_correction_thread(native_correction):
    flow, actor, starts = native_correction
    actor.defect = "missing_body"
    assert _check(flow)["issue"]["code"] == "self_check_needs_correction"
    assert _check(flow)["issue"]["code"] == "self_check_needs_correction"
    third = _check(flow)
    assert third["activity"] == "handoff", third
    assert starts[2]["resume_from"] == starts[1]["root"]
    baseline = json.loads((starts[2]["root"].parent / "native-usage-baseline.json").read_text())
    assert baseline["total"]["inputTokens"] == 200
    assert baseline["source_execution"] == "self-check-00007-001"


@pytest.mark.parametrize(
    "defect",
    [
        "author",
        "phase",
        "generation",
        "round",
        "basis",
        "failed",
        "missing_binding",
        "binding_thread",
    ],
)
def test_real_invocation_rejects_invalid_proof_before_resuming(
    native_correction, workspace, defect
):
    flow, _, starts = native_correction
    first = _check(flow)
    row = workspace.list_kind("execution")[0]
    if defect == "missing_binding":
        (starts[0]["root"] / "thread-binding.json").unlink()
    elif defect == "binding_thread":
        (starts[0]["root"] / "thread-binding.json").write_text('{"thread_id":"other-thread"}')
    else:
        execution = deepcopy(row["content"])
        if defect in {"author", "phase", "generation"}:
            key = {"author": "actor_id", "phase": "purpose", "generation": "generation"}[defect]
            execution["intent"][key] = 99 if defect == "generation" else "other"
        elif defect == "round":
            execution["intent"]["execution_id"] = "self-check-00006-000"
        elif defect == "basis":
            prompt = json.loads(execution["prompt"])
            prompt["self_check_read_basis"]["candidate_ref"] = None
            execution["prompt"] = json.dumps(prompt)
        else:
            execution["result"]["status"] = "failed"
        first["self_check_read_execution_refs"] = [
            workspace.put_reference(row["object_id"], "execution", execution, row["revision"])
        ]
        flow._save(first)
    second = _check(flow)
    assert starts[1]["resume"] is False
    assert starts[1]["resume_from"] is None
    assert second["activity"] == "self_check", second
    assert second["issue"]["coverage"]["materials"][0]["material_id"] == "source"
