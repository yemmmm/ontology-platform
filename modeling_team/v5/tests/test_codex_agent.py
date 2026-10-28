"""Real SDK setup checks; no model turn or upstream request is started."""

import hashlib
import json
import socket
import subprocess
import sys
from pathlib import Path

from openai_codex.generated.v2_all import McpServerToolCallResponse

from ontoweave_modeling.codex_agent import CodexAgent, outbound_tool_names
from ontoweave_modeling.preflight import ModelBinding


def test_isolated_mcp_reads_real_workspace_without_host_dns_files(tmp_path, workspace):
    workspace.put("public", "definition", {"text": "Approved record"}, 0)
    workspace.put("private", "definition", {"text": "Private record"}, 0)
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "manifest.json").write_text("{}")
    connection = dict(workspace.connection)
    connection["hostaddr"] = socket.gethostbyname(connection["host"])
    config = tmp_path / "workspace.json"
    config.write_text(
        json.dumps(
            {
                "connection": connection,
                "schema": workspace.schema,
                "task_ref": workspace.task_ref,
                "read_ids": ["public"],
                "write_ids": [],
            }
        )
    )
    agent = CodexAgent(
        tmp_path / "agent",
        ModelBinding("glm-direct", "glm-5.3-flash", "low"),
        provider_base_url="http://127.0.0.1:9",
        materials=materials,
        instructions="Non-inference workspace read test.",
        on_event=lambda *_: None,
        workspace_config=config,
        allowed_tools=("read_workspace_object",),
    )
    try:
        agent.start()
        params = {
            "threadId": agent.thread_id,
            "server": "workspace",
            "tool": "read_workspace_object",
            "arguments": {"object_id": "public", "revision": 1},
        }
        read = agent.client.request(
            "mcpServer/tool/call", params, response_model=McpServerToolCallResponse
        )
        actual = json.loads(read.content[0]["text"])
        assert not read.is_error and actual["content"] == {"text": "Approved record"}
        denied = agent.client.request(
            "mcpServer/tool/call",
            {**params, "arguments": {"object_id": "private"}},
            response_model=McpServerToolCallResponse,
        )
        assert denied.is_error and "forbidden" in denied.content[0]["text"]
        assert "Private record" not in denied.content[0]["text"]
    finally:
        agent.close()


def test_agent_disables_builtin_skills_before_thread_start(tmp_path):
    materials = tmp_path / "materials"
    materials.mkdir()
    source = b"Engineering material fixture."
    (materials / "source.md").write_bytes(source)
    (materials / "manifest.json").write_text(
        json.dumps(
            {
                "source": {
                    "path": "source.md",
                    "source_ref": "engineering-fixture",
                    "sha256": hashlib.sha256(source).hexdigest(),
                }
            }
        )
    )
    events = []
    agent = CodexAgent(
        tmp_path / "agent",
        ModelBinding("glm-direct", "glm-5.3-flash", "low"),
        provider_base_url="http://127.0.0.1:9",
        materials=materials,
        instructions="Non-inference setup test.",
        on_event=lambda *event: events.append(event),
    )
    try:
        actual = agent.start()
        assert actual["thread"]["turns"] == []
        assert actual["instructionSources"] == []
        skills = next(payload for method, payload in events if method == "skills/list")
        assert not [
            skill for entry in skills["data"] for skill in entry["skills"] if skill["enabled"]
        ]
        assert [method for method, _ in events].index("skills/list") < [
            method for method, _ in events
        ].index("thread/start")
        assert agent.active_turn is None
        mcp = next(payload for method, payload in events if method == "mcpServerStatus/list")
        assert len(mcp["data"]) == 1
        workspace = mcp["data"][0]
        assert set(workspace["tools"]) == {"read_material"}
        assert workspace["tools"]["read_material"]["annotations"]["readOnlyHint"] is True
        assert workspace["resources"] == workspace["resourceTemplates"] == []
    finally:
        agent.close()


def test_real_wire_namespaces_preserve_full_tool_identity():
    assert outbound_tool_names(
        [
            {"type": "function", "name": "list_mcp_resources"},
            {
                "type": "namespace",
                "name": "mcp__workspace",
                "tools": [
                    {"type": "function", "name": "read_material"},
                ],
            },
        ]
    ) == ["list_mcp_resources", "mcp__workspace__read_material"]


def test_local_tool_refusal_is_recorded_before_any_upstream_attempt(tmp_path):
    # The Host bridge imports legacy utility modules. Keep that process separate
    # from the new package's import-isolation test and from every Agent context.
    script = Path(__file__).resolve().parents[1] / "scripts/live_probe.py"
    code = """
import json,runpy,sys,urllib.request,urllib.error
from pathlib import Path
ObservedProvider=runpy.run_path(sys.argv[1])["ObservedProvider"]
events=[]
forwarded=[]
provider=ObservedProvider(b"engineering-fixture", evidence=Path(sys.argv[2]),
                          provider_id="glm-direct",on_attempt=events.append)
def forbidden_forward(body):
    forwarded.append(True)
    raise AssertionError("local refusal must never forward upstream")
provider.forward=forbidden_forward
provider.start()
try:
    body=json.dumps({"model":"glm-5.3-flash","reasoning":{"effort":"low"},
                     "tools":[{"type":"function","name":"write_model"}]}).encode()
    request=urllib.request.Request(provider.base_url+"/responses",data=body,
                                   headers={"Content-Type":"application/json"})
    try:
        urllib.request.urlopen(request,timeout=10)
    except urllib.error.HTTPError as error:
        assert error.code==402
    else:
        raise AssertionError("unapproved tool should be refused")
    assert not forwarded
    assert len(events)==1 and events[0]["status"]=="not_admitted"
    assert events[0]["event"]=="attempt_end"
    valid={"model":"glm-5.3-flash","reasoning":{"effort":"low"},"tools":[
      {"type":"namespace","name":"mcp__workspace","tools":[
        {"type":"function","name":"read_material"}]}]}
    assert provider.admit_attempt({"request_id":"valid","attempt_index":1},request=valid)
finally:
    assert provider.stop()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(script), str(tmp_path / "outbound.jsonl")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
