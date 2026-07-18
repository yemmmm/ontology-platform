#!/usr/bin/env python3
"""Repository-portable structural validation for ontology-builder."""

from __future__ import annotations

import json
import re
from pathlib import Path


EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
SKILL_FILE = SKILL_DIR / "SKILL.md"
MODEL_HANDOFF_SCHEMA = SKILL_DIR / "references" / "modeler-handoff.schema.json"
TOOL_REFERENCE = re.compile(r"`mcp:([a-z][a-z0-9_]*)`")
RESOURCE_REFERENCE = re.compile(r"(?:`|\()(references/[a-z0-9_.-]+\.(?:md|json))(?:`|\))")
STALE_TOOLS = {
    "get_evidence_artifact_status",
    "get_evidence_artifact_chunks",
    "validate_proposal",
    "create_data_source",
    "create_semantic_mapping",
    "run_connector_query",
    "submit_proposal_json",
}

MODEL_HANDOFF_FIELDS = {
    "vertical_slice_rationale",
    "modeling_draft",
    "modeling_batch",
    "coverage_updates",
    "assumptions",
    "excluded_items",
    "handoff_summary",
}
MODELING_BATCH_FIELDS = {
    "client_batch_id",
    "ontology_id",
    "idempotency_key",
    "mode",
    "expected_workspace_version",
    "items",
}
ITEM_PAYLOADS = {
    "CreateClassItem": ("create_class", {"#/$defs/CreateClassPayload"}),
    "CreatePropertyItem": (
        "create_property",
        {
            "#/$defs/CreateDatatypePropertyPayload",
            "#/$defs/CreateObjectPropertyPayload",
        },
    ),
    "CreateRelationTypeItem": (
        "create_relation_type",
        {"#/$defs/CreateRelationTypePayload"},
    ),
    "CreateOperationItem": ("create_operation", {"#/$defs/CreateOperationPayload"}),
}
FORBIDDEN_MODEL_FIELDS = {
    "actor",
    "created_by",
    "credential_id",
    "credential_ref",
    "credential_reference_id",
    "graph_iri",
    "graph_set_id",
    "lease_token",
    "operation_iri",
    "shape_graph_iris",
    "target_graph_iri",
}
FORBIDDEN_SECRET_FIELDS = {
    "access_token",
    "api_key",
    "authorization",
    "header_value",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        _, raw, _ = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    values: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def validate_model_handoff_schema(schema: dict[str, object]) -> list[str]:
    errors: list[str] = []
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        return ["modeler handoff schema must declare $defs"]

    def walk(node: object, location: str) -> None:
        if isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{location}[{index}]")
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if properties is not None:
            if node.get("type") != "object":
                errors.append(f"{location}: properties must belong to an object schema")
            if node.get("additionalProperties") is not False:
                errors.append(f"{location}: object must set additionalProperties=false")
            if not isinstance(properties, dict):
                errors.append(f"{location}: properties must be an object")
            else:
                required = node.get("required")
                if not isinstance(required, list) or set(required) != set(properties):
                    errors.append(f"{location}: every declared property must be required")
        reference = node.get("$ref")
        if isinstance(reference, str):
            prefix = "#/$defs/"
            if not reference.startswith(prefix) or reference[len(prefix) :] not in defs:
                errors.append(f"{location}: unresolved or external $ref {reference!r}")
        for key, child in node.items():
            walk(child, f"{location}.{key}")

    walk(schema, "$")

    root_properties = schema.get("properties")
    if not isinstance(root_properties, dict) or set(root_properties) != MODEL_HANDOFF_FIELDS:
        errors.append("modeler handoff root fields differ from the seven-field contract")

    batch = defs.get("ModelingBatch")
    batch_properties = batch.get("properties") if isinstance(batch, dict) else None
    if not isinstance(batch_properties, dict) or set(batch_properties) != MODELING_BATCH_FIELDS:
        errors.append("ModelingBatch fields differ from the dry-run handoff contract")

    for item_name, (command_kind, payload_refs) in ITEM_PAYLOADS.items():
        item = defs.get(item_name)
        properties = item.get("properties") if isinstance(item, dict) else None
        if not isinstance(properties, dict):
            errors.append(f"{item_name}: missing properties")
            continue
        command = properties.get("command_kind")
        if not isinstance(command, dict) or command.get("const") != command_kind:
            errors.append(f"{item_name}: command_kind is not fixed to {command_kind}")
        payload = properties.get("payload")
        if not isinstance(payload, dict):
            errors.append(f"{item_name}: missing payload schema")
            continue
        if "$ref" in payload:
            actual_refs = {payload["$ref"]}
        else:
            alternatives = payload.get("anyOf")
            actual_refs = (
                {
                    alternative.get("$ref")
                    for alternative in alternatives
                    if isinstance(alternative, dict)
                }
                if isinstance(alternatives, list)
                else set()
            )
        if actual_refs != payload_refs:
            errors.append(f"{item_name}: payload schema is not correlated with {command_kind}")

    forbidden = FORBIDDEN_MODEL_FIELDS | FORBIDDEN_SECRET_FIELDS
    for definition_name, definition in defs.items():
        if not definition_name.endswith("Payload") or not isinstance(definition, dict):
            continue
        properties = definition.get("properties")
        if isinstance(properties, dict):
            found = sorted(forbidden & set(properties))
            if found:
                errors.append(f"{definition_name}: forbidden fields {found}")
    return errors


def main() -> None:
    errors: list[str] = []
    skill_text = SKILL_FILE.read_text(encoding="utf-8")
    try:
        frontmatter = parse_frontmatter(skill_text)
    except ValueError as exc:
        errors.append(str(exc))
        frontmatter = {}
    if frontmatter.get("name") != "ontology-builder":
        errors.append("SKILL.md frontmatter name must be ontology-builder")
    if set(frontmatter) != {"name", "description"}:
        errors.append("SKILL.md frontmatter may contain only name and description")
    if len(frontmatter.get("description", "")) < 40:
        errors.append("SKILL.md frontmatter description is missing or too short")
    if len(skill_text.splitlines()) >= 500:
        errors.append("SKILL.md must stay below 500 lines")

    resource_refs = set(RESOURCE_REFERENCE.findall(skill_text))
    actual_refs = {
        str(path.relative_to(SKILL_DIR))
        for pattern in ("*.md", "*.json")
        for path in (SKILL_DIR / "references").glob(pattern)
    }
    if resource_refs != actual_refs:
        errors.append(
            f"SKILL.md resource links differ: missing={sorted(actual_refs - resource_refs)}, "
            f"unknown={sorted(resource_refs - actual_refs)}"
        )
    for resource in resource_refs:
        if not (SKILL_DIR / resource).is_file():
            errors.append(f"missing linked resource: {resource}")

    try:
        model_handoff_schema = json.loads(MODEL_HANDOFF_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid modeler handoff schema: {exc}")
    else:
        if not isinstance(model_handoff_schema, dict):
            errors.append("modeler handoff schema root must be an object")
        else:
            errors.extend(validate_model_handoff_schema(model_handoff_schema))

    cases = json.loads((EVALS_DIR / "cases.json").read_text(encoding="utf-8"))
    declared = {
        tool for case in cases for tool in case.get("assertions", {}).get("required_tools", [])
    }
    docs = [SKILL_FILE, *sorted((SKILL_DIR / "references").glob("*.md"))]
    documented = {
        tool for path in docs for tool in TOOL_REFERENCE.findall(path.read_text(encoding="utf-8"))
    }
    if declared != documented:
        errors.append(
            f"MCP dependency contract differs: undocumented={sorted(declared - documented)}, "
            f"undeclared={sorted(documented - declared)}"
        )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
    stale = sorted(tool for tool in STALE_TOOLS if tool in combined)
    if stale:
        errors.append(f"stale MCP tool references: {stale}")

    metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    for field in ("display_name:", "short_description:", "default_prompt:"):
        if field not in metadata:
            errors.append(f"agents/openai.yaml missing {field[:-1]}")
    if "$ontology-builder" not in metadata:
        errors.append("agents/openai.yaml default prompt must reference $ontology-builder")

    for removed in (
        SKILL_DIR / "scripts" / "upload_document.py",
        SKILL_DIR / "scripts" / "http_client.py",
        EVALS_DIR / "test_scripts.py",
    ):
        if removed.exists():
            errors.append(f"removed legacy helper still exists: {removed.relative_to(SKILL_DIR)}")

    required_markers = {
        "Business Knowledge Pack",
        "ModelingQualityIssue.model_validate",
        "Modeling Coverage Matrix",
        "detected_by_role",
        "finding_fingerprint",
        "independent_reviewer",
        "question_state_conflict",
        "rework_duration_ms",
        "main Agent never performs an undocumented rewrite",
        "single_agent_fallback",
        "business organizer",
        "modeler",
        "reviewer",
        "main Agent",
        "modeler-handoff.schema.json",
    }
    missing_markers = sorted(marker for marker in required_markers if marker not in combined)
    if missing_markers:
        errors.append(f"staged workflow markers missing: {missing_markers}")
    agents_dir = SKILL_DIR / "agents"
    unexpected_agent_files = sorted(
        str(path.relative_to(SKILL_DIR))
        for path in agents_dir.rglob("*")
        if path.is_file() and path.name != "openai.yaml"
    )
    if unexpected_agent_files:
        errors.append(f"runtime-specific agent files are forbidden: {unexpected_agent_files}")

    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Validated ontology-builder structure, {len(actual_refs)} references, "
        f"and {len(declared)} declared MCP dependencies."
    )


if __name__ == "__main__":
    main()
