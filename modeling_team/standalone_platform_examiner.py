"""Drive one real Platform Examiner child with a chosen prompt variant.

Lets the prompt be iterated quickly without running the full N=2 operation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from modeling_team.contracts import repository_root
from modeling_team.acceptance_runtime import (
    AcceptanceBatchPacket,
    CQ_ACCEPTANCE_BRANCH_V3,
    ExaminerRunMetrics,
    acceptance_branch_for,
    build_platform_examiner_packet,
    examiner_proxy_schemas,
)
from modeling_team.r23006_acceptance_operation import (
    prepare_r23006_operation,
    EXPECTED_SCOPE,
)
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.report_sink_mcp import report_schema as sink_report_schema


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="Which output is consumed?")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--v3-packet",
        type=Path,
        help=(
            "R3.0-011: load a v3 hidden-batch packet JSON, verify the explicit v3 "
            "dispatch and print its digest instead of running the legacy probe"
        ),
    )
    args = parser.parse_args()

    if args.v3_packet is not None:
        # R3.0-011 v3 branch: explicit dispatch on the packet schema version.  A
        # legacy ExaminerRolePacket/v1 file is rejected here rather than being
        # re-labelled, and no child is launched by this offline helper.
        payload = json.loads(args.v3_packet.read_text(encoding="utf-8"))
        role = str(payload.get("role", ""))
        packet = AcceptanceBatchPacket.build(role, dict(payload.get("payload", {})))
        branch = acceptance_branch_for(packet.schema_version)
        if branch != CQ_ACCEPTANCE_BRANCH_V3:
            print(f"v3 packet rejected: branch {branch}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "schema_version": packet.schema_version,
                    "role": packet.role,
                    "batch_id": packet.batch_id,
                    "freeze_digest": packet.freeze_digest,
                    "canonical_digest": packet.canonical_digest,
                    "branch": branch,
                }
            )
        )
        return 0

    root = repository_root()
    prepared = prepare_r23006_operation(root)
    adapter = CodexRuntimeAdapter(repository_root=root, use_bwrap=False)

    scope = dict(EXPECTED_SCOPE)
    payload = {
        "question": args.question,
        "ordinal": 1,
        "count": 2,
        "ticket_binding": {"ticket_digest": prepared.ticket["ticket_digest"]},
        "model_state": {"model_revision": scope["model_revision"], "state_digest": "0" * 64},
        "platform_read_scope": {
            "project_id": scope["project_id"],
            "ontology_id": scope["ontology_id"],
        },
        "proxy_capability": {"capability_id": "standalone-probe"},
        "allowed_read_tools": list(prepared.allowed_tools),
        "request_schema": {"tools": examiner_proxy_schemas(prepared.allowed_tools)},
        "report_schema": sink_report_schema("platform"),
    }
    packet = build_platform_examiner_packet(**payload)
    metrics = ExaminerRunMetrics("platform", max_inference_steps=10)
    metrics.bind_first_turn_input(
        [{"type": "packet", "digest": packet.canonical_digest}], packet=packet
    )
    print(f"tools: {prepared.allowed_tools}")
    print(f"launching platform examiner (timeout {args.timeout}s) ...")
    report = adapter.run_lean_examiner_child(
        packet,
        metrics,
        read_key="unused-standalone",
        platform_forwarder=lambda _tool, _arguments, _key: {},
        timeout_seconds=args.timeout,
    )
    print("REPORT SUBMITTED:")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
