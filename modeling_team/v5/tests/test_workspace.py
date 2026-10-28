"""Real PostgreSQL contracts in a disposable, explicitly owned schema."""

import threading
from concurrent.futures import ThreadPoolExecutor

from ontoweave_modeling.workspace import WorkspaceRepository


def test_business_versions_survive_new_repository_and_keep_authorities_separate(workspace):
    first = workspace.put("definition-a", "definition", {"text": "initial"}, 0)
    assert first["object"]["revision"] == 1
    other = WorkspaceRepository(workspace.connection, workspace.schema, workspace.task_ref)
    second = other.put("definition-a", "definition", {"text": "revised"}, 1)
    assert second["object"]["revision"] == 2
    assert other.get("definition-a", 1)["content"] == {"text": "initial"}
    assert other.get("definition-a")["authority"] == "candidate_workspace"
    alien_task = WorkspaceRepository(workspace.connection, workspace.schema, "other-task")
    assert alien_task.get("definition-a") is None


def test_stale_update_reports_actual_diff_and_does_not_overwrite(workspace):
    workspace.put("shared", "definition", {"text": "v1", "scope": "a"}, 0)
    workspace.put("shared", "definition", {"text": "v2", "scope": "a"}, 1)
    conflict = workspace.put("shared", "definition", {"text": "stale"}, 1)
    assert conflict["code"] == "version_conflict" and conflict["recoverable"]
    assert conflict["actual"]["revision"] == 2
    assert conflict["changed_fields"] == ["text"]
    assert workspace.get("shared")["content"]["text"] == "v2"


def test_conflict_distinguishes_missing_fields_from_explicit_null(workspace):
    workspace.put("shared", "definition", {}, 0)
    workspace.put("shared", "definition", {"scope": None}, 1)
    conflict = workspace.put("shared", "definition", {"new": True}, 1)
    assert conflict["changed_fields"] == ["scope"]


def test_replay_returns_original_operation_without_rolling_back_new_business_content(workspace):
    first = workspace.put("shared", "definition", {"text": "v1"}, 0, operation_id="original-op")
    workspace.put("shared", "definition", {"text": "v2"}, 1)
    replay = workspace.put("shared", "definition", {"text": "v1"}, 0, operation_id="original-op")
    assert replay["replayed"] and replay["object"] == first["object"]
    assert replay["current_revision"] == 2
    assert workspace.get("shared")["revision"] == 2
    conflict = workspace.put(
        "shared", "definition", {"text": "changed-intent"}, 0, operation_id="original-op"
    )
    assert conflict["code"] == "operation_conflict"


def test_postgres_checkpoints_are_a_different_namespace_of_authority(workspace):
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict):
        object_id: str
        revision: int

    workspace.put("shared", "definition", {"text": "current business"}, 0)
    builder = StateGraph(State)
    builder.add_node("reference", lambda state: {"revision": 1})
    builder.add_edge(START, "reference")
    builder.add_edge("reference", END)
    config = {"configurable": {"thread_id": "unit-a"}}
    with workspace.checkpointer() as saver:
        graph = builder.compile(checkpointer=saver)
        graph.invoke({"object_id": "shared", "revision": 0}, config)
    workspace.put("shared", "definition", {"text": "newer business"}, 1)
    with workspace.checkpointer() as saver:
        graph = builder.compile(checkpointer=saver)
        assert graph.get_state(config).values == {"object_id": "shared", "revision": 1}
    assert workspace.get("shared")["content"]["text"] == "newer business"


def test_concurrent_edits_return_one_conflict_with_current_content(workspace):
    workspace.put("shared", "definition", {"text": "baseline"}, 0)
    barrier = threading.Barrier(2)

    def edit(text):
        barrier.wait(timeout=10)
        return workspace.put("shared", "definition", {"text": text}, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["first edit", "second edit"]))
    assert sum(row.get("status") == "recorded" for row in results) == 1
    conflict = next(row for row in results if row.get("code") == "version_conflict")
    assert conflict["actual"] == workspace.get("shared")
    assert conflict["actual"]["revision"] == 2


def test_concurrent_same_operation_returns_one_effect_and_original_receipt(workspace):
    barrier = threading.Barrier(2)

    def retry(_):
        barrier.wait(timeout=10)
        return workspace.put(
            "shared", "definition", {"text": "same intent"}, 0, operation_id="same-operation"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(retry, range(2)))
    assert all(row.get("status") == "recorded" for row in results)
    assert sum(not row["replayed"] for row in results) == 1
    assert workspace.get("shared")["revision"] == 1
