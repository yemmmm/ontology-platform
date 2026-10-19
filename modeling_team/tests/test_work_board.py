"""R4.4-001 engineering checks. No provider, modeling start or semantic claims."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest
import yaml

from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


@pytest.fixture
def broker(tmp_path):
    root = tmp_path / "workspaces/modeling-runs/board-run"
    return TeamTransportBroker(
        root / "transport/broker",
        {("a", "b"), ("b", "a"), ("c", "b"), ("b", "c")},
        run_id="board-run",
        agent_roles={"a": "modeling", "b": "protocol", "c": "coordinator", "judge": "acceptance"},
    )


def call(broker, actor, name, **arguments):
    result = mcp_response(
        {"method": "tools/call", "params": {"name": name, "arguments": arguments}},
        broker=broker,
        agent_id=actor,
    )
    return json.loads(result["content"][0]["text"])


def request(broker, actor="a", recipient="b", request_id=None, **kwargs):
    return call(
        broker,
        actor,
        "send_team_message",
        recipient_id=recipient,
        text="校验关系",
        work_request={
            "action": "request",
            "request_id": request_id or str(uuid4()),
            "summary": "期待校验关系",
            **kwargs,
        },
    )


def test_card_changes_only_on_content_change_and_is_endpoint_bound(broker):
    card = {"current_work": "理解设备资料", "near_term_goals": ["分析生命周期"]}
    first = call(broker, "a", "update_work_card", card=card)
    repeated = call(broker, "a", "update_work_card", card=card)
    assert repeated["changed"] is False
    assert repeated["record_seq"] == first["record_seq"]
    board = call(broker, "b", "get_work_board")
    own = next(c for c in board["cards"] if c["agent_id"] == "a")
    assert own["card"]["current_work"] == "理解设备资料"
    assert (
        next(c for c in board["cards"] if c["agent_id"] == "b")["report_status"] == "not_reported"
    )
    assert own["observed_runtime"]["status"] == "unknown"
    with pytest.raises(RoutingError):
        call(broker, "a", "update_work_card", card={**card, "agent_id": "b"})
    with pytest.raises(RoutingError):
        call(broker, "judge", "update_work_card", card=card)
    assert call(broker, "a", "get_work_board")["cards"][0]["reported_at"] == first["reported_at"]


def test_shared_requests_feedback_resolution_late_and_retry(broker):
    rid = str(uuid4())
    first = request(broker, request_id=rid, blocking=True)
    again = request(broker, request_id=rid, blocking=True)
    assert first["delivery_id"] == again["delivery_id"]
    assert len(broker.drain()) == 1
    assert first["message_status"] == "queued"
    request(broker, actor="c")
    incoming = call(broker, "b", "get_work_board")["requests"]
    assert len(incoming) == 2
    assert {r["requester_id"] for r in incoming} == {"a", "c"}
    with pytest.raises(RoutingError, match="work_request_conflict"):
        request(broker, request_id=rid, blocking=False)
    with pytest.raises(RoutingError):
        call(broker, "c", "get_work_board", request_id=rid)
    update = str(uuid4())
    feedback = dict(
        recipient_id="a",
        text="关系校验结果",
        work_request={
            "action": "feedback",
            "request_id": rid,
            "update_id": update,
            "assignee_report": "responded",
        },
    )
    result = call(broker, "b", "send_team_message", **feedback)
    assert (
        call(broker, "b", "send_team_message", **feedback)["delivery_id"] == result["delivery_id"]
    )
    projection = call(broker, "a", "get_work_board", request_id=rid)["requests"][0]
    assert projection["assignee_report"] == "responded"
    assert projection["requester_state"] == "open"
    before = len(broker.drain())
    assert before == 2
    call(
        broker,
        "a",
        "resolve_work_request",
        request_id=rid,
        resolution="resolved",
        note="已继续分析",
        update_id=str(uuid4()),
    )
    assert broker.drain() == []  # resolved does not add a confirmation handshake
    feedback["work_request"]["update_id"] = str(uuid4())
    call(broker, "b", "send_team_message", **feedback)
    projection = call(broker, "b", "get_work_board", request_id=rid)["requests"][0]
    assert projection["requester_state"] == "resolved"
    assert projection["feedback_refs"][-1]["late"] is True


def test_history_versions_frozen_paging_and_time_filter(broker):
    for text in ("理解资料", "分析业务", "核对成果"):
        call(broker, "a", "update_work_card", card={"current_work": text})
    first = call(broker, "a", "get_work_board", agent_id="a", view="history", limit=1)
    seq = first["history"][0]["record_seq"]
    call(broker, "a", "update_work_card", card={"current_work": "交接"})
    page = first
    all_rows = first["history"][:]
    while page["continuation"]:
        page = call(
            broker,
            "a",
            "get_work_board",
            agent_id="a",
            view="history",
            limit=1,
            cursor=page["continuation"],
        )
        all_rows.extend(page["history"])
    assert [r["card"]["current_work"] for r in all_rows] == ["理解资料", "分析业务", "核对成果"]
    assert all_rows[1]["previous_record_seq"] == seq
    assert "current_work" in all_rows[1]["changed_fields"]
    exact = call(broker, "a", "get_work_board", agent_id="a", view="version", record_seq=seq)
    assert exact["history"][0]["card"]["current_work"] == "理解资料"
    with pytest.raises(RoutingError):
        call(broker, "a", "get_work_board", agent_id="a", view="history", from_time="2026-10-19")
    path = broker.work_board.path
    path.write_bytes(path.read_bytes().replace("理解".encode(), "改写".encode(), 1))
    with pytest.raises(RoutingError, match="source_changed"):
        call(
            broker,
            "a",
            "get_work_board",
            agent_id="a",
            view="history",
            cursor=first["continuation"],
        )


def test_record_failure_does_not_send_or_poison_normal_transport(broker, monkeypatch):
    def failed(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(broker.work_board, "append", failed)
    with pytest.raises(RoutingError, match="work_board_unavailable"):
        request(broker)
    assert broker.drain() == []
    ordinary = broker.send("a", "b", "原通道仍然可用")
    assert broker.drain() == [ordinary]


def test_withdrawal_is_one_message_and_bad_feedback_has_no_effect(broker):
    rid = str(uuid4())
    request(broker, request_id=rid)
    broker.drain()
    with pytest.raises(RoutingError):
        call(
            broker,
            "c",
            "send_team_message",
            recipient_id="b",
            text="伪反馈",
            work_request={
                "action": "feedback",
                "request_id": rid,
                "update_id": str(uuid4()),
                "assignee_report": "responded",
            },
        )
    assert broker.drain() == []
    args = dict(request_id=rid, resolution="withdrawn", note="范围已调整", update_id=str(uuid4()))
    first = call(broker, "a", "resolve_work_request", **args)
    assert call(broker, "a", "resolve_work_request", **args)["delivery_id"] == first["delivery_id"]
    assert len(broker.drain()) == 1


def host_setup(broker):
    root = broker.work_board.root
    root.mkdir(parents=True, exist_ok=True)
    profile = {
        "agents": [
            {"agent_id": name, "package": role}
            for name, role in (
                ("a", "modeling"),
                ("b", "protocol"),
                ("c", "coordinator"),
                ("judge", "acceptance"),
            )
        ],
        "communication": [
            {"from": sender, "to": [recipient]} for sender, recipient in broker.permissions
        ],
    }
    (root / "profile.snapshot.yaml").write_text(yaml.safe_dump(profile))
    return root, root.parents[2]


def published_statistics(root, *, hidden=True):
    from modeling_team.close_statistics import ActivityRecorder, publish_close_statistics

    source = root / "numeric.jsonl"
    recorder = ActivityRecorder(
        root,
        {"runtime": "codex", "agent_id": "a", "role": "modeling", "run_id": root.name},
        usage_sources=[{"path": str(source), "kind": "capture"}],
        fresh_session=True,
    )
    recorder.bind("actual-thread-a")
    source.write_text(
        json.dumps(
            {
                "event": "thread_usage",
                "runtime": "codex",
                "runtime_session_id": "actual-thread-a",
                "thread_id": "actual-thread-a",
                "process_instance": recorder.context["process_instance"],
                "received_at": recorder.started_at,
                "total": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20},
            }
        )
        + "\n"
    )
    recorder.exit(0)
    if hidden:
        private = ActivityRecorder(
            root,
            {"runtime": "codex", "agent_id": "judge", "role": "acceptance", "run_id": root.name},
        )
        private.exit(0)
        other = ActivityRecorder(
            root, {"runtime": "codex", "agent_id": "a", "role": "modeling", "run_id": "another-run"}
        )
        other.exit(0)
    return publish_close_statistics(root, view="run_close", task_ref="task")


def test_host_history_and_statistics_share_retained_versions_without_double_count(broker):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "理解资料"})
    call(broker, "a", "update_work_card", card={"current_work": "分析业务"})
    pointer = published_statistics(root)
    result = get_team_work_board(
        root.name, view="history", include_statistics=True, repository_root=repository
    )
    assert len(result["history"]) == 2
    groups = result["statistics_groups"]
    assert len(groups) == 1
    assert groups[0]["agent_id"] == "a"
    assert groups[0]["usage"]["tokens"]["input_tokens"] == 100
    assert "known_token_share" not in json.dumps(result)
    assert "judge" not in json.dumps(result)
    assert "another-run" not in json.dumps(result)
    assert all(binding["scope"] == "agent_not_subdivided" for binding in result["bindings"])
    assert all(binding["card_tokens"] is None for binding in result["bindings"])
    assert result["statistics"]["source"]["report"]["path"] == pointer["report_ref"]
    filtered = get_team_work_board(
        root.name,
        view="history",
        from_time="2000-01-01T00:00:00Z",
        to_time="2000-01-01T01:00:00Z",
        include_statistics=True,
        repository_root=repository,
    )
    assert filtered["history"] == []
    assert filtered["statistics"]["statistics_window"] == result["statistics"]["statistics_window"]
    assert filtered["statistics_groups"] == groups


def test_close_archives_fixed_history_and_statistics_and_queries_are_read_only(broker):
    from modeling_team.host_ops import get_team_work_board
    from modeling_team.close_statistics import publish_close_statistics

    root, repository = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "原版资料"})
    pointer = published_statistics(root, hidden=False)
    archive_pointer = json.loads((root / "evidence/work-board-retrospective.json").read_text())
    archive_ref = archive_pointer["archive_ref"]
    index = json.loads((root / archive_ref).read_text())
    assert (root / index["history_source"]["path"]).stat().st_mode & 0o777 == 0o600
    assert (root / archive_ref).parent.stat().st_mode & 0o777 == 0o700
    assert (root / archive_ref).stat().st_mode & 0o777 == 0o600
    call(broker, "a", "update_work_card", card={"current_work": "新资料"})
    numeric = root / "numeric.jsonl"
    row = json.loads(numeric.read_text())
    row["total"]["input_tokens"] = 200
    numeric.write_text(json.dumps(row) + "\n")
    second = publish_close_statistics(root, view="run_close", task_ref="task")
    assert second["report_ref"] != pointer["report_ref"]
    new_archive = json.loads((root / "evidence/work-board-retrospective.json").read_text())
    assert new_archive["archive_ref"] != archive_ref
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    archived = get_team_work_board(
        root.name,
        view="history",
        include_statistics=True,
        source_ref={"archive_ref": archive_ref},
        repository_root=repository,
    )
    assert [r["card"]["current_work"] for r in archived["history"]] == ["原版资料"]
    assert archived["statistics_groups"][0]["usage"]["tokens"]["input_tokens"] == 100
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    # A pinned missing original never silently falls forward to the newer report.
    (root / pointer["report_ref"]).unlink()
    missing = get_team_work_board(
        root.name,
        view="history",
        include_statistics=True,
        source_ref={"archive_ref": archive_ref},
        repository_root=repository,
    )
    assert missing["history"]
    assert missing["statistics"]["status"] == "unavailable"


def test_archive_failure_is_separate_from_numeric_publication(broker, monkeypatch):
    from modeling_team import work_board
    from modeling_team.close_statistics import read_close_statistics

    root, _ = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "卡片正文不进统计"})
    original = work_board._atomic_json

    def fail_index(path, value):
        if path.name == "index.json":
            raise OSError("archive disk error")
        return original(path, value)

    monkeypatch.setattr(work_board, "_atomic_json", fail_index)
    result = published_statistics(root, hidden=False)
    assert result["report_status"] == "ready"
    assert read_close_statistics(root) == result
    assert "卡片正文" not in (root / result["report_ref"]).read_text()
    assert (
        json.loads((root / "evidence/work-board-retrospective.json").read_text())["status"]
        == "archive_unavailable"
    )


def test_bad_history_partial_previous_unknown_and_old_run_are_explicit(broker):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "旧"})
    call(broker, "a", "update_work_card", card={"current_work": "新"})
    lines = broker.work_board.path.read_bytes().splitlines(keepends=True)
    broker.work_board.path.write_bytes(b"bad\n" + lines[1] + b'{"incomplete":')
    result = get_team_work_board(
        root.name, agent_id="a", view="history", repository_root=repository
    )
    assert result["history"][0]["previous_status"] == "unknown"
    assert result["history"][0]["changed_fields"] is None
    assert any("history_bad_line" in item for item in result["limitations"])
    assert any("history_truncated" in item for item in result["limitations"])
    broker.work_board.path.unlink()
    old = get_team_work_board(root.name, view="history", repository_root=repository)
    assert old["status"] == "unavailable"
    assert old["history"] == []


def test_structurally_bad_history_rows_are_disclosed_without_breaking_reads(broker):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "保留有效原件"})
    valid = broker.work_board.load()[0][0]
    malformed = {**valid, "record_seq": 2, "previous_record_seq": [1]}
    with broker.work_board.path.open("a") as stream:
        stream.write(json.dumps(malformed) + "\n")
    result = get_team_work_board(root.name, view="history", repository_root=repository)
    assert len(result["history"]) == 1
    assert "history_bad_line:2" in result["limitations"]


def test_recorded_request_with_unknown_receipt_is_not_automatically_replayed(broker):
    rid = str(uuid4())
    request(broker, request_id=rid)
    reopened = TeamTransportBroker(
        broker.evidence_root,
        broker.permissions,
        run_id="board-run",
        agent_roles={"a": "modeling", "b": "protocol"},
    )
    result = call(reopened, "b", "get_work_board", request_id=rid)
    assert result["requests"][0]["message_bindings"][0]["message_status"] == "unknown"
    with pytest.raises(RoutingError, match="work_message_unknown"):
        request(reopened, request_id=rid)
    assert reopened.drain() == []


def test_delivery_projection_no_private_context_result_refs_or_routine_wakeup(broker):
    from modeling_team.host_ops import get_team_work_board
    from modeling_team.delivery import _decision_events

    root, repository = host_setup(broker)
    rid = str(uuid4())
    request(broker, request_id=rid)
    call(
        broker,
        "b",
        "send_team_message",
        recipient_id="a",
        text="private-peer-result",
        work_request={
            "action": "feedback",
            "request_id": rid,
            "update_id": str(uuid4()),
            "assignee_report": "responded",
            "result_refs": ["private-peer-result-ref"],
        },
    )
    data = get_team_work_board(
        root.name, view="history", _projection="delivery", repository_root=repository
    )
    assert "host_context" not in data
    assert "retrospective" not in data
    assert "private-peer-result" not in json.dumps(data)
    events = [
        {"source": "work-board-events.jsonl", "data": row} for row in broker.work_board.load()[0]
    ]
    state = {}
    _decision_events(root.name, {"ok": True, "data": {"events": events}}, state)
    assert state[root.name]["selected"] == []


def test_real_standalone_mcp_uses_bound_socket_without_repo_or_pythonpath(broker, tmp_path):
    home = tmp_path / "isolated-home"
    home.mkdir()
    for name in ("transport_mcp.py", "interventions.py", "work_board.py"):
        shutil.copyfile(Path(__file__).parents[1] / name, home / name)
    broker.start(["a", "b", "c", "judge"])
    commands = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "update_work_card",
                "arguments": {"card": {"current_work": "真正的MCP通道"}},
            },
        },
    ]
    try:
        process = subprocess.run(
            ["/usr/bin/python3", str(home / "transport_mcp.py")],
            input="".join(json.dumps(row) + "\n" for row in commands),
            text=True,
            capture_output=True,
            cwd=home,
            env={"PATH": os.defpath, "TEAM_TRANSPORT_SOCKET": str(broker.endpoint("a"))},
            timeout=10,
            check=True,
        )
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        tools = {tool["name"] for tool in replies[1]["result"]["tools"]}
        assert {"update_work_card", "resolve_work_request", "get_work_board"} <= tools
        assert json.loads(replies[2]["result"]["content"][0]["text"])["changed"] is True
        board = call(broker, "b", "get_work_board", agent_id="a")
        assert board["cards"][0]["card"]["current_work"] == "真正的MCP通道"
        assert not {"update_work_card", "resolve_work_request", "get_work_board"} & {
            t["name"]
            for t in mcp_response({"method": "tools/list"}, broker=broker, agent_id="judge")[
                "tools"
            ]
        }
    finally:
        broker.stop()


def test_real_host_mcp_and_delivery_read_the_same_authorized_projection(
    broker, tmp_path, monkeypatch
):
    from functools import partial
    from modeling_team import host_ops, host_ops_mcp
    from modeling_team.tests.test_host_ops_mcp import _session, _payload
    from modeling_team.tests.test_delivery_session import session

    root, repository = host_setup(broker)
    call(broker, "a", "update_work_card", card={"current_work": "进度摘要"})
    monkeypatch.setattr(
        host_ops_mcp,
        "get_team_work_board",
        partial(host_ops.get_team_work_board, repository_root=repository),
    )

    async def host_call(client):
        return _payload(
            await client.call_tool("get_team_work_board", {"run_id": root.name, "agent_id": "a"})
        )

    (result,) = _session([host_call])
    assert result["ok"] is True
    assert result["data"]["cards"][0]["card"]["current_work"] == "进度摘要"
    delivery = session(tmp_path)
    delivery.repository_root = repository
    delivery.run_ids.add(root.name)
    answer = delivery.call_tool("get_team_work_board", {"run_id": root.name, "agent_id": "a"})
    assert answer["ok"] is True
    assert answer["data"]["cards"][0]["card"]["current_work"] == "进度摘要"
    assert "host_context" not in answer["data"]
    assert (
        delivery.call_tool("get_team_work_board", {"run_id": root.name, "_projection": "host"})[
            "ok"
        ]
        is False
    )
    assert delivery.call_tool("get_team_work_board", {"run_id": "unbound"})["ok"] is False
    published = published_statistics(root)
    for relative in (
        "evidence/work-board-events.jsonl",
        "evidence/close-statistics.json",
        published["report_ref"],
        published["scope_ref"],
    ):
        raw = delivery.call_tool("read_delivery_artifact", {"path": str(root / relative)})
        assert raw["ok"] is False and raw["error"]["code"] == "artifact_forbidden"
    safe = delivery.call_tool(
        "get_team_work_board", {"run_id": root.name, "include_statistics": True}
    )
    assert safe["ok"] is True
    assert all(g["agent_id"] == "a" for g in safe["data"]["statistics_groups"])


def test_cli_history_version_and_archive_read_without_inference(broker, monkeypatch, capsys):
    from modeling_team import __main__ as cli

    root, repository = host_setup(broker)
    first = call(broker, "a", "update_work_card", card={"current_work": "CLI原件"})
    monkeypatch.setattr(cli, "repository_root", lambda: repository)
    monkeypatch.setattr(
        "sys.argv",
        [
            "modeling_team",
            "work-board",
            "--run-id",
            root.name,
            "--agent",
            "a",
            "--record-seq",
            str(first["record_seq"]),
            "--json",
        ],
    )
    assert cli.main() == 0
    exact = json.loads(capsys.readouterr().out)
    assert exact["history"][0]["card"]["current_work"] == "CLI原件"
    published_statistics(root, hidden=False)
    archive = json.loads((root / "evidence/work-board-retrospective.json").read_text())[
        "archive_ref"
    ]
    monkeypatch.setattr(
        "sys.argv",
        [
            "modeling_team",
            "work-board",
            "--run-id",
            root.name,
            "--history",
            "--archive-ref",
            archive,
            "--with-statistics",
            "--json",
        ],
    )
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["statistics_groups"][0]["usage"]["tokens"]["input_tokens"] == 100


def test_minimal_chain_roles_are_read_from_the_frozen_actual_roster(broker):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    profile = yaml.safe_load((root / "profile.snapshot.yaml").read_text())
    profile["agents"][0]["package"] = "minimal-chain-modeling"
    profile["agents"][2]["package"] = "minimal-chain-coordinator"
    (root / "profile.snapshot.yaml").write_text(yaml.safe_dump(profile))
    (root / "baseline-manifest.json").write_text(
        json.dumps(
            {
                "run_id": root.name,
                "work_board_roster": {
                    "a": "modeling",
                    "b": "protocol",
                    "c": "coordinator",
                    "judge": "acceptance",
                },
            }
        )
    )
    call(broker, "a", "update_work_card", card={"current_work": "精简角色实际工作"})
    answer = get_team_work_board(root.name, agent_id="a", repository_root=repository)
    assert answer["cards"][0]["card"]["current_work"] == "精简角色实际工作"


def test_statistics_publication_and_history_stay_fixed_across_all_pages(broker):
    from modeling_team.host_ops import get_team_work_board
    from modeling_team.close_statistics import publish_close_statistics

    root, repository = host_setup(broker)
    for i in range(3):
        call(broker, "a", "update_work_card", card={"current_work": f"工作{i}"})
    original = published_statistics(root, hidden=False)
    first = get_team_work_board(
        root.name,
        agent_id="a",
        view="history",
        include_statistics=True,
        limit=1,
        repository_root=repository,
    )
    row = json.loads((root / "numeric.jsonl").read_text())
    row["total"]["input_tokens"] = 999
    (root / "numeric.jsonl").write_text(json.dumps(row) + "\n")
    publish_close_statistics(root, view="run_close", task_ref="task")
    call(broker, "a", "update_work_card", card={"current_work": "不进入旧分页"})
    page, history, groups = first, first["history"][:], first["statistics_groups"][:]
    while page["continuation"]:
        page = get_team_work_board(
            root.name,
            agent_id="a",
            view="history",
            include_statistics=True,
            limit=1,
            cursor=page["continuation"],
            repository_root=repository,
        )
        history.extend(page["history"])
        groups.extend(page["statistics_groups"])
    assert len(history) == 3 and len(groups) == 1
    assert groups[0]["usage"]["tokens"]["input_tokens"] == 100
    assert page["statistics"]["source"]["report"]["path"] == original["report_ref"]


def test_session_totals_are_reused_once_across_process_generations_and_conflicts_stay_unknown(
    broker,
):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    broker.work_board.member_reader = lambda actor: {
        "run_id": root.name,
        "agent_id": actor,
        "runtime": "codex",
        "runtime_session_id": "native",
        "process_instance": "p1",
    }
    call(broker, "a", "update_work_card", card={"current_work": "第一代进程"})
    broker.work_board.member_reader = lambda actor: {
        "run_id": root.name,
        "agent_id": actor,
        "runtime": "codex",
        "runtime_session_id": "conflicting",
        "process_instance": "p2",
    }
    call(broker, "a", "update_work_card", card={"current_work": "绑定冲突保留未知"})
    members = [
        {
            "run_id": root.name,
            "agent_id": "a",
            "runtime": "codex",
            "role": "modeling",
            "runtime_session_id": "native",
            "process_instance": process,
        }
        for process in ("p1", "p2")
    ]
    target = root / ("evidence/close-statistics/report-" + "1" * 24)
    target.mkdir(parents=True)
    (target / "scope.json").write_text(json.dumps({"close_statistics": {"members": members}}))
    (target / "report.json").write_text(
        json.dumps(
            {
                "close_statistics": {
                    "members": [{**m, "usage": {"tokens": {"input_tokens": None}}} for m in members]
                },
                "task_usage": {
                    "groups": [
                        {
                            "identity": {
                                "runtime": "codex",
                                "run_id": root.name,
                                "runtime_session_id": "native",
                                "role": "modeling",
                            },
                            "tokens": {"input_tokens": 123},
                        }
                    ]
                },
            }
        )
    )
    (root / "evidence/close-statistics.json").write_text(
        json.dumps(
            {
                "report_status": "ready",
                "report_ref": str((target / "report.json").relative_to(root)),
                "scope_ref": str((target / "scope.json").relative_to(root)),
            }
        )
    )
    result = get_team_work_board(
        root.name, view="history", include_statistics=True, repository_root=repository
    )
    members = [g for g in result["statistics_groups"] if g["group_type"] == "registered_member"]
    sessions = [g for g in result["statistics_groups"] if g["group_type"] == "session_usage"]
    assert len(members) == 2 and len(sessions) == 1
    assert all(g["usage"]["tokens"]["input_tokens"] is None for g in members)
    assert sessions[0]["usage"]["tokens"]["input_tokens"] == 123
    assert sessions[0]["additive_to_member_usage"] is False
    assert len(result["bindings"][0]["group_ids"]) == 1
    assert result["bindings"][1]["status"] == "unknown"


def test_transport_receipt_failure_is_partial_and_late_terminal_recipient_is_visible(
    broker, monkeypatch
):
    rid = str(uuid4())
    delivery = request(broker, request_id=rid)

    def fail(*args, **kwargs):
        raise OSError("receipt failure")

    with monkeypatch.context() as patch:
        patch.setattr(broker.work_board, "append", fail)
        broker.record_work_transport(delivery["delivery_id"], "runtime_accepted")
    repeated = request(broker, request_id=rid)
    assert repeated["record_status"] == "partial"
    assert repeated["message_status"] == "runtime_accepted"
    assert len(broker.drain()) == 1
    broker.report("b", "completed", "已完成")
    late = request(broker)
    assert late["message_status"] == "recipient_terminal"
    assert late["record_status"] == "recorded"
    assert broker.drain() == []


@pytest.mark.parametrize("report", ["needs_input", "unable", "in_progress", "responded"])
def test_feedback_needs_no_acceptance_handshake_and_keeps_the_original_reply_slot(broker, report):
    rid = str(uuid4())
    original = call(
        broker,
        "a",
        "send_team_message",
        recipient_id="b",
        text="请求校验",
        expects_reply=True,
        work_request={"action": "request", "request_id": rid, "summary": "校验"},
    )
    broker.drain()
    call(
        broker,
        "b",
        "send_team_message",
        recipient_id="a",
        text="真实反馈",
        expects_reply=False,
        work_request={
            "action": "feedback",
            "request_id": rid,
            "update_id": str(uuid4()),
            "assignee_report": report,
        },
    )
    assert broker._pending_replies[original["delivery_id"]] is None
    request_view = call(broker, "a", "get_work_board", request_id=rid)["requests"][0]
    assert request_view["requester_state"] == "open" and request_view["assignee_report"] == report


def test_peer_filter_counts_and_clearing_a_wait_are_accurate(broker):
    request(broker)
    request(broker, actor="c")
    own = call(broker, "a", "get_work_board")
    assert {row["agent_id"] for row in own["cards"]} == {"a", "b"}
    assert own["coverage"]["requests"]["total"] == 1
    assert "c" not in {row["requester_id"] for row in own["requests"]}
    call(broker, "a", "update_work_card", card={"current_work": "分析", "waiting_note": "待校验"})
    call(broker, "a", "update_work_card", card={"current_work": "分析"})
    assert (
        call(broker, "a", "get_work_board", agent_id="a")["cards"][0]["card"]["waiting_note"] == ""
    )


@pytest.mark.parametrize("dispatch_fails", [False, True])
def test_runner_forwards_reference_and_records_actual_acceptance_before_projection(dispatch_fails):
    from modeling_team.contracts import repository_root
    from modeling_team.runner import TeamRunner
    from modeling_team.tests.test_runner import CapturingAdapter

    root = repository_root()

    class Adapter(CapturingAdapter):
        def send_message(self, agent_id, delivery):
            if dispatch_fails and delivery.text == "检验原件":
                raise RuntimeError("adapter outcome unknown")
            return super().send_message(agent_id, delivery)

    adapter = Adapter()
    runner = TeamRunner(repository_root=root, adapter=adapter)
    run_id = "unit-r44001-" + uuid4().hex
    run_root = root / "workspaces/modeling-runs" / run_id
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
            task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
            scope={"mode": "create"},
        )
        runner.start()
        rid = str(uuid4())
        queued = call(
            runner.transport,
            "modeling",
            "send_team_message",
            recipient_id="protocol",
            text="检验原件",
            work_request={"action": "request", "request_id": rid, "summary": "核对关系"},
        )
        assert queued["message_status"] == "queued"
        if dispatch_fails:
            with pytest.raises(RuntimeError, match="adapter outcome unknown"):
                runner.drain()
            view = call(runner.transport, "protocol", "get_work_board", request_id=rid)
            binding = view["requests"][0]["message_bindings"][0]
            assert binding["message_status"] == "unknown"
            assert binding["receipt_ref"]["source"] == "runtime_adapter.send_message"
            assert queued["delivery_id"] not in runner.transport._acknowledged_deliveries
            return
        runner.drain()
        delivered = next(d for _, d in adapter.messages if d.text == "检验原件")
        assert delivered.work_request_ref["run_id"] == run_id
        assert delivered.work_request_ref["request_id"] == rid
        assert delivered.work_request_ref["requester_id"] == "modeling"
        view = call(runner.transport, "protocol", "get_work_board", request_id=rid)
        assert view["requests"][0]["message_bindings"][0]["message_status"] == "runtime_accepted"
        events = [
            json.loads(line)
            for line in (run_root / "evidence/deliveries.jsonl").read_text().splitlines()
        ]
        assert (
            next(r for r in events if r.get("delivery_id") == delivered.delivery_id)[
                "work_request_ref"
            ]
            == delivered.work_request_ref
        )
        assert sum(d.text == "检验原件" for _, d in adapter.messages) == 1
    finally:
        runner.cleanup()
        shutil.rmtree(run_root, ignore_errors=True)


def test_real_codex_namespace_discovers_board_tools_without_a_model_turn(tmp_path, monkeypatch):
    """Use the installed App Server and production staging; network is disabled."""
    from types import SimpleNamespace
    from modeling_team.contracts import repository_root, _load_package
    from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent

    if not shutil.which("codex") or not shutil.which("bwrap"):
        pytest.skip("installed Codex and bubblewrap are required for native discovery")
    root = repository_root()
    broker = TeamTransportBroker(
        tmp_path / "transport/broker",
        {("modeling", "coordinator")},
        run_id="native-loading-only",
        agent_roles={"modeling": "modeling", "coordinator": "coordinator"},
    )
    broker.start(["modeling"])
    adapter = CodexRuntimeAdapter(repository_root=root)
    adapter._run_root = tmp_path
    (tmp_path / "transport-root").write_text(str(broker.root))
    home, work, skills = (tmp_path / name for name in ("home", "work", "skills"))
    for path in (home, work, skills, tmp_path / "sources"):
        path.mkdir(mode=0o700)
    auth = tmp_path / "test-auth.json"
    auth.write_text("{}")
    auth.chmod(0o600)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: auth)
    agent = _Agent("modeling", _load_package(root, "modeling"), home, work, skills)
    adapter.agents["modeling"] = agent
    original_namespace = adapter.namespace_command
    monkeypatch.setattr(
        adapter,
        "namespace_command",
        lambda item: [
            *original_namespace(item)[:1],
            "--unshare-net",
            *original_namespace(item)[1:],
        ],
    )
    try:
        adapter._stage_skills(agent)
        adapter._write_config(SimpleNamespace(root=tmp_path, protocol_key=None), agent)
        agent.process = adapter._start_process(agent)
        adapter._initialize(agent)
        assert agent.thread_id
        servers = adapter._rpc(agent, "mcpServerStatus/list", {"detail": "full"})["data"]
        transport = next(server for server in servers if server["name"] == "team_transport")
        assert {
            "update_work_card",
            "resolve_work_request",
            "get_work_board",
        } <= adapter._mcp_tool_names(transport["tools"])
        assert not agent.active_turn_id and broker.results == {}
    finally:
        adapter.stop()
        broker.stop()


def test_card_references_keep_the_original_material_audience(broker, tmp_path):
    from modeling_team.handoff_materials import HandoffMaterials

    source = tmp_path / "source"
    source.mkdir()
    (source / "result.txt").write_text("原成果")
    store = HandoffMaterials(tmp_path / "materials", "board-run")
    store.register_actor("a", {"/agent/work": source}, {"b", "c"})
    store.register_actor("b", {}, {"a"})
    store.register_actor("c", {}, {"a"})
    broker.materials = store
    broker.permissions.add(("a", "c"))
    private = store.publish("a", "c", "/agent/work/result.txt")
    call(
        broker,
        "a",
        "update_work_card",
        card={
            "current_work": "成果",
            "latest_result_refs": [{"material_id": private["material_id"]}],
        },
    )
    restricted = call(broker, "b", "get_work_board", agent_id="a")["cards"][0]
    assert restricted["card"]["latest_result_refs"] == []
    assert restricted["references_complete"] is False
    assert call(broker, "c", "get_work_board", agent_id="a")["cards"][0]["card"][
        "latest_result_refs"
    ]
    shared = store.publish("a", "b", "/agent/work/result.txt")
    call(
        broker,
        "a",
        "update_work_card",
        card={
            "current_work": "成果",
            "latest_result_refs": [{"material_id": shared["material_id"]}],
        },
    )
    assert call(broker, "b", "get_work_board", agent_id="a")["cards"][0]["card"][
        "latest_result_refs"
    ]
    history = call(broker, "b", "get_work_board", agent_id="a", view="history")
    assert private["material_id"] not in json.dumps(history)


def test_host_wait_context_reuses_the_existing_journal_and_stays_private(broker, tmp_path):
    from modeling_team.host_ops import get_team_work_board

    root, repository = host_setup(broker)
    (root / "control").mkdir()
    session = tmp_path / "host-session"
    session.mkdir()
    session_ref = session / "session.json"
    session_ref.write_text(json.dumps({"session_id": "host", "run_ids": [root.name]}))
    (root / "control/host-supervisor.json").write_text(
        json.dumps({"session_ref": str(session_ref)})
    )
    rows = [
        {
            "event": "delivery_yield",
            "session_id": "host",
            "waiting_for": [{"run_id": root.name}],
            "next_action": "保留已有等待",
            "reason": "Host私有上下文",
        },
        {
            "event": "host_action_request",
            "run_id": root.name,
            "request_id": "r1",
            "kind": "cq_review",
        },
        {
            "event": "host_action_result",
            "run_id": root.name,
            "request_id": "r1",
            "status": "failed",
        },
    ]
    (session / "session-events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    before = {str(p): p.read_bytes() for p in session.iterdir()}
    host = get_team_work_board(root.name, repository_root=repository)
    assert host["host_context"]["delivery_yield"]["next_action"] == "保留已有等待"
    assert host["host_context"]["unresolved_total"] == 1
    assert before == {str(p): p.read_bytes() for p in session.iterdir()}
    assert "Host私有上下文" not in json.dumps(
        call(broker, "a", "get_work_board"), ensure_ascii=False
    )
