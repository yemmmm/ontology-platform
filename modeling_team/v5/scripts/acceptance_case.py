"""Independent read-only P0 handoff of a frozen actual platform target."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from host_support import HostAgent, write_json
from integration_cases import json_turn, materials, source

from ontoweave_modeling.results import ResultContractError, validate_evaluation_binding

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["PASS", "REVISE", "PARTIAL"]},
        "target_revision": {"type": "integer"},
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "passed": {"type": "boolean"},
                    "actual_answer": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence_iris": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "passed", "actual_answer", "reason", "evidence_iris"],
            },
        },
    },
    "required": ["verdict", "target_revision", "cases"],
}


def verify_required_reads(events_path: Path) -> None:
    completed = set()
    platform_read = False
    for line in events_path.read_text().splitlines():
        event = json.loads(line)
        item = event.get("params", {}).get("item", {})
        if event["method"] != "item/completed" or item.get("status") != "completed":
            continue
        if item.get("tool") == "read_material":
            completed.add(item.get("arguments", {}).get("material_id"))
        platform_read |= item.get("tool") == "query_semantic_context"
    missing = {"scenario", "frozen-questions", "target"} - completed
    if missing or not platform_read:
        raise ResultContractError(
            "evaluation_required_reads_missing: "
            + ",".join(sorted(missing))
            + ("; actual_platform_read" if not platform_read else "")
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--platform-dir", type=Path, required=True)
    parser.add_argument("--frozen-questions", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    platform = args.platform_dir.resolve()
    target = platform / "public-target.json"
    target_revision = json.loads(target.read_text())["modeling_context"]["data"]["workspace"][
        "model_revision"
    ]
    case_count = len(json.loads(args.frozen_questions.read_text())["cases"])
    platform_scope = json.loads((platform / "acceptance-private.json").read_text())
    platform_scope["model_revisions"] = {
        json.loads(target.read_text())["ontology_id"]: target_revision
    }
    bound_config = root / "target-read-private.json"
    write_json(bound_config, platform_scope)
    bound_config.chmod(0o600)
    public_and_private = materials(
        root / "materials",
        {
            "scenario": source(),
            "frozen-questions": (args.frozen_questions.read_text(), "private-frozen-question-set"),
            "target": (target.read_text(), "frozen-platform-target"),
        },
    )
    write_json(
        root / "handoff-binding.json",
        {
            "target_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "questions_sha256": hashlib.sha256(args.frozen_questions.read_bytes()).hexdigest(),
            "input_authority": "original source + independently prepared frozen questions + actual governed reads",
            "production_thread_inherited": False,
        },
    )
    actor = HostAgent(
        root / "independent-evaluation",
        role="acceptance",
        materials=public_and_private,
        platform_config=bound_config,
        allowed_tools=("read_material", "query_semantic_context"),
        instructions="You are an independent read-only evaluator. Never create, resume, repair, or "
        "modify production work. Do not use a producer candidate or its self-evaluation "
        "as model evidence. Read every frozen case and original source; query the actual "
        "platform for supported answers. Preserve missing evidence as PARTIAL/REVISE. "
        "Use the MCP read_material tool, not MCP resource discovery, to obtain scenario, frozen-questions "
        "and target by material_id. query_semantic_context reads the platform model only. "
        "Report privately; do not expose questions, expected answers or private diagnostics "
        "to production. Return one result covering every frozen case.",
    )
    try:
        actor.start()
        result = json_turn(
            actor,
            'Call read_material(material_id="scenario"), read_material(material_id="frozen-questions") '
            'and read_material(material_id="target") to obtain the required inputs. Evaluate every frozen '
            "case against actual query_semantic_context results in the target scope. "
            "Verify the actual model revision matches the target. Read more pages when "
            "required by completeness. Cite actual returned resource IRIs for the judgments. "
            "An unknown is legitimate when the original source does not define it; "
            "a source fact missing from the actual model is not supplied by source alone. "
            f"Use unique indices 1 through {case_count}, and target_revision={target_revision}.",
            SCHEMA,
        )
        assert result["status"] == "completed" and "structured_result" in result
        report = result["structured_result"]
        try:
            verify_required_reads(actor.agent.root / "events.jsonl")
            validate_evaluation_binding(
                report, case_count=case_count, target_revision=target_revision
            )
        except ResultContractError as error:
            write_json(
                root / "report-contract-error.json", {"code": str(error), "recoverable": True}
            )
            correction = json_turn(
                actor,
                f'Correct the report/input contract: {error}. Use MCP read_material(material_id="scenario"), '
                'read_material(material_id="frozen-questions") and read_material(material_id="target"). '
                f"Cover exactly indices 1 through {case_count} "
                f"once each and use target_revision={target_revision}. Preserve your source-based "
                "judgments; do not repair the model or invent evidence.",
                SCHEMA,
            )
            assert correction["status"] == "completed" and "structured_result" in correction
            report = correction["structured_result"]
            verify_required_reads(actor.agent.root / "events.jsonl")
            validate_evaluation_binding(
                report, case_count=case_count, target_revision=target_revision
            )
        write_json(root / "private-report.json", report)
        write_json(
            root / "public-feedback.json",
            {
                "verdict": report["verdict"],
                "target_revision": report["target_revision"],
                "passed": sum(case["passed"] for case in report["cases"]),
                "total": len(report["cases"]),
                "scope": "P0 representative handoff only; not P1 or complete v5 acceptance",
            },
        )
        print((root / "public-feedback.json").read_text())
    finally:
        actor.close()


if __name__ == "__main__":
    main()
