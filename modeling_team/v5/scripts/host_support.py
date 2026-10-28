"""Host-owned GLM routing and raw observations; no amount gate or second cost ledger."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from modeling_team.close_statistics import ActivityRecorder
from modeling_team.deepseek_provider_proxy import (
    GLM_UPSTREAM_URL,
    ResponsesProviderSession,
    preflight_glm_credential,
    read_glm_credential,
)
from modeling_team.usage_capture import NumericReceiptWriter

from ontoweave_modeling.codex_agent import CodexAgent, outbound_tool_names
from ontoweave_modeling.preflight import ModelBinding
from ontoweave_modeling.results import ResultContractError, decode_json_result

TASK_REF = "v5-codex-p0-20261028"
AUTHORIZATION_REF = "user-2026-10-28-continue-client-json-usage-only"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ObservedProvider(ResponsesProviderSession):
    def __init__(
        self,
        *args,
        evidence: Path,
        allowed_tools: tuple[str, ...],
        stream_fault: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.evidence = evidence
        self.allowed_tools = set(allowed_tools) | {
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
        }
        self.stream_fault = stream_fault

    def admit_attempt(self, receipt: dict, *, request: dict | None = None) -> bool:
        request = request or {}
        with self.evidence.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(request, ensure_ascii=False) + "\n")
        allowed = not (set(outbound_tool_names(request.get("tools", []))) - self.allowed_tools)
        allowed = allowed and request.get("model") == "glm-5.3-flash"
        allowed = allowed and (request.get("reasoning") or {}).get("effort") == "low"
        if not allowed:
            self.record_attempt({**receipt, "event": "attempt_end", "status": "not_admitted"})
            return False
        return super().admit_attempt(receipt, request=request)

    def forward(self, body: bytes):
        status, headers, response = super().forward(body)
        if self.stream_fault and status == 200:
            self.stream_fault = False
            response = StreamFault(response)
        return status, headers, response


class StreamFault:
    """A controlled client-stream failure after an actual upstream response."""

    def __init__(self, response):
        self.response = response
        self.sent = False

    def read(self, size: int = -1) -> bytes:
        if self.sent:
            return b""
        self.sent = True
        self.response.close()
        return b'event: error\ndata: {"type":"error","error":{"type":"server_error","code":"p0_injected_stream_failure","message":"P0 controlled stream failure"}}\n\n'

    def close(self):
        self.response.close()

    def __iter__(self):
        return iter(self.read().splitlines(keepends=True))


class HostAgent:
    def __init__(
        self,
        root: Path,
        *,
        materials: Path,
        instructions: str,
        role: str = "modeling",
        native_root: Path | None = None,
        resume: bool = False,
        allowed_tools: tuple[str, ...] = ("read_material",),
        workspace_config: Path | None = None,
        platform_config: Path | None = None,
        config_overrides: dict | None = None,
        stream_fault: bool = False,
        on_event=None,
    ):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        binding = ModelBinding.from_profile(
            ROOT / "modeling_team/model-profiles/glm-flash-low.yaml", role
        )
        credential = preflight_glm_credential()
        context = {
            "task_ref": TASK_REF,
            "run_id": self.root.name,
            "agent_id": self.root.name,
            "role": role,
            "phase": "P0",
            "provider": binding.provider,
            "requested_model": binding.model,
            "actual_model": binding.model,
            "requested_effort": binding.effort,
            "effective_effort": binding.effort,
            "key_ref": credential.key_ref,
            "runtime": "codex",
            "session_id": uuid.uuid4().hex,
            "process_instance": uuid.uuid4().hex,
        }
        self.activity = ActivityRecorder(self.root, context)
        self.usage = NumericReceiptWriter(self.root / "usage.jsonl", context)
        provider_usage = NumericReceiptWriter(self.root / "provider-attempts.jsonl", context)
        self.provider = ObservedProvider(
            read_glm_credential(credential),
            provider_id=binding.provider,
            upstream_url=GLM_UPSTREAM_URL,
            on_attempt=provider_usage,
            max_upstream_attempts=1,
            evidence=self.root / "outbound.jsonl",
            allowed_tools=tuple("mcp__workspace__" + tool for tool in allowed_tools),
            stream_fault=stream_fault,
        )
        self.provider.start()
        self.starts, self.ends = set(), set()
        self.external_event = on_event
        self.agent = CodexAgent(
            native_root or self.root / "agent",
            binding,
            provider_base_url=self.provider.base_url,
            materials=materials,
            instructions=instructions,
            on_event=self.on_event,
            allowed_tools=allowed_tools,
            workspace_config=workspace_config,
            platform_config=platform_config,
            config_overrides=config_overrides,
        )
        self.resume = resume
        self.calls = 0

    def on_event(self, method: str, params: dict) -> None:
        if method in {"thread/start", "thread/resume"}:
            self.activity.bind(params["thread"]["id"])
            self.usage.context.update(self.activity.context)
        elif method == "thread/tokenUsage/updated":
            self.usage(
                {
                    "event": "thread_usage",
                    "thread_id": params["threadId"],
                    "turn_id": params["turnId"],
                    "runtime_session_id": params["threadId"],
                    "total": params["tokenUsage"]["total"],
                }
            )
        elif method in {"turn/started", "turn/completed"}:
            turn_id = params["turn"]["id"]
            seen = self.starts if method == "turn/started" else self.ends
            if turn_id not in seen:
                seen.add(turn_id)
                self.activity.emit(
                    "llm_start" if method == "turn/started" else "llm_end",
                    call_id=f"{params['threadId']}:{turn_id}",
                    turn_id=turn_id,
                    status=params["turn"].get("status"),
                )
        if self.external_event:
            self.external_event(method, params)

    def start(self):
        identity = self.agent.start(resume=self.resume)
        write_json(
            self.root / "execution-binding.json",
            {
                "task_ref": TASK_REF,
                "authorization_ref": AUTHORIZATION_REF,
                "resource_policy": "usage_only",
                "execution_attempt": self.root.name,
                "native_thread_id": self.agent.thread_id,
                "resume": self.resume,
                "model": identity["model"],
                "provider": identity["modelProvider"],
                "effort": identity["reasoningEffort"],
            },
        )
        return self

    def turn(self, prompt: str, schema: dict) -> dict:
        self.calls += 1
        result = self.agent.run_turn(prompt)
        if result["status"] == "completed":
            try:
                result["structured_result"] = decode_json_result(result["final_response"], schema)
                result["result_contract"] = {"status": "valid"}
            except ResultContractError as exc:
                result["result_contract"] = {
                    "status": "needs_correction",
                    "code": str(exc),
                    "recoverable": True,
                }
        write_json(self.root / f"turn-{self.calls:03d}.json", result)
        return result

    def close(self):
        self.agent.close()
        self.provider.stop()
        self.activity.exit(0)
