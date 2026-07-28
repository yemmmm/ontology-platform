#!/usr/bin/env python3
"""Validate the current ontology-modeling skill and legacy deprecation boundary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "ontology-modeling"
LEGACY_SKILLS = (
    "ontology-builder",
    "ontology-business-organizer",
    "ontology-model-reviewer",
    "ontology-retrieval-evaluator",
    "ontology-work-unit-modeler",
)
REQUIRED_REFERENCES = (
    "prompts.md",
    "platform-flow.md",
    "deprecated-artifacts.md",
)
LEGACY_ARTIFACTS = (
    ".codex/modeling-harness.md",
    ".codex/hooks/modeling_harness.py",
    ".codex/fast_local_launcher.py",
    ".codex/local_modeling_adapter.py",
    ".codex/modeling_profiles.py",
    ".codex/shared_modeling_directory.py",
    ".codex/modeling_handoff.py",
    ".claude/modeling-harness.md",
    ".claude/local-modeling.md",
    ".claude/agents/ontology-business-organizer.md",
    ".claude/agents/ontology-model-reviewer.md",
    ".claude/agents/ontology-modeling-agent.md",
    ".claude/agents/ontology-retrieval-evaluator.md",
    ".claude/agents/ontology-reviewer.md",
    ".claude/agents/ontology-work-unit-modeler.md",
    ".claude/agents/semantic-analyst.md",
    ".claude/agents/simulated-user.md",
    ".claude/agents/source-extractor.md",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    require(skill_text.startswith("---\nname: ontology-modeling\n"), "invalid skill frontmatter")
    require("TODO" not in skill_text, "skill still contains TODO")
    require("$ontology-modeling" in metadata, "metadata does not invoke $ontology-modeling")

    for reference in REQUIRED_REFERENCES:
        require((SKILL_ROOT / "references" / reference).is_file(), f"missing {reference}")
        require(f"(references/{reference})" in skill_text, f"SKILL.md does not link {reference}")

    for legacy_name in LEGACY_SKILLS:
        legacy_text = (ROOT / "skills" / legacy_name / "SKILL.md").read_text(encoding="utf-8")
        require("DEPRECATED" in legacy_text, f"{legacy_name} is not marked DEPRECATED")
        require("ontology-modeling" in legacy_text, f"{legacy_name} has no replacement pointer")

    for relative_path in LEGACY_ARTIFACTS:
        path = ROOT / relative_path
        require("DEPRECATED" in path.read_text(encoding="utf-8"), f"{path} is not deprecated")

    print("ontology-modeling skill validation passed")


if __name__ == "__main__":
    main()
