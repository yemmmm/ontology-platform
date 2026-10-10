#!/usr/bin/env python3
"""Controlled Codex App Server executable fixture (no model, no network).

This script is the ``codex`` binary that ``CodexRuntimeAdapter`` resolves first
on a fixture PATH and that the private Examiner namespace ro-binds at
``/agent/bin/codex``.  It speaks the same JSON-RPC app-server surface over
stdio, spawns exactly the MCP servers the mounted child ``config.toml`` declares
(the real staged ``report_sink_mcp.py`` / ``read_proxy_mcp.py`` bridges against
the real host-side AF_UNIX sinks), and then serves the acceptance turn
deterministically from the serialized packet.

It never creates a network socket: socket creation raises, so no real model or
platform endpoint can be reached from the child process.

Evidence contract: every observation the host test needs is carried in the v3
report fields themselves (``reason`` for the platform role, ``note`` for the
judge role) as ``key=value;`` markers, because the child namespace has no other
writable channel out.  Question text may carry ``[[fixture:directive]]`` /
``[[needs:ontology-id]]`` tokens, which are fixture-authored inputs, never
product behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

V3_REPORT_SCHEMA = "r3-0-011-acceptance-batch-report/v1"
V3_FAILURE_LAYER_RUNTIME = "runtime/infrastructure"
PROMPT_V3_MARKERS = ("batch_id", "question_content_version", "submit_examiner_report")
PROMPT_LEGACY_MARKERS = ("answerability", "evidence_ref_ids", "one bounded terminal report")
# The platform instructions must bind evidence by the host-issued handle and
# never ask the child to transcribe digest/path strings.
PROMPT_HANDLE_MARKERS = ("evidence_handle",)
PROMPT_TRANSCRIPTION_MARKERS = ("request_digest", "response_digest", "artifact_path")

# Proof that no real model/platform generation can happen from this process.
import socket as _socket  # noqa: E402


def _forbid_network_socket(*_args: object, **_kwargs: object) -> "_socket.socket":
    raise AssertionError("fixture app-server attempted to open a socket")


_socket.socket = _forbid_network_socket  # type: ignore[assignment]

SPAWNED: dict[str, dict[str, Any]] = {}
ORIGINAL_PACKET = None
COMPLETED_QUESTIONS = set()
WAIT_DIRECTIVE_USED = False


def _sha16(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def _markers(text: str) -> list[str]:
    return [marker for marker in PROMPT_V3_MARKERS if marker in text]


def _legacy_markers(text: str) -> list[str]:
    return [marker for marker in PROMPT_LEGACY_MARKERS if marker in text]


def _mounted_prompts() -> dict[str, Any]:
    """Read the ACTUAL mounted child prompt/skill bytes inside the namespace."""

    home = Path(os.environ.get("CODEX_HOME", "/agent/home"))
    instructions_path = home / "instructions.md"
    instructions = instructions_path.read_bytes() if instructions_path.is_file() else b""
    skills: dict[str, bytes] = {}
    skills_root = Path("/skills")
    if skills_root.is_dir():
        for skill in sorted(skills_root.glob("*/SKILL.md")):
            skills[skill.parent.name] = skill.read_bytes()
    skill_text = b"\n".join(sorted(skills.values()))
    instructions_text = instructions.decode("utf-8", "replace")
    skill_decoded = skill_text.decode("utf-8", "replace")

    def _joined(markers: tuple[str, ...], *texts: str) -> str:
        return ",".join(
            marker for marker in markers if any(marker in text for text in texts)
        )

    return {
        "instructions_sha16": _sha16(instructions),
        "instructions_bytes": len(instructions),
        "skill_names": ",".join(sorted(skills)),
        "skill_sha16": _sha16(skill_text),
        "prompt_markers": _markers(instructions_text),
        "prompt_legacy_markers": _legacy_markers(instructions_text) + _legacy_markers(skill_decoded),
        "prompt_handle_markers": _joined(PROMPT_HANDLE_MARKERS, instructions_text, skill_decoded),
        "prompt_transcription_markers": _joined(
            PROMPT_TRANSCRIPTION_MARKERS, instructions_text, skill_decoded
        ),
    }


def _spawn_mounted_mcp_servers() -> None:
    """Spawn exactly the MCP servers the mounted child config.toml declares."""

    home = Path(os.environ.get("CODEX_HOME", "/agent/home"))
    config_path = home / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    servers = config.get("mcp_servers") or {}
    for name, entry in sorted(servers.items()):
        command = [str(entry["command"]), *[str(item) for item in entry.get("args", [])]]
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/agent/home"),
            "CODEX_HOME": os.environ.get("CODEX_HOME", "/agent/home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        env.update({str(key): str(value) for key, value in (entry.get("env") or {}).items()})
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        SPAWNED[name] = {"process": process, "command": command, "env_keys": sorted(env), "next_id": 0, "tools": {}}
        _mcp_rpc(name, "initialize", {"protocolVersion": "2025-03-26", "clientInfo": {"name": "fixture-app-server", "version": "1"}})
        _mcp_notify(name, "notifications/initialized")
        listed = _mcp_rpc(name, "tools/list", {})
        tools = listed.get("tools", []) if isinstance(listed, dict) else []
        SPAWNED[name]["tools"] = {
            str(tool.get("name")): tool.get("inputSchema") if isinstance(tool, dict) else None
            for tool in tools
            if isinstance(tool, dict)
        }


def _mcp_rpc(name: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = SPAWNED[name]
    entry["next_id"] += 1
    request_id = entry["next_id"]
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    entry["process"].stdin.write(json.dumps(message) + "\n")
    entry["process"].stdin.flush()
    while True:
        line = entry["process"].stdout.readline()
        if not line:
            raise RuntimeError(f"fixture: MCP server {name} closed its output during {method}")
        value = json.loads(line)
        if isinstance(value, dict) and value.get("id") == request_id:
            if "error" in value:
                raise RuntimeError(f"fixture: MCP {name} {method} error: {value['error']}")
            result = value.get("result")
            return result if isinstance(result, dict) else {}


def _mcp_notify(name: str, method: str, params: dict[str, Any] | None = None) -> None:
    entry = SPAWNED[name]
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    entry["process"].stdin.write(json.dumps(message) + "\n")
    entry["process"].stdin.flush()


def _mcp_call(name: str, tool: str, arguments: dict[str, Any], *, typed: bool = True) -> dict[str, Any]:
    """Call one tool through the real staged bridge and decode its answer.

    ``typed`` keeps the two bridge seams distinct: a platform read must return a
    typed JSON payload (that is the whole point of the read contract), while the
    report sink confirms an accepted submission as plain text with no payload.
    """

    result = _mcp_rpc(name, "tools/call", {"name": tool, "arguments": arguments})
    if result.get("isError"):
        text = "".join(item.get("text", "") for item in result.get("content", []) if isinstance(item, dict))
        return {"ok": False, "error": text}
    payload: Any = result.get("structuredContent")
    if not isinstance(payload, dict):
        for item in result.get("content", []):
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                if not typed:
                    # Accepted submission: the sink answers "report-submitted".
                    return {"ok": True, "payload": {"confirmation": item["text"]}}
                try:
                    payload = json.loads(item["text"])
                except json.JSONDecodeError:
                    continue
                break
    if not isinstance(payload, dict):
        if not typed:
            return {"ok": True, "payload": {}}
        return {"ok": False, "error": "fixture: bridge returned no typed payload"}
    # The read bridge forwards the ScopedReadProxy evidence handle merged into
    # the payload it serializes (not as MCP result envelope fields), so it is
    # read back from the decoded payload.
    return {
        "ok": True,
        "payload": payload,
        "evidence_handle": payload.get("evidence_handle") or "",
    }


def _parse_packet(text: str) -> dict[str, Any]:
    if "TRANSPORT_JSON=" in text:
        start = text.index("TRANSPORT_JSON=") + len("TRANSPORT_JSON=")
        transport, _ = json.JSONDecoder().raw_decode(text, start)
        payload = transport["packet"]
        for entries in payload.get("platform_read_responses", {}).values():
            for entry in entries:
                entry["result"] = transport["result_body_registry"][entry.pop("result_ref")]
        return payload
    key = "PACKET_JSON="
    start = text.index(key) + len(key)
    payload, _ = json.JSONDecoder().raw_decode(text, start)
    return payload


def _directives(text: str) -> list[str]:
    return re.findall(r"\[\[fixture:([a-z0-9-]+)\]\]", text)


def _needs(text: str) -> str | None:
    match = re.search(r"\[\[needs:([A-Za-z0-9._-]+)\]\]", text)
    return match.group(1) if match else None


def _submit_report(tool: str, report: dict[str, Any]) -> dict[str, Any]:
    # The report sink confirms acceptance as text, not as a typed payload.
    outcome = _mcp_call("examiner_report", "submit_examiner_report", report, typed=False)
    outcome["question_id"] = report.get("question_id")
    if not outcome["ok"]:
        # A sink rejection is a fixture/product defect, never a scenario step:
        # surface the returned reason immediately instead of swallowing it and
        # letting the session die as an unexplained deadline.
        sys.stderr.write(
            "fixture: submit rejected for "
            f"{report.get('question_id')}: {outcome.get('error')}\n"
        )
        sys.stderr.flush()
    return outcome


def _platform_turn(payload: dict[str, Any], mounted: dict[str, Any]) -> list[dict[str, Any]]:
    scope = [str(item) for item in payload["authorized_scope"]]
    tools = sorted(SPAWNED.get("platform_read_proxy", {}).get("tools", {}))
    schema_flags = ",".join(
        f"{tool}:{int(bool((SPAWNED['platform_read_proxy']['tools'].get(tool) or {}).get('properties')))}"
        for tool in tools
    )
    # One authorized multi-Ontology read, a second-only selection and a subset
    # that excludes the primary entry, all through the same real
    # bridge/proxy/forwarder chain.  No legacy singleton scope fields are
    # supplied by the child: the proxy owns the per-entry binding.
    reads: list[dict[str, Any]] = []
    facts: dict[str, str] = {}
    for label, ontology_ids in (
        ("multi", scope),
        ("second", scope[-1:]),
        ("subset", scope[1:]),
    ):
        outcome = _mcp_call(
            "platform_read_proxy",
            "query_semantic_context",
            {"scope_mode": "ontologies", "ontology_ids": ontology_ids, "query": "entitlement"},
        )
        if outcome["ok"]:
            for result in outcome["payload"].get("results", []):
                for match in result.get("matches", []):
                    facts[str(result["ontology_id"])] = str(match["text"])
        reads.append(
            {
                "label": label,
                "ontology_ids": "+".join(ontology_ids),
                "ok": int(bool(outcome["ok"])),
                "error": "" if outcome["ok"] else str(outcome.get("error"))[:120].replace(";", ","),
                "evidence_handle": outcome.get("evidence_handle") or "",
                # The child must never see digest/path strings to transcribe.
                "digest_leak": int(any(
                    key in outcome["payload"] for key in ("request_digest", "response_digest", "artifact_path")
                )),
                "tool": "query_semantic_context",
            }
        )

    submitted: list[dict[str, Any]] = []
    for question in payload["questions"]:
        question_id = str(question["question_id"])
        if question_id in COMPLETED_QUESTIONS:
            continue
        needed = _needs(str(question["question"])) or scope[0]
        fact = facts.get(needed)
        read = next((item for item in reads if needed in item["ontology_ids"].split("+") and item["ok"]), None)
        evidence = [read["evidence_handle"]] if read else []
        read_marks = []
        for item in reads:
            mark = f"{item['label']}:{item['ontology_ids']}:{item['ok']}"
            if item["error"]:
                mark += "!" + item["error"]
            if item["digest_leak"]:
                mark += "!digest-leak"
            if not item["evidence_handle"]:
                mark += "!no-handle"
            read_marks.append(mark)
        marker = (
            f"fixture:appserver=controlled-codex;role=platform;"
            f"instructions={mounted['instructions_sha16']};skill={mounted['skill_sha16']};"
            f"skill_names={mounted['skill_names']};"
            f"prompt_markers={','.join(mounted['prompt_markers'])};"
            f"prompt_legacy_markers={','.join(mounted['prompt_legacy_markers'])};"
            f"prompt_handle_markers={mounted['prompt_handle_markers']};"
            f"prompt_transcription_markers={mounted['prompt_transcription_markers']};"
            f"schemas={schema_flags};"
            f"reads={','.join(read_marks)};"
            f"packet_blind={int('answer_points' not in payload and 'evidence_bundle' not in payload)};"
            f"spawned={'+'.join(sorted(SPAWNED))}"
        )
        report = {
            "schema_version": V3_REPORT_SCHEMA,
            "batch_id": str(payload["batch_id"]),
            "question_id": question_id,
            "question_content_version": int(question["content_version"]),
            "answer": f"{question_id}: {fact}" if fact else f"{question_id}: platform read unavailable",
            "evidence_refs": evidence,
            "explicit_unknown": [] if fact else ["platform read unavailable"],
            "status": "completed" if fact else "runtime-incomplete",
            "failure_layer": None if fact else V3_FAILURE_LAYER_RUNTIME,
            "reason": marker,
        }
        submitted.append(_submit_report("submit_examiner_report", report))
        COMPLETED_QUESTIONS.add(question_id)
        global WAIT_DIRECTIVE_USED
        directive = "wait-judge-control" if "evidence_bundle" in payload else "wait-consumer-control"
        if directive in _directives(str(question["question"])) and not WAIT_DIRECTIVE_USED:
            WAIT_DIRECTIVE_USED = True
            break
        if "exit-after-first-report" in _directives(str(question["question"])):
            # T-G4-7: die mid-batch after one accepted report, like a crashed child.
            sys.stdout.flush()
            os._exit(9)
    return submitted


def _judge_turn(payload: dict[str, Any], mounted: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("evidence_bundle", {}).get("entries", [])
    examiner = {str(item.get("question_id")): item for item in payload.get("examiner_reports", [])}
    submitted: list[dict[str, Any]] = []
    for question in payload["questions"]:
        question_id = str(question["question_id"])
        if question_id in COMPLETED_QUESTIONS:
            continue
        question_entries = [entry for entry in entries if str(entry.get("question_id")) == question_id]
        evidence = ",".join(
            f"{Path(str(entry.get('source'))).name}:{str(entry.get('content_digest'))[7:19]}"
            for entry in question_entries
        )
        basis = ""
        references = []
        for entry in question_entries:
            content = entry.get("content", "")
            if "reference_id" in entry:
                read = _mcp_call("examiner_report", "read_frozen_evidence", {
                    "run_id": payload["run_id"], "batch_id": payload["batch_id"],
                    "freeze_digest": payload["freeze_digest"], "reference_id": entry["reference_id"],
                })
                if not read["ok"]:
                    raise RuntimeError("fixture frozen source read failed: " + str(read))
                content = read["payload"]["content"]
                references.append(entry["reference_id"])
            match = re.search(r"basis:([a-f0-9]{12})", str(content))
            if match:
                basis = match.group(1)
        answer = str(examiner.get(question_id, {}).get("answer", ""))
        points_covered = all(point in answer for point in question.get("answer_points", []) if point)
        # v3 verdict states are pass / model-recall-insufficient /
        # question-answer-review / platform-runtime-incomplete; a recall gap
        # names its modeling-quality layer and a pass keeps the layer empty.
        verdict = "pass" if basis and points_covered else "model-recall-insufficient"
        note = (
            f"fixture:appserver=controlled-codex;role=acceptance;"
            f"instructions={mounted['instructions_sha16']};skill={mounted['skill_sha16']};"
            f"skill_names={mounted['skill_names']};"
            f"prompt_markers={','.join(mounted['prompt_markers'])};"
            f"prompt_legacy_markers={','.join(mounted['prompt_legacy_markers'])};"
            f"evidence={evidence};basis={basis};examiner_reports={len(examiner)};"
            f"source_references={','.join(references)};"
            f"spawned={'+'.join(sorted(SPAWNED))}"
        )
        report = {
            "schema_version": V3_REPORT_SCHEMA,
            "batch_id": str(payload["batch_id"]),
            "question_id": question_id,
            "verdict": verdict,
            "failure_layer": None if verdict == "pass" else "modeling-quality",
            "conflicting_evidence": [],
            "note": note,
        }
        submitted.append(_submit_report("submit_examiner_report", report))
        COMPLETED_QUESTIONS.add(question_id)
        global WAIT_DIRECTIVE_USED
        directive = "wait-judge-control" if "evidence_bundle" in payload else "wait-consumer-control"
        if directive in _directives(str(question["question"])) and not WAIT_DIRECTIVE_USED:
            WAIT_DIRECTIVE_USED = True
            break
    return submitted


def _serve_turn(text: str) -> dict[str, Any]:
    mounted = _mounted_prompts()
    global ORIGINAL_PACKET
    if "PACKET_JSON=" not in text and "TRANSPORT_JSON=" not in text:
        outer = json.loads(text)
        control = json.loads(outer["text"])
        action = control["action"]
        if action in {"pause", "resume"}:
            acknowledgement = {"request_id": control["request_id"], "action": action}
            if len(COMPLETED_QUESTIONS) == len(ORIGINAL_PACKET["questions"]):
                return {"flow_confirmation": acknowledgement, "text": "original retained Consumer"}
            result = _mcp_call("examiner_report", "record_flow_confirmation", acknowledgement, typed=False)
            if not result["ok"]:
                raise RuntimeError("fixture flow acknowledgement failed: " + str(result))
            if action == "pause":
                return {"waiting": True, "remaining_questions": [q["question_id"] for q in ORIGINAL_PACKET["questions"] if q["question_id"] not in COMPLETED_QUESTIONS]}
        elif action == "consult":
            return {"text": "scoped read-only reply on the original Consumer thread", "completed_questions": sorted(COMPLETED_QUESTIONS)}
        payload = ORIGINAL_PACKET
    else:
        payload = _parse_packet(text)
        ORIGINAL_PACKET = payload
    is_judge = "evidence_bundle" in payload
    submitted = _judge_turn(payload, mounted) if is_judge else _platform_turn(payload, mounted)
    rejected = [item for item in submitted if not item["ok"]]
    if rejected:
        # Fail the turn here rather than reporting a batch that never landed:
        # the controlled child dies loudly with the sink's own rejection text.
        raise RuntimeError(
            "fixture: report sink rejected "
            f"{len(rejected)}/{len(submitted)} submission(s): {json.dumps(rejected)}"
        )
    return {
        "role": "acceptance" if is_judge else "platform-examiner",
        "submitted": [
            {"question_id": item["question_id"], "ok": int(bool(item["ok"])), "error": "" if item["ok"] else str(item.get("error"))[:120]}
            for item in submitted
        ],
    }


def main() -> int:
    _spawn_mounted_mcp_servers()
    thread_id = "thr-fixture-acceptance"
    turn_number = 0
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "serverInfo": {"name": "controlled-codex-app-server", "version": "1"},
            }
        elif method == "thread/start":
            result = {"thread": {"id": thread_id}}
        elif method == "mcpServerStatus/list":
            result = {
                "data": [
                    {"name": name, "tools": [{"name": tool} for tool in sorted(entry["tools"])]}
                    for name, entry in sorted(SPAWNED.items())
                ]
            }
        elif method == "turn/start":
            turn_number += 1
            turn_id = "turn-fixture-" + str(turn_number)
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": turn_id}}})
                + "\n"
            )
            sys.stdout.flush()
            text = ""
            for item in params.get("input", []):
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text += item["text"]
            summary = _serve_turn(text)
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "thread/tokenUsage/updated", "params": {"threadId": thread_id, "turnId": turn_id, "tokenUsage": {"total": {"inputTokens": turn_number * 100, "outputTokens": turn_number * 20}}}}) + "\n")
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": "message-" + turn_id, "type": "agentMessage", "text": json.dumps(summary)}}}) + "\n")
            for method_name in ("turn/completed", "turn/finished"):
                sys.stdout.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": method_name,
                            "params": {"threadId": thread_id, "turnId": turn_id},
                        }
                    )
                    + "\n"
                )
            sys.stdout.flush()
            continue
        else:
            if request_id is None:
                continue
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"fixture: {method} unsupported"},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        sys.stdout.flush()
    for entry in SPAWNED.values():
        try:
            entry["process"].stdin.close()
            entry["process"].wait(timeout=5)
        except Exception:
            entry["process"].kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
