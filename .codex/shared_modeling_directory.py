#!/usr/bin/env python3
"""Deterministic local primitives for an R1.1-006 Shared Modeling Directory.

This module deliberately stops at the filesystem/integration boundary.  It does not load
credentials, choose an execution profile, acquire leases, or submit platform requests.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
EXECUTION_PROFILES = {"local", "formal"}
STATUSES = {"pending", "working", "ready", "blocked", "accepted"}
REVIEW_VERDICTS = {"PASS", "REVISE", "BLOCKED"}
VERIFICATION_VERDICTS = {"PASS", "FAIL", "BLOCKED"}
SET_LIKE_ITEM_FIELDS = {"depends_on", "evidence_reference_ids", "competency_question_ids"}
FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "lease_token",
    "password",
    "secret",
    "token",
}
FORBIDDEN_RUN_FILES = {"mailbox.json", "messages.json", "reasoning.json"}
FORBIDDEN_SOURCE_BODY_FIELDS = {"body", "content", "excerpt", "full_text", "text"}


class DirectoryContractError(ValueError):
    """Raised when current directory state cannot safely advance."""


class CapacityError(DirectoryContractError):
    """Raised when an item or a materialized request cannot satisfy platform limits."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DirectoryContractError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DirectoryContractError(f"malformed JSON in {path}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DirectoryContractError(message)


def _bounded_text(value: Any, field: str, maximum: int = 2_000) -> str:
    _require(isinstance(value, str) and value.strip(), f"{field} must be a non-empty string")
    _require(len(value) <= maximum, f"{field} exceeds {maximum} characters")
    return value


def _unique(values: Iterable[str], field: str) -> list[str]:
    result = list(values)
    _require(all(isinstance(value, str) and value for value in result), f"invalid {field}")
    _require(len(result) == len(set(result)), f"duplicate {field}")
    return result


def _reject_secrets(value: Any, location: str = "document") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            compact = normalized.replace("_", "")
            if (
                normalized in FORBIDDEN_KEYS
                or normalized.endswith(("_api_key", "_token", "_password", "_secret"))
                or compact in {"authorization", "bearertoken", "leasetoken", "accesstoken"}
            ):
                raise DirectoryContractError(f"forbidden secret field {key!r} in {location}")
            _reject_secrets(nested, f"{location}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secrets(nested, f"{location}[{index}]")


def _validate_bounded_list(
    value: Any, field: str, *, maximum_items: int = 100, maximum_text: int = 2_000
) -> None:
    _require(isinstance(value, list), f"{field} must be a list")
    _require(len(value) <= maximum_items, f"{field} exceeds {maximum_items} items")
    for index, item in enumerate(value):
        if isinstance(item, str):
            _bounded_text(item, f"{field}[{index}]", maximum_text)
        else:
            _require(isinstance(item, dict), f"{field}[{index}] must be a string or object")
            _require(
                len(canonical_json_bytes(item)) <= maximum_text * 4,
                f"{field}[{index}] is too large",
            )


def _safe_relative(path: str, field: str) -> Path:
    _require(isinstance(path, str) and path, f"{field} must be a non-empty relative path")
    candidate = Path(path)
    _require(not candidate.is_absolute(), f"{field} must be relative: {path}")
    _require(".." not in candidate.parts, f"{field} must not escape its root: {path}")
    return candidate


def _run_path(run_dir: Path, relative: str) -> Path:
    return run_dir / _safe_relative(relative, "run path")


def _load_run(run_dir: Path) -> dict[str, Any]:
    run = _read_json(run_dir / "run.json")
    _require(isinstance(run, dict), "run.json must contain an object")
    return run


def _repository_root(run_dir: Path, run: dict[str, Any]) -> Path:
    value = run.get("repository_root")
    _require(isinstance(value, str) and value, "repository_root must be a non-empty path")
    path = Path(value)
    root = path.resolve() if path.is_absolute() else (run_dir / path).resolve()
    _require(root.is_dir(), f"repository_root does not exist: {root}")
    return root


def _source_path(run_dir: Path, run: dict[str, Any], locator: str) -> Path:
    return _repository_root(run_dir, run) / _safe_relative(locator, "source locator")


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(item)
    for field in SET_LIKE_ITEM_FIELDS:
        values = normalized.get(field, [])
        _require(isinstance(values, list), f"modeling item {field} must be a list")
        normalized[field] = sorted(set(values))
    normalized.setdefault("evidence", [])
    normalized.setdefault("rationale", None)
    return normalized


def _item_refs(value: Any) -> set[str]:
    if isinstance(value, dict):
        if set(value) == {"item_ref"} and isinstance(value["item_ref"], dict):
            item_id = value["item_ref"].get("client_item_id")
            output = value["item_ref"].get("output")
            _require(
                isinstance(item_id, str) and item_id and output in {"resource_id", "resource_iri"},
                "invalid item_ref; expected client_item_id and resource_id/resource_iri output",
            )
            return {item_id}
        refs: set[str] = set()
        for nested in value.values():
            refs.update(_item_refs(nested))
        return refs
    if isinstance(value, list):
        refs = set()
        for nested in value:
            refs.update(_item_refs(nested))
        return refs
    return set()


def _topological_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = defaultdict(set)
    for raw in items:
        _require(isinstance(raw, dict), "each modeling item must be an object")
        item = _normalize_item(raw)
        item_id = _bounded_text(item.get("client_item_id"), "client_item_id", 255)
        _require(item_id not in by_id, f"duplicate client_item_id: {item_id}")
        _bounded_text(item.get("command_kind"), f"{item_id}.command_kind", 80)
        _require(isinstance(item.get("payload"), dict), f"{item_id}.payload must be an object")
        evidence = item.get("evidence")
        _require(isinstance(evidence, list), f"{item_id}.evidence must be a list")
        for entry in evidence:
            _require(isinstance(entry, dict), f"{item_id}.evidence entry must be an object")
            _bounded_text(entry.get("document_name"), f"{item_id}.evidence.document_name", 255)
            _bounded_text(entry.get("excerpt"), f"{item_id}.evidence.excerpt", 100_000_000)
        refs = set(item["depends_on"]) | _item_refs(item["payload"])
        by_id[item_id] = item
        dependencies[item_id] = refs
    for item_id, refs in dependencies.items():
        unknown = sorted(refs - set(by_id))
        _require(not unknown, f"{item_id} has unresolved item references: {unknown}")
        _require(item_id not in refs, f"{item_id} depends on itself")
        for dependency in refs:
            dependents[dependency].add(item_id)
    ready = sorted(item_id for item_id, refs in dependencies.items() if not refs)
    ordered: list[dict[str, Any]] = []
    while ready:
        item_id = ready.pop(0)
        ordered.append(by_id[item_id])
        for dependent in sorted(dependents[item_id]):
            dependencies[dependent].discard(item_id)
            if not dependencies[dependent] and dependent not in {
                item["client_item_id"] for item in ordered
            }:
                ready.append(dependent)
        ready.sort()
    _require(len(ordered) == len(items), "modeling item dependency graph contains a cycle")
    return ordered


def _result_semantic_hash(result: dict[str, Any]) -> str:
    items = _topological_items(result.get("modeling_items", []))
    return content_hash({"modeling_items": items, "gaps": result.get("gaps", [])})


def initialize_run(run_dir: Path | str, spec: dict[str, Any]) -> dict[str, Any]:
    """Create one run from a small coordinator-owned bootstrap document."""
    run_dir = Path(run_dir).resolve()
    _require(
        not run_dir.exists() or not any(run_dir.iterdir()), f"run directory is not empty: {run_dir}"
    )
    _reject_secrets(spec, "initialization spec")
    run_id = _bounded_text(spec.get("run_id"), "run_id", 120)
    brief = _bounded_text(spec.get("brief"), "brief", 50_000)
    project_ref = spec.get("project_ref")
    _require(
        isinstance(project_ref, dict) and project_ref.get("project_id"),
        "project_ref.project_id is required",
    )
    repo_root = Path(spec.get("repository_root", Path.cwd())).resolve()
    _require(repo_root.is_dir(), f"repository_root does not exist: {repo_root}")
    allowed_commands = _unique(spec.get("allowed_command_kinds", []), "allowed command kind")
    _require(allowed_commands, "allowed_command_kinds snapshot must not be empty")
    execution_profile = spec.get("execution_profile")
    _require(
        execution_profile is None or execution_profile in EXECUTION_PROFILES,
        "execution_profile must be local or formal",
    )
    sources = copy.deepcopy(spec.get("sources", []))
    questions = copy.deepcopy(spec.get("competency_questions", []))
    coverage_items = copy.deepcopy(spec.get("coverage_items", []))
    units = copy.deepcopy(spec.get("work_units", []))
    ontologies = copy.deepcopy(spec.get("ontologies", []))
    _unique((source.get("source_id") for source in sources), "source_id")
    _unique(
        (question.get("competency_question_id") for question in questions),
        "competency_question_id",
    )
    _unique((item.get("coverage_id") for item in coverage_items), "coverage_id")
    unit_ids = _unique((unit.get("work_unit_id") for unit in units), "work_unit_id")
    ontology_ids = _unique((item.get("ontology_id") for item in ontologies), "ontology_id")
    _require(unit_ids and ontology_ids, "at least one Work Unit and Ontology are required")

    run_dir.mkdir(parents=True, exist_ok=True)
    source_index = {"schema_version": SCHEMA_VERSION, "sources": sources}
    for source in sources:
        _require(
            not (set(source) & FORBIDDEN_SOURCE_BODY_FIELDS),
            f"source {source.get('source_id')} must reference content by locator, not embed its body",
        )
        _require(
            isinstance(source.get("scope"), dict), f"source {source.get('source_id')} needs scope"
        )
        locator = source.get("locator")
        path = repo_root / _safe_relative(locator, "source locator")
        _require(path.is_file(), f"source does not exist: {locator}")
        actual_hash = file_hash(path)
        declared = source.get("content_hash")
        _require(declared in {None, actual_hash}, f"source content_hash mismatch: {locator}")
        source["content_hash"] = actual_hash
    coverage = {
        "schema_version": SCHEMA_VERSION,
        "competency_questions": questions,
        "items": coverage_items,
    }
    shared_paths = {
        "brief": "shared/brief.md",
        "source_index": "shared/source-index.json",
        "coverage": "shared/coverage.json",
    }
    work_unit_index = []
    for unit in units:
        unit_id = unit["work_unit_id"]
        ontology_id = unit.get("ontology_id")
        _require(ontology_id in ontology_ids, f"unit {unit_id} has unknown ontology_id")
        task_path = f"units/{unit_id}/task.json"
        status_path = f"units/{unit_id}/status.json"
        result_path = f"units/{unit_id}/result.json"
        output_contract = unit.get("output_contract")
        _require(isinstance(output_contract, dict), f"unit {unit_id} needs output_contract")
        allowed = output_contract.get("allowed_command_kinds", [])
        _require(
            set(allowed) <= set(allowed_commands), f"unit {unit_id} uses unknown command kinds"
        )
        task = {
            "schema_version": SCHEMA_VERSION,
            "work_unit_id": unit_id,
            "ontology_id": ontology_id,
            "source_ids": unit.get("source_ids", []),
            "coverage_ids": unit.get("coverage_ids", []),
            "competency_question_ids": unit.get("competency_question_ids", []),
            "dependency_work_unit_ids": unit.get("dependency_work_unit_ids", []),
            "input_paths": unit.get("input_paths", ["shared/brief.md"]),
            "output_contract": output_contract,
            "input_fingerprint": "pending",
        }
        _atomic_write_json(run_dir / task_path, task)
        _atomic_write_json(
            run_dir / status_path,
            {
                "schema_version": SCHEMA_VERSION,
                "work_unit_id": unit_id,
                "ontology_id": ontology_id,
                "state": "pending",
                "blockers": [],
                "updated_at": _now(),
            },
        )
        work_unit_index.append(
            {
                "work_unit_id": unit_id,
                "ontology_id": ontology_id,
                "task_path": task_path,
                "status_path": status_path,
                "result_path": result_path,
            }
        )
    ontology_index = [
        {
            "ontology_id": ontology_id,
            "candidate_path": f"ontologies/{ontology_id}/candidate.json",
            "review_path": f"ontologies/{ontology_id}/review.json",
            "batch_plan_path": f"ontologies/{ontology_id}/batch-plan.json",
            "verification_path": f"ontologies/{ontology_id}/verification.json",
        }
        for ontology_id in ontology_ids
    ]
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "project_ref": project_ref,
        "repository_root": str(repo_root),
        "shared_paths": shared_paths,
        "allowed_command_kinds": allowed_commands,
        "work_units": work_unit_index,
        "ontologies": ontology_index,
    }
    if execution_profile is not None:
        # A Profile is selected by the coordinator at initialization and is intentionally absent
        # from legacy R1.1-006 runs.  It is never a worker-controlled task field.
        run["execution_profile"] = execution_profile
    (run_dir / "shared").mkdir(exist_ok=True)
    (run_dir / "shared" / "brief.md").write_text(brief.rstrip() + "\n", encoding="utf-8")
    _atomic_write_json(run_dir / "shared" / "source-index.json", source_index)
    _atomic_write_json(run_dir / "shared" / "coverage.json", coverage)
    _atomic_write_json(run_dir / "run.json", run)
    for indexed in work_unit_index:
        task_path = run_dir / indexed["task_path"]
        task = _read_json(task_path)
        task["input_fingerprint"] = compute_unit_input_fingerprint(run_dir, indexed["work_unit_id"])
        _atomic_write_json(task_path, task)
    report = validate_run(run_dir)
    _require(report["valid"], "; ".join(report["errors"]))
    return inspect_run(run_dir)


def _indexes(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run = _load_run(run_dir)
    shared = run.get("shared_paths", {})
    source_index = _read_json(_run_path(run_dir, shared.get("source_index", "")))
    coverage = _read_json(_run_path(run_dir, shared.get("coverage", "")))
    return run, source_index, coverage


def _unit_entry(run: dict[str, Any], unit_id: str) -> dict[str, Any]:
    matches = [entry for entry in run.get("work_units", []) if entry.get("work_unit_id") == unit_id]
    _require(len(matches) == 1, f"unknown or duplicate work_unit_id: {unit_id}")
    return matches[0]


def _ontology_entry(run: dict[str, Any], ontology_id: str) -> dict[str, Any]:
    matches = [
        entry for entry in run.get("ontologies", []) if entry.get("ontology_id") == ontology_id
    ]
    _require(len(matches) == 1, f"unknown or duplicate ontology_id: {ontology_id}")
    return matches[0]


def compute_unit_input_fingerprint(run_dir: Path | str, unit_id: str) -> str:
    run_dir = Path(run_dir).resolve()
    run, source_index, coverage = _indexes(run_dir)
    entry = _unit_entry(run, unit_id)
    task = _read_json(_run_path(run_dir, entry["task_path"]))
    task_for_hash = copy.deepcopy(task)
    task_for_hash.pop("input_fingerprint", None)
    sources_by_id = {source["source_id"]: source for source in source_index.get("sources", [])}
    questions_by_id = {
        question["competency_question_id"]: question
        for question in coverage.get("competency_questions", [])
    }
    coverage_by_id = {item["coverage_id"]: item for item in coverage.get("items", [])}
    entries: list[dict[str, str]] = [
        {"path": entry["task_path"], "content_hash": content_hash(task_for_hash)}
    ]
    brief_path = _run_path(run_dir, run["shared_paths"]["brief"])
    entries.append({"path": run["shared_paths"]["brief"], "content_hash": file_hash(brief_path)})
    for source_id in sorted(task.get("source_ids", [])):
        source = sources_by_id.get(source_id)
        _require(source is not None, f"unit {unit_id} references unknown source {source_id}")
        source_path = _source_path(run_dir, run, source["locator"])
        _require(source_path.is_file(), f"unit {unit_id} source is missing: {source['locator']}")
        scoped = {key: value for key, value in source.items() if key != "content_hash"}
        scoped["content_hash"] = file_hash(source_path)
        entries.append({"path": f"source:{source_id}", "content_hash": content_hash(scoped)})
    selected_coverage = [
        coverage_by_id[item_id]
        for item_id in task.get("coverage_ids", [])
        if item_id in coverage_by_id
    ]
    selected_questions = [
        questions_by_id[item_id]
        for item_id in task.get("competency_question_ids", [])
        if item_id in questions_by_id
    ]
    entries.append({"path": "coverage:selected", "content_hash": content_hash(selected_coverage)})
    entries.append({"path": "questions:selected", "content_hash": content_hash(selected_questions)})
    for path_value in sorted(set(task.get("input_paths", []))):
        relative = _safe_relative(path_value, "input path")
        if relative.as_posix() == run["shared_paths"]["brief"]:
            continue
        path = (
            run_dir / relative
            if relative.parts[0] in {"shared", "units"}
            else _repository_root(run_dir, run) / relative
        )
        _require(path.is_file(), f"unit {unit_id} input path is missing: {path_value}")
        entries.append({"path": f"input:{path_value}", "content_hash": file_hash(path)})
    for dependency_id in sorted(task.get("dependency_work_unit_ids", [])):
        dependency = _unit_entry(run, dependency_id)
        status = _read_json(_run_path(run_dir, dependency["status_path"]))
        if status.get("state") in {"ready", "accepted"}:
            result = _read_json(_run_path(run_dir, dependency["result_path"]))
            dependency_hash = _result_semantic_hash(result)
        else:
            dependency_hash = "incomplete"
        entries.append({"path": f"dependency:{dependency_id}", "content_hash": dependency_hash})
    entries.sort(key=lambda value: value["path"])
    return content_hash(entries)


def _validate_item(item: dict[str, Any], allowed_commands: set[str]) -> None:
    normalized = _normalize_item(item)
    item_id = _bounded_text(normalized.get("client_item_id"), "client_item_id", 255)
    command = _bounded_text(normalized.get("command_kind"), f"{item_id}.command_kind", 80)
    _require(command in allowed_commands, f"{item_id} command_kind is not allowed: {command}")
    _require(isinstance(normalized.get("payload"), dict), f"{item_id}.payload must be an object")
    _reject_secrets(normalized, f"modeling item {item_id}")


def validate_run(run_dir: Path | str) -> dict[str, Any]:
    """Return actionable diagnostics without guessing through invalid state."""
    run_dir = Path(run_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        run, source_index, coverage = _indexes(run_dir)
        _reject_secrets(run, "run.json")
        _reject_secrets(source_index, "source-index.json")
        _reject_secrets(coverage, "coverage.json")
        _require(run.get("schema_version") == SCHEMA_VERSION, "unsupported run schema_version")
        _bounded_text(run.get("run_id"), "run_id", 120)
        _require(
            run.get("execution_profile") is None
            or run.get("execution_profile") in EXECUTION_PROFILES,
            "run execution_profile is invalid",
        )
        local_execution = run.get("local_execution")
        _require(
            local_execution is None or run.get("execution_profile") == "local",
            "local_execution requires a local Profile run",
        )
        if local_execution is not None:
            _require(isinstance(local_execution, dict), "local_execution must be an object")
            _bounded_text(local_execution.get("build_session_id"), "local build_session_id", 255)
            harness_run_id = local_execution.get("harness_run_id")
            _require(
                harness_run_id is None or (isinstance(harness_run_id, str) and harness_run_id),
                "local harness_run_id is invalid",
            )
        _require(
            isinstance(run.get("project_ref"), dict) and run["project_ref"].get("project_id"),
            "project_ref.project_id is required",
        )
        allowed_commands = set(
            _unique(run.get("allowed_command_kinds", []), "allowed command kind")
        )
        _require(allowed_commands, "allowed command snapshot is empty")
        shared = run.get("shared_paths", {})
        _require(
            set(shared) == {"brief", "source_index", "coverage"}, "run shared_paths is incomplete"
        )
        brief = _run_path(run_dir, shared["brief"])
        _require(
            brief.is_file() and brief.read_text(encoding="utf-8").strip(),
            "shared brief is missing or empty",
        )
        source_ids = _unique(
            (item.get("source_id") for item in source_index.get("sources", [])), "source_id"
        )
        question_ids = _unique(
            (
                item.get("competency_question_id")
                for item in coverage.get("competency_questions", [])
            ),
            "competency_question_id",
        )
        coverage_ids = _unique(
            (item.get("coverage_id") for item in coverage.get("items", [])), "coverage_id"
        )
        unit_ids = _unique(
            (item.get("work_unit_id") for item in run.get("work_units", [])), "work_unit_id"
        )
        ontology_ids = _unique(
            (item.get("ontology_id") for item in run.get("ontologies", [])), "ontology_id"
        )
        sources_by_id = {item["source_id"]: item for item in source_index["sources"]}
        questions_by_id = {
            item["competency_question_id"]: item for item in coverage["competency_questions"]
        }
        for source in source_index["sources"]:
            _require(
                not (set(source) & FORBIDDEN_SOURCE_BODY_FIELDS),
                f"source {source.get('source_id')} embeds a forbidden source body",
            )
            path = _source_path(run_dir, run, source.get("locator", ""))
            _require(path.is_file(), f"source is missing: {source.get('locator')}")
            if file_hash(path) != source.get("content_hash"):
                warnings.append(f"source content_hash is stale: {source['source_id']}")
            scope = source.get("scope")
            _require(
                isinstance(scope, dict), f"source {source['source_id']} scope must be an object"
            )
        for question in coverage["competency_questions"]:
            _bounded_text(
                question.get("text"),
                f"question {question.get('competency_question_id')} text",
                10_000,
            )
            _require(
                question.get("ontology_id") in ontology_ids,
                f"question {question.get('competency_question_id')} has unknown ontology",
            )
            _require(
                question.get("acceptance") is not None,
                f"question {question.get('competency_question_id')} lacks acceptance",
            )
            bound_id = question.get("platform_competency_question_id")
            _require(
                bound_id is None or (isinstance(bound_id, str) and bound_id),
                f"question {question.get('competency_question_id')} has invalid platform binding",
            )
            local_alias = question.get("local_competency_question_id")
            _require(
                local_alias is None or (isinstance(local_alias, str) and local_alias),
                f"question {question.get('competency_question_id')} has invalid local alias",
            )
            if bound_id is not None:
                _require(
                    question.get("competency_question_id") == bound_id,
                    f"question {local_alias or question.get('competency_question_id')} binding is not projected",
                )
        for item in coverage["items"]:
            _require(
                item.get("ontology_id") in ontology_ids,
                f"coverage {item.get('coverage_id')} has unknown ontology",
            )
            _require(
                item.get("work_unit_id") in unit_ids,
                f"coverage {item.get('coverage_id')} has unknown unit",
            )
            _require(
                set(item.get("source_ids", [])) <= set(source_ids),
                f"coverage {item.get('coverage_id')} has unknown source",
            )
            _require(
                set(item.get("competency_question_ids", [])) <= set(question_ids),
                f"coverage {item.get('coverage_id')} has unknown question",
            )
        tasks: dict[str, dict[str, Any]] = {}
        for entry in run["work_units"]:
            unit_id = entry["work_unit_id"]
            _require(
                entry.get("ontology_id") in ontology_ids, f"unit {unit_id} has unknown ontology"
            )
            for field in ("task_path", "status_path", "result_path"):
                _safe_relative(entry.get(field, ""), f"unit {unit_id} {field}")
            task = _read_json(_run_path(run_dir, entry["task_path"]))
            status = _read_json(_run_path(run_dir, entry["status_path"]))
            _reject_secrets(task, f"unit {unit_id} task")
            _reject_secrets(status, f"unit {unit_id} status")
            _require(
                task.get("schema_version") == SCHEMA_VERSION, f"unit {unit_id} task schema mismatch"
            )
            _require(
                task.get("work_unit_id") == unit_id
                and task.get("ontology_id") == entry["ontology_id"],
                f"unit {unit_id} task identity mismatch",
            )
            _require(
                status.get("work_unit_id") == unit_id
                and status.get("ontology_id") == entry["ontology_id"],
                f"unit {unit_id} status identity mismatch",
            )
            _require(status.get("state") in STATUSES, f"unit {unit_id} has invalid status")
            _bounded_text(status.get("updated_at"), f"unit {unit_id} updated_at", 100)
            _validate_bounded_list(
                status.get("blockers", []), f"unit {unit_id} blockers", maximum_items=20
            )
            _require(
                set(task.get("source_ids", [])) <= set(source_ids),
                f"unit {unit_id} has unknown source",
            )
            _require(
                set(task.get("coverage_ids", [])) <= set(coverage_ids),
                f"unit {unit_id} has unknown coverage",
            )
            _require(
                set(task.get("competency_question_ids", [])) <= set(question_ids),
                f"unit {unit_id} has unknown question",
            )
            _require(
                set(task.get("dependency_work_unit_ids", [])) <= set(unit_ids) - {unit_id},
                f"unit {unit_id} has invalid dependency",
            )
            contract = task.get("output_contract")
            _require(
                isinstance(contract, dict) and contract.get("result_schema"),
                f"unit {unit_id} output_contract is incomplete",
            )
            task_allowed = set(contract.get("allowed_command_kinds", []))
            _require(
                task_allowed and task_allowed <= allowed_commands,
                f"unit {unit_id} has invalid allowed commands",
            )
            for source_id in task.get("source_ids", []):
                scoped = sources_by_id[source_id].get("scope", {}).get("ontology_ids", [])
                _require(
                    entry["ontology_id"] in scoped,
                    f"source {source_id} is outside unit {unit_id} ontology scope",
                )
            for question_id in task.get("competency_question_ids", []):
                _require(
                    questions_by_id[question_id].get("ontology_id") == entry["ontology_id"],
                    f"question {question_id} is outside unit {unit_id} ontology scope",
                )
            for coverage_id in task.get("coverage_ids", []):
                coverage_item = next(
                    value for value in coverage["items"] if value["coverage_id"] == coverage_id
                )
                _require(
                    coverage_item.get("work_unit_id") == unit_id
                    and coverage_item.get("ontology_id") == entry["ontology_id"],
                    f"coverage {coverage_id} is outside unit {unit_id} scope",
                )
            tasks[unit_id] = task
        for unit_id, task in tasks.items():
            entry = _unit_entry(run, unit_id)
            status = _read_json(_run_path(run_dir, entry["status_path"]))
            if status["state"] in {"ready", "accepted"}:
                for dependency_id in task.get("dependency_work_unit_ids", []):
                    dependency = _unit_entry(run, dependency_id)
                    dependency_status = _read_json(_run_path(run_dir, dependency["status_path"]))
                    _require(
                        dependency_status.get("state") in {"ready", "accepted"},
                        f"unit {unit_id} dependency {dependency_id} is incomplete",
                    )
                result = _read_json(_run_path(run_dir, entry["result_path"]))
                _reject_secrets(result, f"unit {unit_id} result")
                _require(
                    result.get("schema_version") == SCHEMA_VERSION,
                    f"unit {unit_id} result schema mismatch",
                )
                _require(
                    result.get("work_unit_id") == unit_id
                    and result.get("ontology_id") == entry["ontology_id"],
                    f"unit {unit_id} result identity mismatch",
                )
                for field in ("source_ids", "coverage_ids", "competency_question_ids"):
                    _require(
                        set(result.get(field, [])) == set(task.get(field, [])),
                        f"unit {unit_id} result {field} mismatch",
                    )
                expected_fingerprint = compute_unit_input_fingerprint(run_dir, unit_id)
                _require(
                    result.get("input_fingerprint") == expected_fingerprint,
                    f"unit {unit_id} result has stale input fingerprint",
                )
                _require(
                    task.get("input_fingerprint") == expected_fingerprint,
                    f"unit {unit_id} task has stale input fingerprint",
                )
                _validate_bounded_list(result.get("gaps"), f"unit {unit_id} gaps")
                _bounded_text(result.get("summary"), f"unit {unit_id} summary", 2_000)
                for item in result.get("modeling_items", []):
                    _validate_item(item, set(task["output_contract"]["allowed_command_kinds"]))
                    _require(
                        set(item.get("competency_question_ids", []))
                        <= set(task.get("competency_question_ids", [])),
                        f"unit {unit_id} item has a competency question outside its task contract",
                    )
                _topological_items(result.get("modeling_items", []))
            else:
                current = compute_unit_input_fingerprint(run_dir, unit_id)
                if task.get("input_fingerprint") != current:
                    warnings.append(
                        f"unit {unit_id} task inputs changed; reset or explicit no_change resolution required"
                    )
        for forbidden in FORBIDDEN_RUN_FILES:
            _require(
                not any(run_dir.rglob(forbidden)),
                f"forbidden mailbox/reasoning file exists: {forbidden}",
            )
        for ontology_id in ontology_ids:
            ontology_entry = _ontology_entry(run, ontology_id)
            candidate_path = _run_path(run_dir, ontology_entry["candidate_path"])
            if candidate_path.exists():
                candidate = _read_json(candidate_path)
                _require(
                    candidate.get("schema_version") == SCHEMA_VERSION,
                    f"ontology {ontology_id} candidate schema mismatch",
                )
                _require(
                    candidate.get("ontology_id") == ontology_id,
                    f"ontology {ontology_id} candidate identity mismatch",
                )
                expected = candidate_hash(candidate)
                _require(
                    candidate.get("candidate_hash") == expected,
                    f"ontology {ontology_id} candidate_hash mismatch",
                )
                for item in candidate.get("modeling_items", []):
                    _require(
                        set(item.get("competency_question_ids", [])) <= set(question_ids),
                        f"ontology {ontology_id} candidate has unknown competency question",
                    )
                review_path = _run_path(run_dir, ontology_entry["review_path"])
                if review_path.exists():
                    validate_review(run_dir, ontology_id, require_pass=False)
                plan_path = _run_path(run_dir, ontology_entry["batch_plan_path"])
                if plan_path.exists():
                    validate_batch_plan(run_dir, ontology_id)
                verification_path = _run_path(run_dir, ontology_entry["verification_path"])
                if verification_path.exists():
                    validate_verification(run_dir, ontology_id)
    except (DirectoryContractError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def inspect_run(run_dir: Path | str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    units = []
    for entry in run.get("work_units", []):
        status_path = _run_path(run_dir, entry["status_path"])
        state = _read_json(status_path).get("state") if status_path.exists() else "missing"
        units.append(
            {
                "work_unit_id": entry["work_unit_id"],
                "ontology_id": entry["ontology_id"],
                "state": state,
            }
        )
    ontologies = []
    for entry in run.get("ontologies", []):
        ontologies.append(
            {
                "ontology_id": entry["ontology_id"],
                "candidate": _run_path(run_dir, entry["candidate_path"]).exists(),
                "review": _run_path(run_dir, entry["review_path"]).exists(),
                "batch_plan": _run_path(run_dir, entry["batch_plan_path"]).exists(),
                "verification": _run_path(run_dir, entry["verification_path"]).exists(),
            }
        )
    return {
        "run_id": run.get("run_id"),
        "run_dir": str(run_dir),
        "units": units,
        "ontologies": ontologies,
        "validation": validate_run(run_dir),
    }


def bind_platform_competency_questions(
    run_dir: Path | str, bindings: dict[str, str]
) -> dict[str, Any]:
    """Project accepted local CQ aliases into platform IDs before any Work Unit modeling.

    The local alias remains traceable in Coverage, while the platform ID replaces it in Coverage
    references and every downstream task/result/candidate/Batch contract.  This is intentionally a
    one-time pre-modeling transformation: changing IDs after a result or candidate exists would
    rewrite reviewed semantic content and is therefore rejected.
    """
    run_dir = Path(run_dir).resolve()
    _require(isinstance(bindings, dict) and bindings, "competency question bindings are required")
    _reject_secrets(bindings, "competency question bindings")
    run, _, coverage = _indexes(run_dir)
    _require(run.get("execution_profile") == "local", "CQ binding requires a local Profile run")
    validate_cq_binding_window(run_dir)
    questions = coverage.get("competency_questions", [])
    by_alias = {
        question.get(
            "local_competency_question_id", question.get("competency_question_id")
        ): question
        for question in questions
    }
    _require(len(by_alias) == len(questions), "competency questions are not uniquely indexed")
    _require(
        len(set(bindings.values())) == len(bindings),
        "platform competency question bindings collide",
    )
    for question_id, platform_id in bindings.items():
        _require(question_id in by_alias, f"unknown competency question: {question_id}")
        _bounded_text(platform_id, f"platform competency question for {question_id}", 255)
        existing = by_alias[question_id].get("platform_competency_question_id")
        _require(
            existing in {None, platform_id},
            f"competency question {question_id} is already bound to another platform ID",
        )
    mapped_ids = {question_id: platform_id for question_id, platform_id in bindings.items()}
    for question_id, platform_id in mapped_ids.items():
        question = by_alias[question_id]
        question["local_competency_question_id"] = question_id
        question["competency_question_id"] = platform_id
        question["platform_competency_question_id"] = platform_id
    for item in coverage.get("items", []):
        item["competency_question_ids"] = [
            mapped_ids.get(question_id, question_id)
            for question_id in item.get("competency_question_ids", [])
        ]
    _atomic_write_json(run_dir / run["shared_paths"]["coverage"], coverage)
    for entry in run.get("work_units", []):
        task_path = _run_path(run_dir, entry["task_path"])
        task = _read_json(task_path)
        task["competency_question_ids"] = [
            mapped_ids.get(question_id, question_id)
            for question_id in task.get("competency_question_ids", [])
        ]
        _atomic_write_json(task_path, task)
    for entry in run.get("work_units", []):
        task_path = _run_path(run_dir, entry["task_path"])
        task = _read_json(task_path)
        task["input_fingerprint"] = compute_unit_input_fingerprint(run_dir, entry["work_unit_id"])
        _atomic_write_json(task_path, task)
    report = validate_run(run_dir)
    _require(report["valid"], "; ".join(report["errors"]))
    return {
        "run_id": run["run_id"],
        "execution_profile": "local",
        "competency_question_bindings": {
            question_id: by_alias[question_id]["platform_competency_question_id"]
            for question_id in sorted(bindings)
        },
    }


def validate_cq_binding_window(run_dir: Path | str) -> None:
    """Reject a CQ-ID projection once downstream semantic content could need rewriting."""
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    for entry in run.get("work_units", []):
        status = _read_json(_run_path(run_dir, entry["status_path"]))
        _require(
            status.get("state") == "pending",
            f"competency question binding is too late: unit {entry['work_unit_id']} is active",
        )
        _require(
            not _run_path(run_dir, entry["result_path"]).exists(),
            f"competency question binding is too late: unit {entry['work_unit_id']} has a result",
        )
    for ontology in run.get("ontologies", []):
        for field in ("candidate_path", "review_path", "batch_plan_path", "verification_path"):
            _require(
                not _run_path(run_dir, ontology[field]).exists(),
                f"competency question binding is too late: {ontology['ontology_id']} has modeling progress",
            )


def bind_local_execution(
    run_dir: Path | str,
    *,
    build_session_id: str,
    harness_run_id: str | None = None,
) -> dict[str, Any]:
    """Store only stable non-secret Local execution references in a fixed Profile run."""
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    _require(
        run.get("execution_profile") == "local", "Local execution requires a local Profile run"
    )
    _bounded_text(build_session_id, "build_session_id", 255)
    if harness_run_id is not None:
        _bounded_text(harness_run_id, "harness_run_id", 255)
    existing = run.get("local_execution", {})
    _require(isinstance(existing, dict), "local_execution must be an object")
    expected = {"build_session_id": build_session_id}
    if harness_run_id is not None:
        expected["harness_run_id"] = harness_run_id
    _require(
        not existing
        or existing == expected
        or (
            existing.get("build_session_id") == build_session_id
            and harness_run_id is not None
            and existing.get("harness_run_id") in {None, harness_run_id}
        ),
        "Local execution references are already bound to another Session or Harness run",
    )
    if existing.get("harness_run_id") and harness_run_id is None:
        expected["harness_run_id"] = existing["harness_run_id"]
    run["local_execution"] = expected
    _atomic_write_json(run_dir / "run.json", run)
    return {"run_id": run["run_id"], "execution_profile": "local", **expected}


def reset_unit(run_dir: Path | str, unit_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    entry = _unit_entry(run, unit_id)
    result_path = _run_path(run_dir, entry["result_path"])
    if result_path.exists():
        result_path.unlink()
    task_path = _run_path(run_dir, entry["task_path"])
    task = _read_json(task_path)
    task["input_fingerprint"] = compute_unit_input_fingerprint(run_dir, unit_id)
    _atomic_write_json(task_path, task)
    status = {
        "schema_version": SCHEMA_VERSION,
        "work_unit_id": unit_id,
        "ontology_id": entry["ontology_id"],
        "state": "pending",
        "blockers": [],
        "updated_at": _now(),
    }
    _atomic_write_json(_run_path(run_dir, entry["status_path"]), status)
    return status


def rebind_no_change(
    run_dir: Path | str, unit_id: str, assessed_result: dict[str, Any], reason: str
) -> dict[str, Any]:
    """Explicitly rebind stale inputs only after equivalent semantic output is supplied."""
    run_dir = Path(run_dir).resolve()
    reason = _bounded_text(reason, "no_change reason", 1_000)
    run = _load_run(run_dir)
    entry = _unit_entry(run, unit_id)
    result_path = _run_path(run_dir, entry["result_path"])
    current = _read_json(result_path)
    _require(
        _result_semantic_hash(current) == _result_semantic_hash(assessed_result),
        "no_change assessment changed normalized semantic content",
    )
    new_fingerprint = compute_unit_input_fingerprint(run_dir, unit_id)
    old_fingerprint = current.get("input_fingerprint")
    rebound = copy.deepcopy(assessed_result)
    rebound.update(
        {
            "schema_version": SCHEMA_VERSION,
            "work_unit_id": unit_id,
            "ontology_id": entry["ontology_id"],
            "input_fingerprint": new_fingerprint,
            "input_rebind": {
                "decision": "no_change",
                "reason": reason,
                "previous_input_fingerprint": old_fingerprint,
                "semantic_content_hash": _result_semantic_hash(rebound),
            },
        }
    )
    _atomic_write_json(result_path, rebound)
    task_path = _run_path(run_dir, entry["task_path"])
    task = _read_json(task_path)
    task["input_fingerprint"] = new_fingerprint
    _atomic_write_json(task_path, task)
    return rebound


def candidate_hash(candidate: dict[str, Any]) -> str:
    ontology_id = candidate.get("ontology_id")
    contributors = sorted(set(candidate.get("contributing_work_unit_ids", [])))
    items = _topological_items(candidate.get("modeling_items", []))
    return content_hash(
        {
            "ontology_id": ontology_id,
            "contributing_work_unit_ids": contributors,
            "modeling_items": items,
        }
    )


def merge_ontology(run_dir: Path | str, ontology_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    ontology_entry = _ontology_entry(run, ontology_id)
    contributors = [entry for entry in run["work_units"] if entry["ontology_id"] == ontology_id]
    _require(contributors, f"ontology {ontology_id} has no Work Units")
    all_items: list[dict[str, Any]] = []
    terms: dict[str, Any] = {}
    for entry in sorted(contributors, key=lambda value: value["work_unit_id"]):
        status = _read_json(_run_path(run_dir, entry["status_path"]))
        _require(
            status.get("state") in {"ready", "accepted"},
            f"unit {entry['work_unit_id']} is not ready",
        )
        result = _read_json(_run_path(run_dir, entry["result_path"]))
        task = _read_json(_run_path(run_dir, entry["task_path"]))
        for dependency_id in task.get("dependency_work_unit_ids", []):
            dependency = _unit_entry(run, dependency_id)
            dependency_status = _read_json(_run_path(run_dir, dependency["status_path"]))
            _require(
                dependency_status.get("state") in {"ready", "accepted"},
                f"unit {entry['work_unit_id']} dependency {dependency_id} is incomplete",
            )
        expected_fingerprint = compute_unit_input_fingerprint(run_dir, entry["work_unit_id"])
        _require(
            result.get("input_fingerprint") == expected_fingerprint
            and task.get("input_fingerprint") == expected_fingerprint,
            f"unit {entry['work_unit_id']} has stale inputs",
        )
        for item in result.get("modeling_items", []):
            _validate_item(item, set(task["output_contract"]["allowed_command_kinds"]))
        all_items.extend(result["modeling_items"])
        for term in result.get("terms", []):
            _require(isinstance(term, dict) and term.get("term"), "term entries need term")
            key = term["term"].strip().casefold()
            if key in terms and content_hash(terms[key]) != content_hash(term):
                raise DirectoryContractError(f"conflicting shared terminology: {term['term']}")
            terms[key] = term
    ordered = _topological_items(all_items)
    identities: dict[tuple[str, str], str] = {}
    for item in ordered:
        for key, value in item["payload"].items():
            if key.endswith(("_id", "_iri")) and isinstance(value, str):
                identity = (key, value)
                digest = content_hash(
                    {"command_kind": item["command_kind"], "payload": item["payload"]}
                )
                _require(
                    identity not in identities or identities[identity] == digest,
                    f"conflicting semantic identity {key}={value}",
                )
                identities[identity] = digest
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "ontology_id": ontology_id,
        "contributing_work_unit_ids": sorted(entry["work_unit_id"] for entry in contributors),
        "modeling_items": ordered,
        "terms": [terms[key] for key in sorted(terms)],
    }
    candidate["candidate_hash"] = candidate_hash(candidate)
    _atomic_write_json(_run_path(run_dir, ontology_entry["candidate_path"]), candidate)
    return candidate


def validate_review(
    run_dir: Path | str, ontology_id: str, *, require_pass: bool = True
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    entry = _ontology_entry(run, ontology_id)
    candidate = _read_json(_run_path(run_dir, entry["candidate_path"]))
    review = _read_json(_run_path(run_dir, entry["review_path"]))
    _reject_secrets(review, "review")
    _require(review.get("schema_version") == SCHEMA_VERSION, "review schema_version mismatch")
    _require(review.get("ontology_id") == ontology_id, "review ontology_id mismatch")
    _require(
        review.get("candidate_hash") == candidate_hash(candidate),
        "review is stale for current candidate",
    )
    _require(review.get("verdict") in REVIEW_VERDICTS, "invalid review verdict")
    _validate_bounded_list(review.get("findings"), "review findings")
    if require_pass:
        _require(review["verdict"] == "PASS", f"review gate is {review['verdict']}, not PASS")
    return review


def _limits(limits: dict[str, Any]) -> dict[str, int]:
    required = {
        "modeling_batch_max_items",
        "modeling_batch_max_request_bytes",
        "modeling_batch_max_inline_evidence",
        "modeling_batch_max_evidence_excerpt_chars",
    }
    _require(set(limits) == required, f"capacity limits must contain exactly {sorted(required)}")
    normalized = {key: int(value) for key, value in limits.items()}
    _require(
        all(value >= 0 for value in normalized.values()), "capacity limits must be non-negative"
    )
    _require(
        normalized["modeling_batch_max_items"] > 0
        and normalized["modeling_batch_max_request_bytes"] > 0,
        "item and byte limits must be positive",
    )
    return normalized


def _client_batch_id(
    run_id: str, ontology_id: str, candidate_digest: str, item_ids: list[str]
) -> str:
    membership = content_hash(item_ids)[:16]
    return f"{run_id}:{ontology_id}:{candidate_digest[:12]}:{membership}"[:255]


def _request_envelope(
    ontology_id: str,
    client_batch_id: str,
    items: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    envelope = copy.deepcopy(attempt)
    lease_token_chars = envelope.pop("lease_token_chars", None)
    if lease_token_chars is not None:
        _require(
            isinstance(lease_token_chars, int) and lease_token_chars >= 0,
            "lease_token_chars must be a non-negative integer",
        )
        envelope["lease_token"] = "x" * lease_token_chars if lease_token_chars else None
    envelope.update(
        {"client_batch_id": client_batch_id, "ontology_id": ontology_id, "items": items}
    )
    return envelope


def _capacity_problem(
    items: list[dict[str, Any]],
    limits: dict[str, int],
    ontology_id: str,
    client_batch_id: str,
    attempts: list[dict[str, Any]],
) -> str | None:
    if len(items) > limits["modeling_batch_max_items"]:
        return "item count"
    evidence = [entry for item in items for entry in item.get("evidence", [])]
    if len(evidence) > limits["modeling_batch_max_inline_evidence"]:
        return "inline Evidence count"
    for entry in evidence:
        if len(entry["excerpt"]) > limits["modeling_batch_max_evidence_excerpt_chars"]:
            return "inline Evidence excerpt length"
    for attempt in attempts:
        request_bytes = len(
            canonical_json_bytes(_request_envelope(ontology_id, client_batch_id, items, attempt))
        )
        if request_bytes > limits["modeling_batch_max_request_bytes"]:
            return f"serialized {attempt.get('mode', 'attempt')} request bytes"
    return None


def plan_batches(
    run_dir: Path | str,
    ontology_id: str,
    limits: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Greedily form deterministic topological partitions under all four live limits."""
    run_dir = Path(run_dir).resolve()
    normalized_limits = _limits(limits)
    _require(
        len(attempts) >= 2, "dry-run and apply attempt templates are required for byte planning"
    )
    _require(
        {attempt.get("mode") for attempt in attempts} >= {"dry_run", "apply_atomic"},
        "attempt templates must include dry_run and apply_atomic",
    )
    for attempt in attempts:
        _reject_secrets(attempt, "attempt template")
    run = _load_run(run_dir)
    entry = _ontology_entry(run, ontology_id)
    candidate = _read_json(_run_path(run_dir, entry["candidate_path"]))
    digest = candidate_hash(candidate)
    _require(candidate.get("candidate_hash") == digest, "candidate_hash mismatch")
    validate_review(run_dir, ontology_id)
    ordered = _topological_items(candidate["modeling_items"])
    partitions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in ordered:
        trial = current + [item]
        trial_id = _client_batch_id(
            run["run_id"], ontology_id, digest, [value["client_item_id"] for value in trial]
        )
        problem = _capacity_problem(trial, normalized_limits, ontology_id, trial_id, attempts)
        if problem and current:
            partitions.append(current)
            current = [item]
            single_id = _client_batch_id(
                run["run_id"], ontology_id, digest, [item["client_item_id"]]
            )
            problem = _capacity_problem(
                current, normalized_limits, ontology_id, single_id, attempts
            )
        if problem:
            raise CapacityError(f"item {item['client_item_id']} cannot fit a Batch: {problem}")
        if trial == current or not current:
            current = trial
        elif current == [item]:
            pass
        else:
            current = trial
    if current:
        partitions.append(current)
    item_to_batch = {
        item["client_item_id"]: index
        for index, partition in enumerate(partitions)
        for item in partition
    }
    batches = []
    for index, partition in enumerate(partitions):
        item_ids = [item["client_item_id"] for item in partition]
        dependencies = sorted(
            {
                item_to_batch[dependency]
                for item in partition
                for dependency in set(item.get("depends_on", []))
                | _item_refs(item.get("payload", {}))
                if item_to_batch[dependency] != index
            }
        )
        batch_id = _client_batch_id(run["run_id"], ontology_id, digest, item_ids)
        batches.append(
            {
                "order": index,
                "client_batch_id": batch_id,
                "item_ids": item_ids,
                "depends_on_batch_orders": dependencies,
                "state": "logical",
                "platform_batch_id": None,
                "immutable_content_hash": None,
                "materialized_items": None,
                "request_bytes": {},
                "resource_outputs": {},
                "context_refreshed": False,
            }
        )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "ontology_id": ontology_id,
        "candidate_hash": digest,
        "limits": normalized_limits,
        "attempt_templates": attempts,
        "batches": batches,
    }
    plan_path = _run_path(run_dir, entry["batch_plan_path"])
    if plan_path.exists():
        previous = _read_json(plan_path)
        submitted = [
            batch["client_batch_id"]
            for batch in previous.get("batches", [])
            if batch.get("state") not in {"logical", "materialized"}
        ]
        _require(
            not submitted,
            f"cannot replace a Batch plan containing submitted immutable Batches: {submitted}",
        )
    _atomic_write_json(plan_path, plan)
    return plan


def _resolve_materialized_refs(
    value: Any, same_batch_ids: set[str], outputs: dict[str, dict[str, str]]
) -> Any:
    if isinstance(value, dict):
        if set(value) == {"item_ref"} and isinstance(value["item_ref"], dict):
            ref = value["item_ref"]
            item_id = ref.get("client_item_id")
            output = ref.get("output")
            if item_id in same_batch_ids:
                return copy.deepcopy(value)
            _require(
                item_id in outputs and output in outputs[item_id],
                f"cross-Batch item reference {item_id}.{output} lacks an applied stable resource identity",
            )
            return outputs[item_id][output]
        return {
            key: _resolve_materialized_refs(nested, same_batch_ids, outputs)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_resolve_materialized_refs(nested, same_batch_ids, outputs) for nested in value]
    return value


def materialize_batch(
    run_dir: Path | str,
    ontology_id: str,
    client_batch_id: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve cross-Batch references and freeze the platform-equivalent immutable content."""
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    entry = _ontology_entry(run, ontology_id)
    candidate = _read_json(_run_path(run_dir, entry["candidate_path"]))
    plan_path = _run_path(run_dir, entry["batch_plan_path"])
    plan = _read_json(plan_path)
    _require(plan.get("candidate_hash") == candidate_hash(candidate), "batch plan is stale")
    matches = [batch for batch in plan["batches"] if batch["client_batch_id"] == client_batch_id]
    _require(len(matches) == 1, f"unknown client_batch_id: {client_batch_id}")
    batch = matches[0]
    _require(batch["state"] in {"logical", "materialized"}, "submitted Batch content is immutable")
    by_id = {item["client_item_id"]: item for item in candidate["modeling_items"]}
    same_batch = set(batch["item_ids"])
    outputs: dict[str, dict[str, str]] = {}
    for predecessor in plan["batches"]:
        if predecessor["order"] in batch["depends_on_batch_orders"]:
            _require(
                predecessor["state"] == "applied",
                f"predecessor Batch {predecessor['client_batch_id']} is not applied",
            )
            _require(
                predecessor.get("context_refreshed") is True,
                f"Modeling Context was not refreshed after {predecessor['client_batch_id']}",
            )
            outputs.update(predecessor.get("resource_outputs", {}))
    items = []
    for item_id in batch["item_ids"]:
        item = copy.deepcopy(by_id[item_id])
        item["payload"] = _resolve_materialized_refs(item["payload"], same_batch, outputs)
        item["depends_on"] = sorted(
            dependency for dependency in item.get("depends_on", []) if dependency in same_batch
        )
        _require(
            not (_item_refs(item["payload"]) - same_batch),
            f"materialized Batch still has a cross-Batch item reference: {item_id}",
        )
        items.append(_normalize_item(item))
    immutable = {
        "ontology_id": ontology_id,
        "items": sorted(items, key=lambda value: value["client_item_id"]),
    }
    immutable_hash = content_hash(immutable)
    if batch.get("immutable_content_hash"):
        _require(
            batch["immutable_content_hash"] == immutable_hash,
            "materialized immutable content changed",
        )
    limits = _limits(plan["limits"])
    problem = _capacity_problem(items, limits, ontology_id, client_batch_id, attempts)
    if problem:
        if len(items) == 1:
            raise CapacityError(
                f"materialized Batch {client_batch_id} has an unsplittable item exceeding {problem}"
            )
        prefix_size = 0
        for size in range(len(items) - 1, 0, -1):
            prefix = items[:size]
            prefix_id = _client_batch_id(
                run["run_id"],
                ontology_id,
                plan["candidate_hash"],
                [item["client_item_id"] for item in prefix],
            )
            if not _capacity_problem(prefix, limits, ontology_id, prefix_id, attempts):
                prefix_size = size
                break
        if not prefix_size:
            raise CapacityError(
                f"materialized Batch {client_batch_id} starts with an unsplittable item exceeding {problem}"
            )
        raw_parts = [batch["item_ids"][:prefix_size], batch["item_ids"][prefix_size:]]
        replacement = []
        for item_ids in raw_parts:
            replacement.append(
                {
                    "order": 0,
                    "client_batch_id": _client_batch_id(
                        run["run_id"], ontology_id, plan["candidate_hash"], item_ids
                    ),
                    "item_ids": item_ids,
                    "depends_on_batch_orders": [],
                    "state": "logical",
                    "platform_batch_id": None,
                    "immutable_content_hash": None,
                    "materialized_items": None,
                    "request_bytes": {},
                    "resource_outputs": {},
                    "context_refreshed": False,
                }
            )
        position = plan["batches"].index(batch)
        plan["batches"][position : position + 1] = replacement
        item_to_batch: dict[str, int] = {}
        for order, current_batch in enumerate(plan["batches"]):
            current_batch["order"] = order
            for item_id in current_batch["item_ids"]:
                item_to_batch[item_id] = order
        candidate_by_id = {item["client_item_id"]: item for item in candidate["modeling_items"]}
        for current_batch in plan["batches"]:
            order = current_batch["order"]
            current_batch["depends_on_batch_orders"] = sorted(
                {
                    item_to_batch[dependency]
                    for item_id in current_batch["item_ids"]
                    for dependency in (
                        set(candidate_by_id[item_id].get("depends_on", []))
                        | _item_refs(candidate_by_id[item_id].get("payload", {}))
                    )
                    if item_to_batch[dependency] != order
                }
            )
        _atomic_write_json(plan_path, plan)
        result = materialize_batch(
            run_dir,
            ontology_id,
            replacement[0]["client_batch_id"],
            attempts,
        )
        result["replaced_unsubmitted_client_batch_id"] = client_batch_id
        return result
    batch["state"] = "materialized"
    batch["materialized_items"] = items
    batch["immutable_content_hash"] = immutable_hash
    batch["request_bytes"] = {
        attempt["mode"]: len(
            canonical_json_bytes(_request_envelope(ontology_id, client_batch_id, items, attempt))
        )
        for attempt in attempts
    }
    _atomic_write_json(plan_path, plan)
    return {
        "client_batch_id": client_batch_id,
        "immutable_content_hash": immutable_hash,
        "items": items,
        "request_bytes": batch["request_bytes"],
    }


def bind_platform_response(
    run_dir: Path | str,
    ontology_id: str,
    client_batch_id: str,
    mode: str,
    immutable_content_hash: str,
    response: dict[str, Any],
    *,
    context_refreshed: bool = False,
) -> dict[str, Any]:
    """Bind dry-run/apply responses without performing the platform request."""
    _require(mode in {"dry_run", "apply_atomic"}, "mode must be dry_run or apply_atomic")
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    entry = _ontology_entry(run, ontology_id)
    plan_path = _run_path(run_dir, entry["batch_plan_path"])
    plan = _read_json(plan_path)
    batch = next(
        (value for value in plan["batches"] if value["client_batch_id"] == client_batch_id), None
    )
    _require(batch is not None, f"unknown client_batch_id: {client_batch_id}")
    _require(
        batch.get("immutable_content_hash") == immutable_content_hash,
        "platform response immutable-content hash mismatch",
    )
    if response.get("client_batch_id") is not None:
        _require(
            response["client_batch_id"] == client_batch_id,
            "platform response client_batch_id mismatch",
        )
    platform_batch_id = _bounded_text(response.get("batch_id"), "platform batch_id", 255)
    if mode == "dry_run":
        _require(batch["state"] == "materialized", "dry-run requires materialized Batch")
        _require(
            response.get("attempt_status") in {"validated", "validation_failed"},
            "unexpected dry-run attempt_status",
        )
        _require(response.get("attempt_status") == "validated", "dry-run did not pass validation")
        batch["platform_batch_id"] = platform_batch_id
        batch["state"] = "dry_run_bound"
    else:
        _require(batch["state"] == "dry_run_bound", "apply requires a successful bound dry-run")
        _require(
            batch.get("platform_batch_id") == platform_batch_id,
            "dry-run/apply returned different platform batch_id",
        )
        _require(response.get("attempt_status") == "applied", "apply response is not applied")
        outputs: dict[str, dict[str, str]] = {}
        for item in response.get("items", []):
            item_id = item.get("client_item_id")
            resource_outputs = item.get("resource_outputs", {})
            _require(
                item_id in batch["item_ids"] and isinstance(resource_outputs, dict),
                "invalid platform item outputs",
            )
            outputs[item_id] = {
                key: value
                for key, value in resource_outputs.items()
                if key in {"resource_id", "resource_iri"} and isinstance(value, str)
            }
        batch["resource_outputs"] = outputs
        batch["context_refreshed"] = bool(context_refreshed)
        batch["state"] = "applied"
    _atomic_write_json(plan_path, plan)
    return batch


def validate_batch_plan(run_dir: Path | str, ontology_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run = _load_run(run_dir)
    entry = _ontology_entry(run, ontology_id)
    candidate = _read_json(_run_path(run_dir, entry["candidate_path"]))
    plan = _read_json(_run_path(run_dir, entry["batch_plan_path"]))
    _reject_secrets(plan, "batch plan")
    _require(plan.get("schema_version") == SCHEMA_VERSION, "batch plan schema_version mismatch")
    _require(plan.get("ontology_id") == ontology_id, "batch plan ontology_id mismatch")
    _require(
        plan.get("candidate_hash") == candidate_hash(candidate),
        f"ontology {ontology_id} batch plan is stale",
    )
    limits = _limits(plan.get("limits", {}))
    batches = plan.get("batches")
    _require(isinstance(batches, list), "batch plan batches must be a list")
    ordered_items = _topological_items(candidate.get("modeling_items", []))
    _require(not ordered_items or batches, "a non-empty candidate requires at least one Batch")
    _require(
        [batch.get("order") for batch in batches] == list(range(len(batches))),
        "batch plan order must be contiguous",
    )
    client_batch_ids = _unique(
        (batch.get("client_batch_id") for batch in batches), "client_batch_id"
    )
    _require(len(client_batch_ids) == len(batches), "invalid client_batch_id index")
    flattened = [item_id for batch in batches for item_id in batch.get("item_ids", [])]
    expected_item_ids = [item["client_item_id"] for item in ordered_items]
    _require(flattened == expected_item_ids, "batch plan membership/order does not match candidate")
    item_to_batch = {item_id: batch["order"] for batch in batches for item_id in batch["item_ids"]}
    candidate_by_id = {item["client_item_id"]: item for item in ordered_items}
    for batch in batches:
        order = batch["order"]
        expected_dependencies = sorted(
            {
                item_to_batch[dependency]
                for item_id in batch["item_ids"]
                for dependency in (
                    set(candidate_by_id[item_id].get("depends_on", []))
                    | _item_refs(candidate_by_id[item_id].get("payload", {}))
                )
                if item_to_batch[dependency] != order
            }
        )
        _require(
            batch.get("depends_on_batch_orders") == expected_dependencies,
            f"Batch {batch['client_batch_id']} dependency index mismatch",
        )
        state = batch.get("state")
        _require(
            state in {"logical", "materialized", "dry_run_bound", "applied"},
            f"Batch {batch['client_batch_id']} has invalid state",
        )
        if state == "logical":
            _require(
                batch.get("materialized_items") is None
                and batch.get("immutable_content_hash") is None
                and batch.get("platform_batch_id") is None,
                f"logical Batch {batch['client_batch_id']} contains submitted content",
            )
            continue
        items = batch.get("materialized_items")
        _require(
            isinstance(items, list) and items,
            f"Batch {batch['client_batch_id']} lacks materialized items",
        )
        _require(
            [item["client_item_id"] for item in items] == batch["item_ids"],
            f"Batch {batch['client_batch_id']} materialized membership mismatch",
        )
        same_batch = set(batch["item_ids"])
        _require(
            all(_item_refs(item.get("payload", {})) <= same_batch for item in items),
            f"Batch {batch['client_batch_id']} contains a cross-Batch item reference",
        )
        _require(
            all(set(item.get("depends_on", [])) <= same_batch for item in items),
            f"Batch {batch['client_batch_id']} contains cross-Batch depends_on",
        )
        immutable = {
            "ontology_id": ontology_id,
            "items": sorted(items, key=lambda value: value["client_item_id"]),
        }
        _require(
            batch.get("immutable_content_hash") == content_hash(immutable),
            f"Batch {batch['client_batch_id']} immutable-content hash mismatch",
        )
        request_bytes = batch.get("request_bytes")
        _require(
            isinstance(request_bytes, dict) and request_bytes,
            f"Batch {batch['client_batch_id']} lacks request sizes",
        )
        _require(
            all(
                isinstance(value, int) and value <= limits["modeling_batch_max_request_bytes"]
                for value in request_bytes.values()
            ),
            f"Batch {batch['client_batch_id']} exceeds its recorded request-byte limit",
        )
        if state in {"dry_run_bound", "applied"}:
            _bounded_text(batch.get("platform_batch_id"), "platform batch_id", 255)
        if state == "applied":
            _require(
                isinstance(batch.get("resource_outputs"), dict),
                f"applied Batch {batch['client_batch_id']} lacks resource outputs",
            )
            _require(
                isinstance(batch.get("context_refreshed"), bool),
                f"applied Batch {batch['client_batch_id']} lacks context refresh state",
            )
    return plan


def _validate_passed_check_evidence(check: dict[str, Any], index: int) -> None:
    descriptions = [check[field] for field in ("query", "check_description") if field in check]
    _require(
        descriptions,
        f"passed verification check {index} lacks an executed query/check description",
    )
    for description in descriptions:
        _bounded_text(
            description,
            f"passed verification check {index} query/check description",
            10_000,
        )

    result_fields = (
        "returned_resources",
        "returned_relations",
        "returned_evidence",
        "rows",
        "matches",
    )
    has_non_empty_result = False
    for field in result_fields:
        if field not in check:
            continue
        values = check[field]
        _require(
            isinstance(values, list),
            f"passed verification check {index} {field} must be a structured result list",
        )
        _require(
            len(values) <= 1_000,
            f"passed verification check {index} {field} exceeds 1000 items",
        )
        for result_index, value in enumerate(values):
            if isinstance(value, str):
                _bounded_text(
                    value,
                    f"passed verification check {index} {field}[{result_index}]",
                    10_000,
                )
            else:
                _require(
                    isinstance(value, dict) and value,
                    f"passed verification check {index} {field}[{result_index}] is malformed",
                )
                _require(
                    len(canonical_json_bytes(value)) <= 40_000,
                    f"passed verification check {index} {field}[{result_index}] is too large",
                )
        has_non_empty_result = has_non_empty_result or bool(values)

    empty_result = check.get("empty_result")
    if empty_result is not None:
        _require(
            isinstance(empty_result, dict)
            and set(empty_result) == {"expected", "observed_count", "assertion"},
            f"passed verification check {index} has malformed empty_result evidence",
        )
        _require(
            empty_result["expected"] is True
            and type(empty_result["observed_count"]) is int
            and empty_result["observed_count"] == 0,
            f"passed verification check {index} empty_result must assert expected=true and observed_count=0",
        )
        _bounded_text(
            empty_result["assertion"],
            f"passed verification check {index} empty_result assertion",
            2_000,
        )
        _require(
            not has_non_empty_result,
            f"passed verification check {index} has contradictory non-empty and empty results",
        )
    _require(
        has_non_empty_result or empty_result is not None,
        f"passed verification check {index} lacks structured result evidence",
    )


def validate_verification(run_dir: Path | str, ontology_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run, _, coverage = _indexes(run_dir)
    entry = _ontology_entry(run, ontology_id)
    candidate = _read_json(_run_path(run_dir, entry["candidate_path"]))
    plan = validate_batch_plan(run_dir, ontology_id)
    verification = _read_json(_run_path(run_dir, entry["verification_path"]))
    _reject_secrets(verification, "verification")
    digest = candidate_hash(candidate)
    _require(
        verification.get("schema_version") == SCHEMA_VERSION,
        "verification schema_version mismatch",
    )
    _require(verification.get("ontology_id") == ontology_id, "verification ontology_id mismatch")
    _require(
        verification.get("candidate_hash") == digest == plan.get("candidate_hash"),
        "verification candidate_hash mismatch",
    )
    expected_batches = {
        batch["client_batch_id"]: (batch["platform_batch_id"], batch["immutable_content_hash"])
        for batch in plan["batches"]
    }
    actual_batches = {
        batch.get("client_batch_id"): (
            batch.get("platform_batch_id"),
            batch.get("immutable_content_hash"),
        )
        for batch in verification.get("batches", [])
    }
    _require(
        expected_batches == actual_batches, "verification Batch references do not match the plan"
    )
    _require(
        all(batch["state"] == "applied" for batch in plan["batches"]),
        "verification requires a completely applied Batch plan",
    )
    expected_questions = {
        question["competency_question_id"]
        for question in coverage.get("competency_questions", [])
        if question.get("ontology_id") == ontology_id
    }
    checks = verification.get("checks")
    _require(isinstance(checks, list), "verification checks must be a list")
    _require(len(checks) <= 1_000, "verification checks exceed 1000 items")
    for index, check in enumerate(checks):
        _require(isinstance(check, dict), f"verification check {index} must be an object")
    check_ids = {check.get("competency_question_id") for check in checks}
    _require(
        expected_questions <= check_ids, "verification does not cover every competency question"
    )
    for index, check in enumerate(checks):
        _require(
            check.get("status") in {"passed", "failed", "blocked"},
            f"verification check {index} has invalid status",
        )
        if check.get("status") == "passed":
            _validate_passed_check_evidence(check, index)
    _validate_bounded_list(verification.get("gaps"), "verification gaps")
    _require(verification.get("verdict") in VERIFICATION_VERDICTS, "invalid verification verdict")
    if verification["verdict"] == "PASS":
        _require(
            all(check["status"] == "passed" for check in checks),
            "PASS verification contains a non-passing check",
        )
    return verification


def _json_argument(path: str) -> Any:
    return _read_json(Path(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("run_dir")
    init_parser.add_argument("--spec", required=True)
    for name in ("inspect", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("run_dir")
    reset_parser = subparsers.add_parser("reset-unit")
    reset_parser.add_argument("run_dir")
    reset_parser.add_argument("work_unit_id")
    rebind_parser = subparsers.add_parser("rebind-no-change")
    rebind_parser.add_argument("run_dir")
    rebind_parser.add_argument("work_unit_id")
    rebind_parser.add_argument("--assessment", required=True)
    rebind_parser.add_argument("--reason", required=True)
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("run_dir")
    merge_parser.add_argument("ontology_id")
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("run_dir")
    plan_parser.add_argument("ontology_id")
    plan_parser.add_argument("--limits", required=True)
    plan_parser.add_argument("--attempts", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("run_dir")
    materialize_parser.add_argument("ontology_id")
    materialize_parser.add_argument("client_batch_id")
    materialize_parser.add_argument("--attempts", required=True)
    bind_parser = subparsers.add_parser("bind-response")
    bind_parser.add_argument("run_dir")
    bind_parser.add_argument("ontology_id")
    bind_parser.add_argument("client_batch_id")
    bind_parser.add_argument("mode", choices=["dry_run", "apply_atomic"])
    bind_parser.add_argument("immutable_content_hash")
    bind_parser.add_argument("--response", required=True)
    bind_parser.add_argument("--context-refreshed", action="store_true")
    verification_parser = subparsers.add_parser("validate-verification")
    verification_parser.add_argument("run_dir")
    verification_parser.add_argument("ontology_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize_run(args.run_dir, _json_argument(args.spec))
        elif args.command == "inspect":
            result = inspect_run(args.run_dir)
        elif args.command == "validate":
            result = validate_run(args.run_dir)
        elif args.command == "reset-unit":
            result = reset_unit(args.run_dir, args.work_unit_id)
        elif args.command == "rebind-no-change":
            result = rebind_no_change(
                args.run_dir, args.work_unit_id, _json_argument(args.assessment), args.reason
            )
        elif args.command == "merge":
            result = merge_ontology(args.run_dir, args.ontology_id)
        elif args.command == "plan":
            result = plan_batches(
                args.run_dir,
                args.ontology_id,
                _json_argument(args.limits),
                _json_argument(args.attempts),
            )
        elif args.command == "materialize":
            result = materialize_batch(
                args.run_dir, args.ontology_id, args.client_batch_id, _json_argument(args.attempts)
            )
        elif args.command == "bind-response":
            result = bind_platform_response(
                args.run_dir,
                args.ontology_id,
                args.client_batch_id,
                args.mode,
                args.immutable_content_hash,
                _json_argument(args.response),
                context_refreshed=args.context_refreshed,
            )
        else:
            result = validate_verification(args.run_dir, args.ontology_id)
    except DirectoryContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not isinstance(result, dict) or result.get("valid", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
