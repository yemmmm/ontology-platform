"""Project continuity, orthogonal understanding, and invalidation without changing business truth."""

import json
from contextlib import contextmanager

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.memory import SharedMemory
from ontoweave_modeling.semantic_workspace import SemanticWorkspace
from ontoweave_modeling.workspace import WorkspaceRepository


@pytest.mark.parametrize(
    "reference",
    [
        {"material_id": "source", "sha256": "a" * 64},
        {"record_id": "p"},
        {"record_id": "p", "reference": {"record_id": "p", "revision": 1}},
    ],
)
def test_malformed_dependency_is_rejected_before_record_commit(workspace, binding, reference):
    space = SemanticWorkspace(workspace, binding.data)
    with pytest.raises(FrameworkError, match="invalid_dependency_reference") as caught:
        space.write("bad", "coverage", "Coverage", "Incomplete reference", depends_on=[reference])
    assert caught.value.detail["path"] == "/depends_on/0"
    assert workspace.get("semantic:bad") is None


def test_retained_bad_dependency_is_readable_for_agent_repair(workspace, binding):
    reference = {"material_id": "source", "sha256": "a" * 64}
    workspace.put_reference(
        "semantic:retained",
        "semantic_record",
        {
            "kind": "coverage",
            "view": "production",
            "body": "Retained bad original",
            "states": {"applicability": "current"},
            "depends_on": [reference],
        },
        0,
    )
    actual = SemanticWorkspace(workspace, binding.data).read("retained")
    assert actual["body"] == "Retained bad original"
    assert actual["freshness"]["state"] == "needs_review"
    assert actual["freshness"]["invalid_dependencies"] == [reference]


def test_linked_proposition_decision_and_summary_refresh_by_exact_dependency(workspace, binding):
    space = SemanticWorkspace(workspace, binding.data)
    p = space.write(
        "p",
        "proposition",
        "Condition",
        "Only after approval; exception and unknown retained.",
        [{"material_id": "source"}],
    )["record"]
    d = space.write(
        "d",
        "decision",
        "Interpretation",
        "Approval is permission, not obligation.",
        depends_on=[p["reference"]],
    )["record"]
    s = space.write(
        "s",
        "summary",
        "Overview",
        "Navigate to the full condition and decision.",
        depends_on=[d["reference"]],
    )["record"]
    assert s["freshness"]["state"] == "current"
    changed = space.write(
        "p",
        "proposition",
        "Condition",
        "Approval condition revised; exception retained.",
        [{"material_id": "source"}],
        expected_revision=p["revision"],
    )["record"]
    assert changed["revision"] == 2
    assert space.read("d")["freshness"]["state"] == "needs_review"
    assert space.read("s")["freshness"]["state"] == "needs_review"
    assert space.read("p", 1)["freshness"]["state"] == "historical"
    conflict = space.write("p", "proposition", "Condition", "stale update", expected_revision=1)
    assert conflict["code"] == "version_conflict" and conflict["actual"]["revision"] == 2


def test_project_scope_survives_new_task_without_loading_other_task_records(workspace, binding):
    first = {**binding.data, "project_ref": "shared-project"}
    space = SemanticWorkspace(workspace, first)
    space.write(
        "project-summary",
        "summary",
        "Shared rules",
        "Condition, rare exception and unknown.",
        [{"material_id": "source"}],
        scope="project",
    )
    space.write("local", "open_item", "Local unfinished work", "Only this task")
    notes = SharedMemory(workspace, "modeling", "shared-project", first)
    notes.scoped("project").write(
        "scope", "decision", "Scope", "Same project, never a new confirmation"
    )
    other = WorkspaceRepository(workspace.connection, workspace.schema, "second-task")
    second = {**first, "task_ref": "second-task", "run_id": "second-run"}
    inherited = SemanticWorkspace(other, second)
    assert (
        inherited.read("project-summary", scope="project")["body"]
        == "Condition, rare exception and unknown."
    )
    assert inherited.read("local")["state"] == "not_found"
    assert inherited.context()["project_navigation"]["total"] == 1
    assert (
        SharedMemory(other, "reader", "shared-project", second)
        .scoped("project")
        .read("scope")["body"]
        .startswith("Same project")
    )
    assert (
        SemanticWorkspace(other, {**second, "project_ref": "unrelated-project"}).read(
            "project-summary", scope="project"
        )["state"]
        == "not_found"
    )


def test_newly_created_platform_project_becomes_available_without_rewriting_task_binding(
    workspace, binding
):
    from ontoweave_modeling.flow import WorkUnitFlow

    original = dict(binding.data)

    class Platform:
        def call(self, action, payload):
            assert action == "prepare_scope"
            return {"project_id": "created-project", "model_revisions": {"ontology": 0}}

    flow = WorkUnitFlow(binding, workspace, Platform(), None)
    flow._prepare(flow.initialize())
    space = SemanticWorkspace(workspace, binding.data)
    assert space.context()["project_ref"] == "created-project"
    space.write("p", "proposition", "Shared", "Shared condition", scope="project")
    notes = SharedMemory(workspace, "modeling", task=binding.data).scoped("project")
    notes.write("rule", "decision", "Shared", "Reusable meaning")
    assert notes.read("rule")["body"] == "Reusable meaning"
    assert binding.data == original


def test_source_withdrawal_marks_review_not_false_and_preserves_old_revision(workspace, binding):
    space = SemanticWorkspace(workspace, binding.data)
    before = space.write(
        "rule", "proposition", "Rule", "A condition and exception", [{"material_id": "source"}]
    )["record"]
    count = space.invalidate_sources(binding.data["source_manifest"], ["source"], "withdraw-source")
    assert len(count) == 1
    after = space.read("rule")
    assert after["body"] == before["body"] and after["states"]["applicability"] == "needs_review"
    assert after["freshness"]["state"] == "needs_review"
    assert not space.invalidate_sources(
        binding.data["source_manifest"], ["source"], "withdraw-source"
    )
    assert space.read("rule")["revision"] == after["revision"]


def test_new_source_marks_local_judgments_as_review_candidates(workspace, binding):
    space = SemanticWorkspace(workspace, binding.data, "a")
    space.write("scope", "open_item", "Old unknown", "A not yet specified field")
    memory = SharedMemory(workspace, "a", task=binding.data)
    memory.write("scope", "open_item", "Old unknown", "Still needs business review")
    space.invalidate_sources(
        binding.data["source_manifest"], ["new-source"], "new-source-arrived", ["a"]
    )
    assert space.read("scope")["freshness"]["state"] == "needs_review"
    assert memory.read("scope")["applicability"] == "needs_review"


def test_views_and_private_execution_content_are_not_workspace_records(workspace, binding):
    producer = SemanticWorkspace(workspace, binding.data)
    producer.write("private-production", "decision", "Candidate", "Not an applied model")
    consumer = SemanticWorkspace(workspace, binding.data, view="consumer")
    assert consumer.read("private-production")["state"] == "not_found"
    workspace.put_reference(
        "secret-evaluation", "execution", {"final_response": "hidden reasons"}, 0
    )
    assert producer.read("secret-evaluation")["state"] == "not_found"
    with pytest.raises(FrameworkError, match="host_observation_required"):
        producer.write("fake", "decision", "State", "Not proof", states={"acceptance": "PASS"})
    with pytest.raises(FrameworkError, match="source_reference_mismatch"):
        producer.write(
            "wrong",
            "proposition",
            "Wrong source",
            "Claim",
            [{"material_id": "source", "sha256": "0" * 64}],
        )


def test_actual_model_change_invalidates_navigation_without_changing_source_truth(
    workspace, binding
):
    task = {**binding.data, "project_ref": "shared-project"}
    space = SemanticWorkspace(workspace, task)
    space.observe_models({"ontology": 3})
    space.write("p", "proposition", "Original condition", "Only after approval")
    summary = space.write("s", "summary", "Overview", "Approval condition is expressed")["record"]
    assert summary["model_basis"] == {"ontology": 3}
    # A different task observes a newer actual model; an older late observation cannot rewind it.
    other = WorkspaceRepository(workspace.connection, workspace.schema, "second-task")
    observer = SemanticWorkspace(other, {**task, "task_ref": "second-task"})
    observer.observe_models({"ontology": 4})
    space.observe_models({"ontology": 3})
    assert space.read("s")["freshness"]["state"] == "needs_review"
    assert space.read("p")["freshness"]["state"] == "current"
    space.observe_models({"ontology": 4})
    refreshed = space.write(
        "s", "summary", "Overview", "Rechecked actual model", expected_revision=1
    )
    assert refreshed["record"]["freshness"]["state"] == "current"
    assert space.read("s", revision=1)["freshness"]["state"] == "historical"


def test_explicit_new_source_impact_can_reopen_prior_task_project_record(workspace, binding):
    first = {**binding.data, "project_ref": "shared-project", "task_ref": "first-task"}
    SemanticWorkspace(workspace, first).write(
        "unknown-format", "open_item", "Format", "Format not specified", scope="project"
    )
    second = SemanticWorkspace(workspace, {**first, "task_ref": "second-task"})
    second.invalidate_sources(
        first["source_manifest"],
        ["new-format"],
        "format-added",
        [],
        [{"scope": "project", "record_id": "unknown-format"}],
    )
    assert second.read("unknown-format", scope="project")["freshness"]["state"] == "needs_review"


@pytest.mark.parametrize("read_only", [False, True])
def test_real_isolated_workspace_tools_with_bound_project(
    workspace, binding, tmp_path, monkeypatch, read_only
):
    from openai_codex.generated.v2_all import McpServerToolCallResponse

    from ontoweave_modeling.codex_agent import CodexAgent

    binding.data.update(
        task_ref=workspace.task_ref, project_ref="isolated-project", semantic_workspace=True
    )
    (binding.root / "private-runtime.json").write_text(
        json.dumps({"connection": workspace.connection, "workspace_schema": workspace.schema})
    )
    config = tmp_path / "platform.json"
    config.write_text("{}")

    class Bridge:
        def call(self, operation, payload):
            return {"config_ref": str(config)}

        @contextmanager
        def provider(self, *args):
            yield "http://127.0.0.1:9"

    class Probe(CodexAgent):
        def run_turn(self, prompt):
            if read_only:
                events = [
                    json.loads(line)
                    for line in (self.root / "events.jsonl").read_text().splitlines()
                ]
                mcp = next(e["params"] for e in events if e["method"] == "mcpServerStatus/list")
                assert set(mcp["data"][0]["tools"]) == {
                    "read_material",
                    "query_semantic_context",
                    "read_model_resource",
                }
                assert mcp["data"][0]["tools"]["read_model_resource"]["annotations"]["readOnlyHint"]
                assert self.team_config is None
                return {"status": "completed"}
            for tool, args in [
                ("get_modeling_context", {}),
                (
                    "write_semantic_record",
                    {
                        "record_id": "p",
                        "kind": "proposition",
                        "title": "Condition",
                        "body": "With rare exception",
                        "source_refs": [{"material_id": "source"}],
                        "scope": "project",
                    },
                ),
                ("search_semantic_records", {"scope": "project", "query": "exception"}),
                ("read_semantic_record", {"record_id": "p", "scope": "project"}),
            ]:
                result = self.client.request(
                    "mcpServer/tool/call",
                    {
                        "threadId": self.thread_id,
                        "server": "workspace",
                        "tool": tool,
                        "arguments": args,
                    },
                    response_model=McpServerToolCallResponse,
                )
                assert not result.is_error, result.content
            return {"status": "completed"}

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Probe)
    root = tmp_path / "execution"
    root.mkdir()
    result = CodexInvocation(binding, Bridge(), read_only=read_only)(
        root, "overview" if read_only else "modeling", "No inference", []
    )
    assert result["status"] == "completed"
    if not read_only:
        assert (
            SemanticWorkspace(workspace, binding.data).read("p", scope="project")["body"]
            == "With rare exception"
        )
