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
MULTIVIEW_SCENARIO_MAP_SCHEMA = "r4-0-007-scenario-map/v1"
VIEWPOINTS = frozenset({
    "object", "behavior", "rule", "role", "process", "data_mapping", "interface_mapping",
})
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
    # R3.0-006 M3 additive extension: the optional ``ontology_plan`` field.
    "topology_missing_ontology_plan",
    "topology_invalid_ontology_plan",
    "topology_dangling_slice",
)
# The additive R3.0-006 extension of the frozen six-field record: optional
# ``ontology_plan`` (mandatory for every non-single-Ontology selection).
TOPOLOGY_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_id",
        "options",
        "selected_option",
        "rationale",
        "decided_by",
    }
)
TOPOLOGY_ONTOLOGY_PLAN_FIELD = "ontology_plan"
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


def validate_scenario_map(
    value: Any, *, run_root: Path | None = None
) -> tuple[ScenarioMapIssue, ...]:
    """Closed structural check of the six-section scenario map (A.2)."""

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, dict):
        return (ScenarioMapIssue("map_schema_mismatch", "scenario map is not an object"),)
    multiview = value.get("schema_version") == MULTIVIEW_SCENARIO_MAP_SCHEMA
    if value.get("schema_version") not in (SCENARIO_MAP_SCHEMA, MULTIVIEW_SCENARIO_MAP_SCHEMA):
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
    for index, item in enumerate(slices):
        fields = {
            "slice_id",
            "name",
            "scope",
            "owner",
            "status",
        } | ({"viewpoints"} if multiview else set())
        if not isinstance(item, dict) or set(item) != fields:
            issues.append(ScenarioMapIssue("map_schema_mismatch", f"slices[{index}]: fields drift"))
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
        if multiview:
            _validate_viewpoints(item["viewpoints"], f"slices[{index}].viewpoints", issues)

    terms = value["shared_terms"]
    definition_ids: set[str] = set()
    for index, item in enumerate(terms):
        required = {"term", "used_by_slices", "owner_slice"} | (
            {"definition_id", "meaning_scope", "status", "candidate_refs"} if multiview else set()
        )
        path = f"shared_terms[{index}]"
        if not isinstance(item, dict) or not required <= set(item) or set(item) - required - {"notes"}:
            issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}: fields drift"))
            continue
        if not _nonempty(item["term"]) or not _nonempty(item["owner_slice"]):
            issues.append(ScenarioMapIssue("map_schema_mismatch", "shared term field is empty"))
            continue
        if multiview:
            if not _semantic_key(item["definition_id"]) or not _nonempty(item["meaning_scope"]):
                issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}.definition_id/meaning_scope"))
            else:
                definition_ids.add(item["definition_id"])
            if item["status"] not in ("proposed", "confirmed", "unknown", "conflict"):
                issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}.status"))
            _validate_candidate_refs(item["candidate_refs"], f"{path}.candidate_refs", issues,
                                     run_root=run_root, scenario_id=value.get("scenario_id"))
        if item["owner_slice"] not in slice_ids:
            issues.append(
                ScenarioMapIssue("map_dangling_reference", f"{path}.owner_slice")
            )
        used_by = item["used_by_slices"]
        if not isinstance(used_by, list) or not used_by or any(
            not _nonempty(slice_id) or slice_id not in slice_ids for slice_id in used_by
        ):
            issues.append(
                ScenarioMapIssue("map_dangling_reference", f"{path}.used_by_slices")
            )
    # A shared term must have exactly one owner entry; a duplicated term key
    # (even with the same owner) is not a unique registration.
    seen_terms: set[str] = set()
    for item in terms:
        key = "definition_id" if multiview else "term"
        if isinstance(item, dict) and _nonempty(item.get(key)):
            term = item[key]
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

    for index, item in enumerate(value["adjustments"]):
        required = {
            "change",
            "approved_by_coordinator",
        }
        if (not isinstance(item, dict) or not required <= set(item)
            or set(item) - required - ({"review"} if multiview else set())
            or not _nonempty(item["change"]) or not _nonempty(item["approved_by_coordinator"])):
            issues.append(ScenarioMapIssue("map_schema_mismatch", f"adjustments[{index}]: fields"))
            continue
        if "review" in item:
            _validate_review(item["review"], f"adjustments[{index}].review", issues,
                             definition_ids=definition_ids, slice_ids=slice_ids,
                             run_root=run_root, scenario_id=value.get("scenario_id"))

    return tuple(issues)


def _semantic_key(value: Any) -> bool:
    return _nonempty(value) and _ABSOLUTE_IRI.match(value) is None


def _validate_viewpoints(value: Any, path: str, issues: list[ScenarioMapIssue]) -> None:
    if not isinstance(value, list):
        issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}: expected array"))
        return
    seen: set[str] = set()
    for index, entry in enumerate(value):
        location = f"{path}[{index}]"
        if (not isinstance(entry, dict) or set(entry) != {"viewpoint", "status", "note"}
            or not _nonempty(entry.get("viewpoint")) or entry["viewpoint"] not in VIEWPOINTS
            or entry.get("status") not in ("pending", "modeled", "unknown", "not_applicable")
            or not _nonempty(entry.get("note"))):
            issues.append(ScenarioMapIssue("map_schema_mismatch", location))
            continue
        if entry["viewpoint"] in seen:
            issues.append(ScenarioMapIssue("map_schema_mismatch", f"{location}.viewpoint: duplicate"))
        seen.add(entry["viewpoint"])


def _validate_candidate_refs(
    value: Any, path: str, issues: list[ScenarioMapIssue], *, run_root: Path | None,
    scenario_id: str, historical: bool = False, references: bool = False,
    slice_ids: set[str] | None = None,
) -> None:
    if not isinstance(value, list):
        issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}: expected array"))
        return
    fields = {"candidate_id", "revision", "item_id"}
    if references:
        fields |= {"slice_id", "result", "note"}
    for index, entry in enumerate(value):
        location = f"{path}[{index}]"
        if (not isinstance(entry, dict) or set(entry) != fields
            or not _semantic_key(entry.get("candidate_id"))
            or not _semantic_key(entry.get("item_id"))
            or type(entry.get("revision")) is not int or entry["revision"] < 1):
            issues.append(ScenarioMapIssue("map_schema_mismatch", location))
            continue
        if references:
            if not _nonempty(entry["slice_id"]) or entry["slice_id"] not in slice_ids:
                issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}.slice_id"))
            if (entry["result"] not in ("unchanged", "revised", "unknown", "conflict")
                or not _nonempty(entry["note"])):
                issues.append(ScenarioMapIssue("map_schema_mismatch", f"{location}.result/note"))
        if run_root is None:
            continue
        directory = Path(run_root) / "stage3-neutral-graph" / "candidates"
        candidate_id, revision = entry["candidate_id"], entry["revision"]
        candidate_path = directory / f"{candidate_id}-r{revision}.json"
        if directory.is_symlink() or not candidate_path.resolve().is_relative_to(directory.resolve()):
            issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}: unsafe candidate path"))
            continue
        try:
            candidate = _load_json_artifact(candidate_path, unparsable_code="map_dangling_reference")
        except ScenarioMapArtifactError:
            issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}: candidate unavailable"))
            continue
        from .staged_decisions import validate_unified_candidate

        items = candidate.get("items") or []
        matched = next((item for item in items if isinstance(item, dict)
                        and item.get("item_id") == entry["item_id"]), None)
        if (validate_unified_candidate(candidate) or candidate.get("candidate_id") != candidate_id
            or candidate.get("revision") != revision or candidate.get("scenario_id") != scenario_id
            or matched is None):
            issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}: candidate/item binding"))
            continue
        if references and entry["slice_id"] not in matched.get("slice_ids", []):
            issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}.slice_id: item scope"))
        if not historical:
            # Only this candidate identity's published revisions are considered.
            for other in directory.iterdir():
                suffix = other.name.removeprefix(f"{candidate_id}-r").removesuffix(".json")
                if (other.name.startswith(f"{candidate_id}-r") and other.suffix == ".json"
                    and suffix.isdigit() and int(suffix) > revision):
                    issues.append(ScenarioMapIssue("map_dangling_reference", f"{location}.revision: stale"))
                    break


def _validate_review(
    value: Any, path: str, issues: list[ScenarioMapIssue], *, definition_ids: set[str],
    slice_ids: set[str], run_root: Path | None, scenario_id: str,
) -> None:
    fields = {"definition_ids", "before_refs", "after_refs", "coverage", "coverage_note",
              "references", "outcome", "reason"}
    if not isinstance(value, dict) or set(value) != fields:
        issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}: fields drift"))
        return
    ids = value["definition_ids"]
    if not _nonempty_strings(ids) or any(key not in definition_ids for key in ids):
        issues.append(ScenarioMapIssue("map_dangling_reference", f"{path}.definition_ids"))
    if (value["coverage"] not in ("complete", "incomplete")
        or value["outcome"] not in ("pending", "ready", "deferred", "conflict")
        or not _nonempty(value["coverage_note"]) or not _nonempty(value["reason"])):
        issues.append(ScenarioMapIssue("map_schema_mismatch", f"{path}.coverage/outcome/note/reason"))
    for field in ("before_refs", "after_refs", "references"):
        _validate_candidate_refs(value[field], f"{path}.{field}", issues, run_root=run_root,
                                 scenario_id=scenario_id, historical=field == "before_refs",
                                 references=field == "references", slice_ids=slice_ids)


def collaboration_projection(
    value: dict[str, Any], *, bindings: dict[tuple[str, int, str], str], visible_iris: set[str]
) -> dict[str, Any]:
    """Project only statuses of identities already visible in authorized reads.

    Free text, private definitions and reference counts never cross this seam.
    This is work context for the independent Judge, not semantic evidence.
    """
    definitions = []
    for term in value["shared_terms"]:
        iris = {
            bindings.get((ref["candidate_id"], ref["revision"], ref["item_id"]))
            for ref in term["candidate_refs"]
        } & visible_iris
        for iri in sorted(iris):
            reviews = []
            for adjustment in value["adjustments"]:
                review = adjustment.get("review")
                if review and term["definition_id"] in review["definition_ids"]:
                    # A multi-definition review may reveal private work; only
                    # project reviews whose entire identity scope is visible.
                    if all(any(
                        bindings.get((ref["candidate_id"], ref["revision"], ref["item_id"]))
                        in visible_iris for ref in registered["candidate_refs"]
                    ) for key in review["definition_ids"] for registered in value["shared_terms"]
                           if registered["definition_id"] == key):
                        reviews.append({"coverage": review["coverage"], "outcome": review["outcome"]})
            definitions.append({"definition_id": term["definition_id"], "resource_iri": iri,
                                "status": term["status"], "reviews": reviews})
    return {
        "schema_version": "r4-0-007-collaboration-context/v1",
        "scope_note": "Only definitions visible in this attempt's authorized model reads. "
                      "Omissions do not mean absence. These are collaboration states, not "
                      "business truth, compatibility proof or semantic acceptance.",
        "definitions": definitions,
    }


def _validate_ontology_plan(
    value: Any, *, slice_ids: set[str] | frozenset[str] | None
) -> list[ScenarioMapIssue]:
    """Structural (and, with ``slice_ids``, closure) check of ``ontology_plan``.

    R3.0-006 M3 additive extension: a mechanical ``[{name, slice_ids}]`` list
    with at least two Ontologies, non-empty unique names, and every slice of
    the scenario map assigned to at least one planned Ontology.  A logical
    slice may be served by more than one planned Ontology (shared core plus
    domain topology), so overlapping ``slice_ids`` sets are legal as long as
    each entry still names at least one slice; the plan never invents an empty
    Ontology.  Slice closure mirrors the
    ``validate_protection_iri_suggestions`` precedent: it is only checked when
    the caller passes the scenario map's slice list.
    """

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, list) or not value or (len(value) < 2 and not any(
        isinstance(entry, dict) and "ontology_id" in entry for entry in value
    )):
        return [
            ScenarioMapIssue(
                "topology_invalid_ontology_plan", "ontology_plan requires at least two entries"
            )
        ]
    names: set[str] = set()
    assigned: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) not in ({"name", "slice_ids"}, {"ontology_id", "slice_ids"}):
            issues.append(
                ScenarioMapIssue("topology_invalid_ontology_plan", "entry fields drift")
            )
            continue
        name = entry.get("ontology_id", entry.get("name"))
        if not _nonempty(name):
            issues.append(ScenarioMapIssue("topology_invalid_ontology_plan", "name is empty"))
            continue
        if name in names:
            issues.append(
                ScenarioMapIssue("topology_invalid_ontology_plan", f"duplicate name {name}")
            )
            continue
        names.add(name)
        entry_slices = entry["slice_ids"]
        if (
            not _nonempty_strings(entry_slices)
            or len(set(entry_slices)) != len(entry_slices)
        ):
            issues.append(
                ScenarioMapIssue(
                    "topology_invalid_ontology_plan", f"slice_ids of {name} are invalid"
                )
            )
            continue
        assigned.update(entry_slices)
        if slice_ids is not None:
            dangling = [slice_id for slice_id in entry_slices if slice_id not in slice_ids]
            if dangling:
                issues.append(
                    ScenarioMapIssue("topology_dangling_slice", ",".join(sorted(dangling)))
                )
    if slice_ids is not None and assigned != set(slice_ids):
        issues.append(
            ScenarioMapIssue(
                "topology_invalid_ontology_plan",
                "every scenario-map slice must be covered by at least one planned Ontology",
            )
        )
    return issues


def validate_topology_decision(
    value: Any, *, slice_ids: set[str] | frozenset[str] | None = None
) -> tuple[ScenarioMapIssue, ...]:
    """Existence/coverage check of the topology decision record (A.3).

    The gate never judges decision quality; it only rejects records that do
    not compare at least the three required options across all six fixed
    dimensions with a selection and a rationale.  R3.0-006 M3 adds the
    optional ``ontology_plan``: absent is only legal for a
    ``single_ontology`` selection, every other selection requires it, and its
    slice references must close against the scenario map when ``slice_ids``
    is provided.
    """

    issues: list[ScenarioMapIssue] = []
    if not isinstance(value, dict):
        return (ScenarioMapIssue("topology_schema_mismatch", "decision is not an object"),)
    if value.get("schema_version") != TOPOLOGY_DECISION_SCHEMA:
        issues.append(ScenarioMapIssue("topology_schema_mismatch", "schema_version drift"))
    if not set(value) <= TOPOLOGY_DECISION_FIELDS | {TOPOLOGY_ONTOLOGY_PLAN_FIELD} or (
        TOPOLOGY_DECISION_FIELDS - set(value)
    ):
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
    # R3.0-006 M3 additive ontology_plan extension (registered revision of the
    # frozen R3.0-002 six-field record; see the design's exception list).
    plan_present = TOPOLOGY_ONTOLOGY_PLAN_FIELD in value
    if plan_present and selected == "single_ontology" and not (
        isinstance(value[TOPOLOGY_ONTOLOGY_PLAN_FIELD], list)
        and len(value[TOPOLOGY_ONTOLOGY_PLAN_FIELD]) == 1
        and isinstance(value[TOPOLOGY_ONTOLOGY_PLAN_FIELD][0], dict)
        and "ontology_id" in value[TOPOLOGY_ONTOLOGY_PLAN_FIELD][0]
    ):
        issues.append(
            ScenarioMapIssue(
                "topology_schema_mismatch",
                "ontology_plan must be absent for a single_ontology selection",
            )
        )
    if not plan_present and _nonempty(selected) and selected != "single_ontology":
        issues.append(
            ScenarioMapIssue("topology_missing_ontology_plan", str(selected)[:80])
        )
    if plan_present:
        issues.extend(
            _validate_ontology_plan(
                value[TOPOLOGY_ONTOLOGY_PLAN_FIELD], slice_ids=slice_ids
            )
        )
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
