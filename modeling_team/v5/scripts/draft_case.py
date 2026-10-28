"""Produce a source-grounded, generic definition plan with a real bounded Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from host_support import ROOT, HostAgent, write_json
from integration_cases import json_turn, materials, source

SEMANTIC = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "semantic_role": {"type": "string"},
        "business_meaning": {"type": "string"},
        "applicability": {"type": "string"},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "not_applicable": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["business_meaning", "applicability", "unknowns", "not_applicable"],
}
BASE = {
    "key": {"type": "string"},
    "name": {"type": "string"},
    "description": {"type": "string"},
    "semantic_definition": SEMANTIC,
    "source_refs": {"type": "array", "items": {"type": "string"}},
}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": BASE,
                "required": list(BASE),
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    **BASE,
                    "source_key": {"type": "string"},
                    "target_key": {"type": "string"},
                },
                "required": [*BASE, "source_key", "target_key"],
            },
        },
        "explicit_unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["concepts", "relationships", "explicit_unknowns"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    method_path = ROOT / "modeling_team/references/platform-neutral-candidate-authoring.json"
    method = json.loads(method_path.read_text())["multiview_semantic_definition"]
    public = materials(
        root / "materials",
        {
            "scenario": source(),
            "definition-contract": (
                json.dumps(method, ensure_ascii=False),
                str(method_path.relative_to(ROOT)),
            ),
        },
    )
    actor = HostAgent(
        root / "production",
        materials=public,
        instructions="Model only the authorized source. Preserve complete business meaning, scope, "
        "negative statements and unknowns. Never invent instances or platform identities.",
    )
    try:
        actor.start()
        result = json_turn(
            actor,
            "Read scenario and definition-contract through tools. Prepare the complete source-grounded "
            "definition plan: concepts will become Class definitions, relationships RelationType definitions. "
            "Choose local neutral keys; relation endpoints reference those keys. "
            "The host compiler binds actual resource identities from receipts. Keep unsupported details "
            "explicitly unknown and source references exact. This is a small definition-only model; "
            "do not create named business instances or any other scope.",
            SCHEMA,
        )
        assert result["status"] == "completed" and "structured_result" in result
        write_json(root / "definition-plan.json", result["structured_result"])
        print(
            json.dumps(
                {
                    "status": "drafted",
                    "native_thread": result["thread_id"],
                    "semantic_acceptance": "unverified",
                }
            )
        )
    finally:
        actor.close()


if __name__ == "__main__":
    main()
