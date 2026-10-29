import asyncio
import json
from contextlib import contextmanager

from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.material_tools import material_server
from ontoweave_modeling.memory import SharedMemory
from ontoweave_modeling.workspace import WorkspaceRepository


def test_unknown_id_search_and_another_agent_reads_full_note(workspace):
    a = SharedMemory(workspace, "modeling")
    b = SharedMemory(workspace, "reviewer")
    body = "A condition with an exception and an explicit unknown. " * 20
    a.write("device-scope", "decision", "Device scope", body, [{"material_id": "source"}])
    found = b.search("exception")
    assert found["total"] == 1 and len(found["entries"][0]["preview"]) == 400
    entry = b.read(found["entries"][0]["entry_id"])
    assert entry["body"] == body and entry["author"] == "modeling"
    assert entry["source_refs"] == [{"material_id": "source"}]


def test_revision_conflict_returns_current_and_old_revision_survives(workspace):
    a = SharedMemory(workspace, "a")
    b = SharedMemory(workspace, "b")
    a.write("scope", "decision", "scope", "first")
    b.write("scope", "decision", "scope", "first plus exception", expected_revision=1)
    conflict = a.write("scope", "decision", "scope", "stale", expected_revision=1)
    assert conflict["code"] == "version_conflict" and conflict["actual"]["revision"] == 2
    assert conflict["actual"]["body"] == "first plus exception"
    assert a.read("scope", 1)["body"] == "first"
    assert b.write("scope", "decision", "scope", "first plus exception")["replayed"] is True


def test_memory_is_task_scoped_and_search_pages(workspace):
    a = SharedMemory(workspace, "a")
    for n in range(3):
        a.write(str(n), "open_item", "scope " + str(n), "unknown")
    assert a.search("scope", kind="open_item", limit=2)["next_offset"] == 2
    assert len(a.search("scope", limit=2, offset=2)["entries"]) == 1
    other = WorkspaceRepository(workspace.connection, workspace.schema, "other-task")
    assert SharedMemory(other, "b").search()["total"] == 0


def test_memory_tools_loaded_in_production_mcp_config(workspace, binding, tmp_path):
    config = tmp_path / "team.json"
    task = {**binding.data, "task_ref": workspace.task_ref, "shared_memory": True}
    config.write_text(
        json.dumps(
            {
                "task": task,
                "connection": workspace.connection,
                "schema": workspace.schema,
                "actor": "modeling",
            }
        )
    )
    server = material_server(binding.root / "materials", team_config=config)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"write_memory", "read_memory", "search_memory"} <= names


def test_real_isolated_memory_tools_use_production_invocation(
    workspace, binding, tmp_path, monkeypatch
):
    from openai_codex.generated.v2_all import McpServerToolCallResponse

    from ontoweave_modeling.codex_agent import CodexAgent

    binding.data.update(task_ref=workspace.task_ref, shared_memory=True)
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
            assert "Use team tools" not in self.instructions
            for tool, args in [
                (
                    "write_memory",
                    {
                        "entry_id": "scope",
                        "kind": "decision",
                        "title": "Scope",
                        "body": "With exception",
                    },
                ),
                ("search_memory", {"query": "exception"}),
                ("read_memory", {"entry_id": "scope"}),
            ]:
                value = self.client.request(
                    "mcpServer/tool/call",
                    {
                        "threadId": self.thread_id,
                        "server": "workspace",
                        "tool": tool,
                        "arguments": args,
                    },
                    response_model=McpServerToolCallResponse,
                )
                assert not value.is_error, value.content
            return {"status": "completed"}

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Probe)
    root = tmp_path / "execution"
    root.mkdir()
    CodexInvocation(binding, Bridge())(root, "modeling", "No inference", [])
    assert SharedMemory(workspace, "reader").read("scope")["body"] == "With exception"
