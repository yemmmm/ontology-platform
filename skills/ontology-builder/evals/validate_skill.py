#!/usr/bin/env python3
"""Repository-portable structural validation for ontology-builder."""

from __future__ import annotations

import json
import re
from pathlib import Path


EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
SKILL_FILE = SKILL_DIR / "SKILL.md"
TOOL_REFERENCE = re.compile(r"`mcp:([a-z][a-z0-9_]*)`")
RESOURCE_REFERENCE = re.compile(r"`(references/[a-z0-9_-]+\.md)`")
STALE_TOOLS = {
    "get_evidence_artifact_status",
    "get_evidence_artifact_chunks",
    "validate_proposal",
    "create_data_source",
    "create_semantic_mapping",
    "run_connector_query",
    "submit_proposal_json",
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
    if len(frontmatter.get("description", "")) < 40:
        errors.append("SKILL.md frontmatter description is missing or too short")

    resource_refs = set(RESOURCE_REFERENCE.findall(skill_text))
    actual_refs = {
        str(path.relative_to(SKILL_DIR)) for path in (SKILL_DIR / "references").glob("*.md")
    }
    if resource_refs != actual_refs:
        errors.append(
            f"SKILL.md resource links differ: missing={sorted(actual_refs - resource_refs)}, "
            f"unknown={sorted(resource_refs - actual_refs)}"
        )
    for resource in resource_refs:
        if not (SKILL_DIR / resource).is_file():
            errors.append(f"missing linked resource: {resource}")

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

    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Validated ontology-builder structure, {len(actual_refs)} references, "
        f"and {len(declared)} declared MCP dependencies."
    )


if __name__ == "__main__":
    main()
