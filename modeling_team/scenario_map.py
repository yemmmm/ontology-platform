"""R3.0-002 multi-slice scenario-map artifact contracts (pure mechanical).

This module owns only deterministic mechanics: artifact loading (with
symlink/escape rejection), closed structural validation of the scenario map,
the topology decision record, and the protection IRI suggestion handover, plus
the deterministic reason codes the Runner's independent platform MCP gate
feeds back to the Coordinator.  It never judges semantic quality (R3.0-006).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCENARIO_MAP_SCHEMA = "r3-0-002-scenario-map/v1"
TOPOLOGY_DECISION_SCHEMA = "r3-0-002-topology-decision/v1"
PROTECTION_IRI_SUGGESTIONS_SCHEMA = "r3-0-002-protection-iri-suggestions/v1"

# Canonical in-run artifact locations (relative to the run root).
SCENARIO_MAP_ARTIFACT_DIR = "scenario-map"
SCENARIO_MAP_FILENAME = "scenario-map.json"
TOPOLOGY_DECISION_FILENAME = "topology-decision.json"
PROTECTION_IRI_SUGGESTIONS_FILENAME = "protection-iri-suggestions.json"
TOPOLOGY_DECISION_REF_VALUE = TOPOLOGY_DECISION_FILENAME

# A.3: the three mandatory compared topology options and the six fixed
# comparison dimensions (never table count or team count).
TOPOLOGY_REQUIRED_OPTION_IDS = (
    "single_ontology",
    "domain_ontology_split",
    "shared_core_plus_domain",
)
TOPOLOGY_DIMENSIONS = (
    "concept_cohesion",
    "relation_density",
    "reuse",
    "permission_boundary",
    "change_cadence",
    "cross_domain_query",
)

# Deterministic reason codes (design §5).  ``map_unparsable`` also covers a
# missing scenario-map artifact at load time; a missing topology-decision
# artifact is reported by the Runner as ``topology_missing_artifact`` before
# this loader runs.
MAP_REASON_CODES = (
    "map_schema_mismatch",
    "map_missing_section",
    "map_dangling_reference",
    "map_term_owner_not_unique",
    "map_unparsable",
)
TOPOLOGY_REASON_CODES = (
    "topology_missing_artifact",
    "topology_unparsable",
    "topology_schema_mismatch",
    "topology_insufficient_options",
    "topology_missing_required_option",
    "topology_missing_dimension",
    "topology_empty_dimension",
    "topology_missing_selection",
    "topology_empty_rationale",
)
SUGGESTIONS_REASON_CODES = (
    "suggestions_schema_mismatch",
    "suggestions_invalid_iri",
    "suggestions_invalid_target",
    "suggestions_dangling_slice",
)

_ABSOLUTE_IRI = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S+$")
_PROTECTION_TARGET = re.compile(r"^(existing|new):.+$")


class ScenarioMapArtifactError(RuntimeError):
    """A scenario-map artifact is unavailable, unsafe, or unparsable."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class ScenarioMapIssue:
    """One deterministic structural violation of an artifact contract."""

    reason_code: str
    detail: str


def scenario_map_artifact_paths(run_root: Path) -> dict[str, Path]:
    """Canonical artifact paths inside one run workspace (A.1/A.2 locations)."""

    directory = Path(run_root) / SCENARIO_MAP_ARTIFACT_DIR
    return {
        "scenario_map": directory / SCENARIO_MAP_FILENAME,
        "topology_decision": directory / TOPOLOGY_DECISION_FILENAME,
        "protection_iri_suggestions": directory / PROTECTION_IRI_SUGGESTIONS_FILENAME,
    }


def _load_json_artifact(path: Path, *, unparsable_code: str) -> dict[str, Any]:
    """Load one JSON artifact, rejecting symlinks, non-files, and bad JSON."""

    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ScenarioMapArtifactError(unparsable_code, f"{candidate} is unavailable")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenarioMapArtifactError(unparsable_code, str(exc)) from exc
    if not isinstance(value, dict):
        raise ScenarioMapArtifactError(unparsable_code, "artifact is not a JSON object")
    return value


def load_scenario_map(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="map_unparsable")


def load_topology_decision(path: Path) -> dict[str, Any]:
    return _load_json_artifact(path, unparsable_code="topology_unparsable")


def load_protection_iri_suggestions(path: Path) -> dict[str, Any]:
    return _load_json_artifact(
        path, unparsable_code="suggestions_schema_mismatch"
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty(item) for item in value)
    )


def validate_scenario_map(value: Any) -> tuple[ScenarioMapIssue, ...]:
    """Closed structural check of the six-section scenario map (A.2)."""

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, dict):
        return (ScenarioMapIssue("map_schema_mismatch", "scenario map is not an object"),)
    if value.get("schema_version") != SCENARIO_MAP_SCHEMA:
        issues.append(ScenarioMapIssue("map_schema_mismatch", "schema_version drift"))
    sections = {
        "schema_version",
        "scenario_id",
        "slices",
        "shared_terms",
        "cross_slice_dependencies",
        "cross_slice_competency_questions",
        "explicit_unknowns",
        "adjustments",
        "topology_decision_ref",
    }
    if set(value) != sections:
        issues.append(ScenarioMapIssue("map_schema_mismatch", "top-level fields drift"))
    if not _nonempty(value.get("scenario_id")):
        issues.append(ScenarioMapIssue("map_missing_section", "scenario_id is missing"))
    for section in (
        "slices",
        "shared_terms",
        "cross_slice_dependencies",
        "cross_slice_competency_questions",
        "explicit_unknowns",
        "adjustments",
    ):
        if not isinstance(value.get(section), list):
            issues.append(ScenarioMapIssue("map_missing_section", f"{section} is missing"))
            return tuple(issues)
    reference = value.get("topology_decision_ref")
    if not isinstance(reference, str) or (
        reference.strip() and reference.strip() != TOPOLOGY_DECISION_REF_VALUE
    ):
        issues.append(
            ScenarioMapIssue("map_schema_mismatch", "topology_decision_ref is invalid")
        )

    slices = value["slices"]
    if not slices:
        issues.append(ScenarioMapIssue("map_missing_section", "slices is empty"))
    slice_ids: set[str] = set()
    for item in slices:
        if not isinstance(item, dict) or set(item) != {
            "slice_id",
            "name",
            "scope",
            "owner",
            "status",
        }:
            issues.append(ScenarioMapIssue("map_schema_mismatch", "slice fields drift"))
            continue
        if not all(_nonempty(item[field]) for field in ("slice_id", "name", "scope", "owner", "status")):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "slice field is empty"))
            continue
        if item["slice_id"] in slice_ids:
            issues.append(
                ScenarioMapIssue("map_schema_mismatch", f"duplicate slice {item['slice_id']}")
            )
            continue
        slice_ids.add(item["slice_id"])

    terms = value["shared_terms"]
    for item in terms:
        if not isinstance(item, dict) or not {"term", "used_by_slices", "owner_slice"} <= set(item) or set(item) - {
            "term",
            "used_by_slices",
            "owner_slice",
            "notes",
        }:
            issues.append(ScenarioMapIssue("map_schema_mismatch", "shared term fields drift"))
            continue
        if not _nonempty(item["term"]) or not _nonempty(item["owner_slice"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "shared term field is empty"))
            continue
        if item["owner_slice"] not in slice_ids:
            issues.append(
                ScenarioMapIssue("map_dangling_reference", f"owner slice {item['owner_slice']}")
            )
        used_by = item["used_by_slices"]
        if not isinstance(used_by, list) or not used_by or any(
            slice_id not in slice_ids for slice_id in used_by
        ):
            issues.append(
                ScenarioMapIssue("map_dangling_reference", f"used_by_slices of {item['term']}")
            )
    # A shared term must have exactly one owner entry; a duplicated term key
    # (even with the same owner) is not a unique registration.
    seen_terms: set[str] = set()
    for item in terms:
        if isinstance(item, dict) and _nonempty(item.get("term")):
            term = item["term"]
            if term in seen_terms:
                issues.append(
                    ScenarioMapIssue("map_term_owner_not_unique", f"term {term} registered twice")
                )
            seen_terms.add(term)

    for item in value["cross_slice_dependencies"]:
        if not isinstance(item, dict) or set(item) != {
            "from_slice",
            "to_slice",
            "direction",
            "connection_points",
        }:
            issues.append(
                ScenarioMapIssue("map_schema_mismatch", "dependency fields drift")
            )
            continue
        if item["from_slice"] not in slice_ids or item["to_slice"] not in slice_ids:
            issues.append(ScenarioMapIssue("map_dangling_reference", "dependency endpoint"))
        if not _nonempty(item["direction"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "dependency direction"))
        if not _nonempty_strings(item["connection_points"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "connection points"))

    for item in value["cross_slice_competency_questions"]:
        if not isinstance(item, dict) or set(item) != {
            "question_id",
            "question",
            "spans_slices",
        }:
            issues.append(ScenarioMapIssue("map_schema_mismatch", "question fields drift"))
            continue
        if not _nonempty(item["question_id"]) or not _nonempty(item["question"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "question field is empty"))
            continue
        spans = item["spans_slices"]
        if not isinstance(spans, list) or len(spans) < 2:
            issues.append(ScenarioMapIssue("map_schema_mismatch", "spans_slices < 2"))
        elif any(slice_id not in slice_ids for slice_id in spans):
            issues.append(ScenarioMapIssue("map_dangling_reference", "spans_slices"))

    for item in value["explicit_unknowns"]:
        if not isinstance(item, dict) or set(item) != {"topic", "needed_from", "status"} or not all(
            _nonempty(item[field]) for field in ("topic", "needed_from", "status")
        ):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "explicit unknown fields"))
            break

    for item in value["adjustments"]:
        if not isinstance(item, dict) or set(item) != {
            "change",
            "approved_by_coordinator",
        } or not _nonempty(item["change"]) or not _nonempty(item["approved_by_coordinator"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "adjustment fields"))
            break

    return tuple(issues)


def validate_topology_decision(value: Any) -> tuple[ScenarioMapIssue, ...]:
    """Existence/coverage check of the topology decision record (A.3).

    The gate never judges decision quality; it only rejects records that do
    not compare at least the three required options across all six fixed
    dimensions with a selection and a rationale.
    """

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, dict):
        return (ScenarioMapIssue("topology_schema_mismatch", "decision is not an object"),)
    if value.get("schema_version") != TOPOLOGY_DECISION_SCHEMA:
        issues.append(ScenarioMapIssue("topology_schema_mismatch", "schema_version drift"))
    if set(value) != {
        "schema_version",
        "scenario_id",
        "options",
        "selected_option",
        "rationale",
        "decided_by",
    }:
        issues.append(
            ScenarioMapIssue("topology_schema_mismatch", "top-level fields drift")
        )
    if not _nonempty(value.get("scenario_id")) or not _nonempty(value.get("decided_by")):
        issues.append(ScenarioMapIssue("topology_schema_mismatch", "identity field is empty"))
    options = value.get("options")
    if not isinstance(options, list):
        return (
            ScenarioMapIssue("topology_schema_mismatch", "options is not a list"),
            *issues,
        )
    option_ids: list[str] = []
    for option in options:
        if not isinstance(option, dict) or set(option) != {"option_id", "assessment"}:
            issues.append(ScenarioMapIssue("topology_schema_mismatch", "option fields drift"))
            continue
        option_id = option["option_id"]
        if not _nonempty(option_id):
            issues.append(ScenarioMapIssue("topology_schema_mismatch", "option_id is empty"))
            continue
        if option_id in option_ids:
            issues.append(
                ScenarioMapIssue("topology_schema_mismatch", f"duplicate option {option_id}")
            )
            continue
        option_ids.append(option_id)
        assessment = option["assessment"]
        if not isinstance(assessment, dict):
            issues.append(
                ScenarioMapIssue("topology_missing_dimension", f"assessment of {option_id}")
            )
            continue
        for dimension in TOPOLOGY_DIMENSIONS:
            if dimension not in assessment:
                issues.append(
                    ScenarioMapIssue(
                        "topology_missing_dimension", f"{option_id}.{dimension}"
                    )
                )
            elif not _nonempty(assessment[dimension]):
                issues.append(
                    ScenarioMapIssue("topology_empty_dimension", f"{option_id}.{dimension}")
                )
        if set(assessment) - set(TOPOLOGY_DIMENSIONS):
            issues.append(
                ScenarioMapIssue(
                    "topology_schema_mismatch", f"extra dimensions in {option_id}"
                )
            )
    if len(option_ids) < 3:
        issues.append(ScenarioMapIssue("topology_insufficient_options", "fewer than 3 options"))
    missing = set(TOPOLOGY_REQUIRED_OPTION_IDS) - set(option_ids)
    if missing:
        issues.append(
            ScenarioMapIssue(
                "topology_missing_required_option", ",".join(sorted(missing))
            )
        )
    selected = value.get("selected_option")
    if not _nonempty(selected) or selected not in option_ids:
        issues.append(ScenarioMapIssue("topology_missing_selection", "selected_option"))
    if not _nonempty(value.get("rationale")):
        issues.append(ScenarioMapIssue("topology_empty_rationale", "rationale"))
    return tuple(issues)


def validate_protection_iri_suggestions(
    value: Any, *, slice_ids: set[str] | frozenset[str] | None = None
) -> tuple[ScenarioMapIssue, ...]:
    """Format-only check of the protection IRI suggestion handover (A.4)."""

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, dict):
        return (
            ScenarioMapIssue("suggestions_schema_mismatch", "suggestions is not an object"),
        )
    if value.get("schema_version") != PROTECTION_IRI_SUGGESTIONS_SCHEMA:
        issues.append(ScenarioMapIssue("suggestions_schema_mismatch", "schema_version drift"))
    if set(value) != {"schema_version", "scenario_id", "entries", "summarized_by"}:
        issues.append(
            ScenarioMapIssue("suggestions_schema_mismatch", "top-level fields drift")
        )
    if not _nonempty(value.get("scenario_id")) or not _nonempty(value.get("summarized_by")):
        issues.append(ScenarioMapIssue("suggestions_schema_mismatch", "identity field is empty"))
    entries = value.get("entries")
    if not isinstance(entries, list):
        issues.append(ScenarioMapIssue("suggestions_schema_mismatch", "entries is not a list"))
        return tuple(issues)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "iri",
            "reason",
            "proposing_slice",
            "target_protection_set",
        }:
            issues.append(
                ScenarioMapIssue("suggestions_schema_mismatch", "entry fields drift")
            )
            continue
        iri = entry["iri"]
        if not isinstance(iri, str) or not _ABSOLUTE_IRI.match(iri):
            issues.append(ScenarioMapIssue("suggestions_invalid_iri", str(iri)[:80]))
        if not _nonempty(entry["reason"]) or not _nonempty(entry["proposing_slice"]):
            issues.append(
                ScenarioMapIssue("suggestions_schema_mismatch", "entry field is empty")
            )
        target = entry["target_protection_set"]
        if not isinstance(target, str) or not _PROTECTION_TARGET.match(target):
            issues.append(ScenarioMapIssue("suggestions_invalid_target", str(target)[:80]))
        if slice_ids is not None and entry["proposing_slice"] not in slice_ids:
            issues.append(
                ScenarioMapIssue(
                    "suggestions_dangling_slice", str(entry["proposing_slice"])
                )
            )
    return tuple(issues)
