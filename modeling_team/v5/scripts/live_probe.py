"""P0 real SDK/MCP probe, reusing the Host's existing provider and budget ledger."""

from __future__ import annotations

import argparse
import hashlib
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
from modeling_team.runtimes.budget import runtime_budget
from modeling_team.task_budget import TaskBudget
from modeling_team.usage_capture import NumericReceiptWriter

from ontoweave_modeling.codex_agent import CodexAgent, outbound_tool_names
from ontoweave_modeling.preflight import ModelBinding
from ontoweave_modeling.results import (
    MATERIAL_RESULT_SCHEMA,
    ResultContractError,
    decode_json_result,
)


def append_json(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


class ObservedProvider(ResponsesProviderSession):
    def __init__(self, *args, evidence: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence = evidence

    def admit_attempt(self, receipt: dict, *, request: dict | None = None) -> bool:
        request = request or {}
        append_json(self.evidence, request)
        names = outbound_tool_names(request.get("tools", []))
        allowed = {
            "mcp__workspace__read_material",
            # These helpers read only the same configured MCP server, whose
            # resource/resource-template inventories are empty in this probe.
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
        }
        permitted = not (set(names) - allowed) and not (
            request.get("model") != "glm-5.3-flash"
            or (request.get("reasoning") or {}).get("effort") != "low"
        )
        if not permitted:
            self.record_attempt({**receipt, "event": "attempt_end", "status": "not_admitted"})
            return False
        return super().admit_attempt(receipt, request=request)


def run(root: Path, budget_ref: Path, *, plain_output: bool = False) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_ref = "docs/evaluation-scenarios/minimal-installation-chain/modeling-input/scenario.md"
    source = (ROOT / source_ref).read_bytes()
    materials = root / "materials"
    materials.mkdir(mode=0o700)
    (materials / "scenario.md").write_bytes(source)
    (materials / "manifest.json").write_text(
        json.dumps(
            {
                "scenario": {
                    "path": "scenario.md",
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "source_ref": source_ref,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    binding = ModelBinding.from_profile(
        ROOT / "modeling_team/model-profiles/glm-flash-low.yaml", "modeling"
    )
    budget = TaskBudget(budget_ref)
    credential = preflight_glm_credential()
    owner_id = root.name
    context = {
        "task_ref": "v5-codex-p0-20261028",
        "run_id": owner_id,
        "agent_id": owner_id,
        "role": "modeling",
        "phase": "P0-V1",
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
    usage_path, proxy_path = root / "usage.jsonl", root / "provider-attempts.jsonl"
    usage = NumericReceiptWriter(usage_path, context)
    proxy_usage = NumericReceiptWriter(proxy_path, context)
    member = runtime_budget(
        root, owner_id, binding=context, runtime="codex", explicit=budget, role="modeling"
    )
    member.register_source(usage_path, "capture")
    member.register_source(
        proxy_path, "capture", shared=True, capture_session_id=context["session_id"]
    )
    activity = ActivityRecorder(
        root,
        context,
        fresh_session=True,
        budget=budget,
        budget_owner_id=owner_id,
        budget_binding=context,
        budget_runtime="codex",
        usage_sources=[
            {"path": usage_path, "kind": "capture"},
            {
                "path": proxy_path,
                "kind": "capture",
                "shared": True,
                "capture_session_id": context["session_id"],
            },
        ],
    )
    usage.context.update(activity.context)
    seen_starts, seen_ends = set(), set()

    def on_event(method: str, params: dict) -> None:
        if method == "thread/start":
            activity.bind(params["thread"]["id"])
            usage.context.update(activity.context)
        elif method == "thread/tokenUsage/updated":
            usage(
                {
                    "event": "thread_usage",
                    "thread_id": params["threadId"],
                    "runtime_session_id": params["threadId"],
                    "turn_id": params["turnId"],
                    "total": params["tokenUsage"]["total"],
                }
            )
        elif method == "turn/started":
            turn_id = params["turn"]["id"]
            if turn_id not in seen_starts:
                seen_starts.add(turn_id)
                activity.emit(
                    "llm_start", call_id=f"{params['threadId']}:{turn_id}", turn_id=turn_id
                )
        elif method == "turn/completed":
            turn_id = params["turn"]["id"]
            if turn_id not in seen_ends:
                seen_ends.add(turn_id)
                activity.emit(
                    "llm_end",
                    call_id=f"{params['threadId']}:{turn_id}",
                    turn_id=turn_id,
                    status=params["turn"]["status"],
                )

    provider = ObservedProvider(
        read_glm_credential(credential),
        provider_id=binding.provider,
        upstream_url=GLM_UPSTREAM_URL,
        on_attempt=proxy_usage,
        max_upstream_attempts=1,
        evidence=root / "outbound.jsonl",
    )
    provider.start()
    agent = CodexAgent(
        root / "agent",
        binding,
        provider_base_url=provider.base_url,
        materials=materials,
        instructions=(
            "You are a bounded semantic modeling assistant. Use only the authorized material MCP. "
            "Preserve source conditions, exceptions, negation and unknowns; do not invent business facts. "
            "This task prepares source propositions; it does not apply an ontology or prove acceptance."
        ),
        on_event=on_event,
    )
    monitor = budget.monitor(interval=2)
    result = None
    try:
        identity = agent.start()
        (root / "execution-binding.json").write_text(
            json.dumps(
                {
                    "task_ref": context["task_ref"],
                    "budget_ref": str(budget.ref),
                    "work_unit": "P0-V1",
                    "execution_attempt": owner_id,
                    "codex_thread": identity["thread"]["id"],
                    "model_binding": {
                        "provider": binding.provider,
                        "model": binding.model,
                        "effort": binding.effort,
                    },
                    "source_sha256": hashlib.sha256(source).hexdigest(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        budget.tick()
        budget.require_available(operation="production", binding=context)
        result = agent.run_turn(
            "本次是 P0 工具集成验证。先调用 read_material，使用 material_id=missing，"
            "观察类型化错误，再依据工具反馈读取获准的 scenario 材料；需要时分页补读。"
            "阅读后列出完整业务命题、关键条件及明确未知，每条保留来源引用。"
            "不要应用本体，不要读取隐藏题或其他文件。最后返回 JSON，字段 propositions、unknowns、"
            "source_refs 均为字符串数组。",
            output_schema=None if plain_output else MATERIAL_RESULT_SCHEMA,
        )
        try:
            result["structured_result"] = decode_json_result(
                result["final_response"],
                MATERIAL_RESULT_SCHEMA,
            )
            result["result_contract"] = {"status": "valid", "semantic_acceptance": "unverified"}
        except ResultContractError as exc:
            result["result_contract"] = {
                "status": "needs_correction",
                "code": str(exc),
                "recoverable": True,
                "semantic_acceptance": "unverified",
            }
        (root / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    finally:
        agent.close()
        provider.stop()
        activity.exit(0 if result and result["status"] == "completed" else 1)
        state = budget.tick()
        (root / "budget-after.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        monitor.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-ref", type=Path, required=True)
    parser.add_argument("--plain-output", action="store_true")
    args = parser.parse_args()
    result = run(args.output_dir, args.budget_ref, plain_output=args.plain_output)
    print(
        json.dumps(
            {
                "thread_id": result["thread_id"],
                "turn_id": result["turn_id"],
                "native_status": result["status"],
                "error": result["error"],
                "result_contract": result["result_contract"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
