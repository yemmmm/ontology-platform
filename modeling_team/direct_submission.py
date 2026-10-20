"""Resolve direct Modeling inputs against this run's retained governed reads."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class SubmissionInputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "") -> None:
        super().__init__(message)
        self.code, self.path = code, path


def _absolute_iri(value: Any) -> bool:
    """Recognize an IRI so it cannot cross the resource-id boundary."""

    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        return False
    parsed = urlparse(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))


def json_pointer(value: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise SubmissionInputError("invalid_resource_reference", "Use a JSON Pointer into the retained response")
    for part in pointer.split("/")[1:] if pointer else []:
        if re.search(r"~(?![01])", part):
            raise SubmissionInputError("invalid_resource_reference", "Invalid JSON Pointer escape")
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(part)] if isinstance(value, list) else value[part]
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            raise SubmissionInputError("invalid_resource_reference", "Resource pointer was not found") from exc
    return value


def apply_request_edits(request: Mapping[str, Any], edits: Any) -> dict[str, Any]:
    """Apply Agent-selected JSON Patch operations to a copy of one immutable request."""
    if not isinstance(edits, list) or not edits:
        raise SubmissionInputError(
            "request_edits_invalid", "Supply a nonempty array of explicit edits", "/request_edits"
        )
    result = deepcopy(dict(request))

    def location(pointer, *, add=False):
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("Use a non-root JSON Pointer")
        parts = pointer.split("/")[1:]
        if any(re.search(r"~(?![01])", part) for part in parts):
            raise ValueError("Invalid JSON Pointer escape")
        parts = [part.replace("~1", "/").replace("~0", "~") for part in parts]
        parent = result
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            key = part
            if isinstance(parent, list):
                if last and add and part == "-":
                    key = len(parent)
                elif not re.fullmatch(r"0|[1-9][0-9]*", part):
                    raise ValueError("Use a nonnegative canonical array index")
                else:
                    key = int(part)
                if key >= len(parent) + int(last and add):
                    raise ValueError("Array index is out of range")
            elif not isinstance(parent, dict):
                raise ValueError("Pointer parent must be an object or array")
            if last:
                if not add and (key not in parent if isinstance(parent, dict)
                                else key >= len(parent)):
                    raise ValueError("Pointer does not select an existing value")
                return parent, key
            parent = parent[key]
        raise ValueError("Use a non-root JSON Pointer")

    for index, edit in enumerate(edits):
        try:
            if not isinstance(edit, Mapping):
                raise ValueError("Each edit must be an object")
            op = edit.get("op")
            required = {"op", "path"} | ({"from"} if op == "move" else
                                         {"value"} if op in {"add", "replace"} else set())
            if op not in {"add", "replace", "remove", "move"} or set(edit) != required:
                raise ValueError("Use exactly the fields for add, replace, remove or move")
            if op == "move":
                source = edit["from"]
                destination = edit["path"]
                source_parent, source_key = location(source)
                if destination == source:
                    continue
                if isinstance(destination, str) and destination.startswith(source + "/"):
                    raise ValueError("Cannot move a value into its own descendant")
                value = source_parent.pop(source_key)
            elif op != "remove":
                value = deepcopy(edit["value"])
            parent, key = location(edit["path"], add=op in {"add", "move"})
            if op == "remove":
                parent.pop(key)
            elif isinstance(parent, list) and op in {"add", "move"}:
                parent.insert(key, value)
            else:
                parent[key] = value
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SubmissionInputError(
                "request_edits_invalid", str(exc), f"/request_edits/{index}"
            ) from exc
    return result


class ObservedModelBindings:
    def __init__(self, root: Path, observations: Mapping[str, Any], project_id: str,
                 ontology_ids: list[str], read: Any, namespace: Any = None) -> None:
        self.root, self.observations = root, observations
        self.project_id, self.ontology_ids, self.read = project_id, ontology_ids, read
        self.namespace = namespace
        self._snapshots: dict[str, Any] = {}
        self._delete_bindings: dict[str, dict[str, Any]] = {}

    def resolve(self, reference: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(reference, Mapping) or set(reference) != {"artifact_ref", "path"}:
            raise SubmissionInputError("invalid_resource_reference", "Use {artifact_ref, path} for an observed resource")
        key = json.dumps(dict(reference), sort_keys=True)
        if key in self._delete_bindings:
            return self._delete_bindings[key]
        ref = reference["artifact_ref"]
        record = self.observations.get(ref) if isinstance(ref, str) else None
        if not record or not record.get("successful") or record.get("tool") not in {
            "get_ontology_read_model", "query_semantic_context", "submit_modeling_batch", "get_modeling_batch",
        }:
            raise SubmissionInputError("resource_reference_not_observed", "Resource must come from this run's authorized read or applied receipt")
        if ref not in self._snapshots:
            target = self.root / ref
            if Path(ref).is_absolute() or ".." in Path(ref).parts or target.is_symlink() or not target.resolve().is_relative_to(self.root.resolve()):
                raise SubmissionInputError("resource_reference_outside_scope", "Resource reference escapes the retained run")
            raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record["response_digest"]:
                raise SubmissionInputError("resource_reference_changed", "The retained response changed")
            self._snapshots[ref] = json.loads(raw)
        snapshot = self._snapshots[ref]
        entry = json_pointer(snapshot, reference["path"])
        if not isinstance(entry, Mapping):
            raise SubmissionInputError("resource_entry_required", "Point to one concrete resource entry")
        envelope = snapshot.get("structuredContent", snapshot)
        data = envelope.get("data", envelope)
        request = record["request_arguments"]
        ontology_id = entry.get("ontology_id") or data.get("ontology_id") or request.get("ontology_id")
        project_id = entry.get("project_id") or data.get("project_id") or request.get("project_id")
        if project_id not in {None, self.project_id} or ontology_id not in self.ontology_ids:
            raise SubmissionInputError("forbidden_scope", "Resource reference is outside the run's authorized scope")
        revision = entry.get("model_revision", data.get("model_revision"))
        if revision is None:
            revision = next((item.get("model_revision")
                             for item in data.get("scope", {}).get("ontologies", [])
                             if item.get("ontology_id") == ontology_id), None)
        if record["tool"] == "submit_modeling_batch":
            if data.get("attempt_status") != "applied":
                raise SubmissionInputError("resource_not_applied", "Only an applied Attempt proves an existing resource")
            revision = data.get("workspace", {}).get("after_version")
        result = dict(entry.get("resource_outputs", entry))
        if "resource_iri" not in result:
            for iri_key in (
                "iri",
                "class_iri",
                "property_iri",
                "relation_type_iri",
                "entity_iri",
                "operation_iri",
            ):
                if isinstance(entry.get(iri_key), str):
                    result["resource_iri"] = entry[iri_key]
                    break
        if "resource_id" not in result:
            for identity in (entry.get("semantic_id"), entry.get("id")):
                if isinstance(identity, str) and not _absolute_iri(identity):
                    result["resource_id"] = identity
                    break
        elif _absolute_iri(result.get("resource_id")):
            # Read-model ``id`` is a semantic IRI.  Treat an IRI supplied in
            # the resource-id slot as missing instead of allowing the compiler
            # to turn it into an encoded platform ID.
            result.pop("resource_id", None)
        current = self.read("get_modeling_context", {"ontology_id": ontology_id})
        workspace = current.get("data", {}).get("workspace", {})
        current_revision = workspace.get("model_revision")
        if type(revision) is not int or current.get("ok") is not True or type(current_revision) is not int:
            raise SubmissionInputError("resource_revision_conflict", "Refresh the governed resource read and recheck the original modeling intent")
        if current_revision != revision:
            # An applied batch receipt carries the platform UUID and the
            # resource IRI together.  The UUID remains the resource identity
            # after later batches advance the workspace revision, but it is
            # reusable only when the current governed read below still sees
            # that exact IRI.  Read-model ``id``/``iri`` values alone never
            # cross this boundary.
            if (
                record["tool"] != "submit_modeling_batch"
                or current_revision < revision
                or not isinstance(result.get("resource_id"), str)
                or _absolute_iri(result.get("resource_id"))
                or not _absolute_iri(result.get("resource_iri"))
            ):
                raise SubmissionInputError("resource_revision_conflict", "Refresh the governed resource read and recheck the original modeling intent")
            revision = current_revision
        result.update(ontology_id=ontology_id, model_revision=revision, reference=dict(reference))
        command = next((item.get("command_kind") for item in request.get("items", [])
                        if item.get("client_item_id") == entry.get("client_item_id")), None)
        if command:
            result["resource_kind"] = command.split("_", 1)[1]
        elif entry.get("resource_kind"):
            result["resource_kind"] = entry["resource_kind"]
        elif request.get("model_name") in {"entities", "entity-list", "entity-detail"}:
            result["resource_kind"] = "entity"
        elif request.get("model_name") in {"classes", "class-hierarchy"}:
            result["resource_kind"] = "class"
        elif request.get("model_name") in {"facts", "predicate-facts"}:
            result["resource_kind"] = "fact"
            # statement-list uses the subject as its generic row IRI. A fact
            # is identified by its observed statement, never by that subject.
            result.pop("resource_iri", None)
            result.pop("resource_id", None)
            if entry.get("fact_id"):
                result["resource_id"] = entry["fact_id"]
            result.update(
                subject_iri=entry.get("subject_iri", entry.get("subject")),
                predicate_iri=entry.get("predicate_iri", entry.get("predicate")),
                object_value=entry.get("object_value", entry.get("object")),
                object_is_iri=entry.get("object_is_iri", entry.get("object_kind") == "iri"),
            )
        elif entry.get("kind") in {"concept", "instance", "operation", "metric"}:
            result["resource_kind"] = {"concept": "class", "instance": "entity",
                                       "operation": "operation", "metric": "metric_definition"}[entry["kind"]]
        if "resource_kind" not in result:
            types = entry.get("data", {}).get("rdf_types", [])
            for rdf_type in types:
                local = rdf_type.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                kind = {"TableMapping": "table_mapping", "JoinMapping": "join_mapping",
                        "EnumValueMeaning": "enum_meaning", "MetricDefinition": "metric_definition",
                        "DatatypeProperty": "property", "AnnotationProperty": "property",
                        "ObjectProperty": "relation_type"}.get(local)
                if kind:
                    result["resource_kind"] = kind
                    break
        iri = result.get("resource_iri")
        if isinstance(iri, str):
            visible = self.read("query_semantic_context", {
                "project_id": self.project_id, "scope_mode": "ontologies",
                "ontology_ids": [ontology_id], "query": iri, "depth": 0,
                "context_limit": 0, "context_detail": "full",
            })
            matches = visible.get("data", {}).get("primary_matches", [])
            if visible.get("ok") is not True or not any(item.get("iri") == iri for item in matches):
                raise SubmissionInputError("forbidden", "The referenced resource is not currently readable in the authorized scope")
            visible_revision = next((item.get("model_revision")
                                     for item in visible.get("data", {}).get("scope", {}).get("ontologies", [])
                                     if item.get("ontology_id") == ontology_id), revision)
            if visible_revision != revision:
                raise SubmissionInputError("resource_revision_conflict", "The resource changed during binding; refresh its governed read and recheck the affected intent", reference["path"])
            if self.namespace is not None and "resource_id" not in result:
                # Search categories (e.g. concept) are hints. Only the actual
                # current RDF type can authorize recovering a native identity.
                from app.services.modeling_handlers import CREATE_RESOURCES

                types = {rdf_type for item in matches if item.get("iri") == iri
                         for rdf_type in item.get("data", {}).get("rdf_types", [])}
                vocab = self.namespace.vocab
                type_kinds = {
                    "http://www.w3.org/2002/07/owl#Class": "class",
                    "http://www.w3.org/2000/01/rdf-schema#Class": "class",
                    "http://www.w3.org/2002/07/owl#NamedIndividual": "entity",
                    "http://www.w3.org/2002/07/owl#DatatypeProperty": "property",
                    "http://www.w3.org/2002/07/owl#AnnotationProperty": "property",
                    "http://www.w3.org/2002/07/owl#ObjectProperty": "relation_type",
                    **{str(vocab[name]): kind for name, kind in {
                        "Operation": "operation", "SemanticMapping": "mapping",
                        "TableMapping": "table_mapping", "JoinMapping": "join_mapping",
                        "EnumValueMeaning": "enum_meaning", "MetricDefinition": "metric_definition",
                    }.items()},
                }
                observed_types = set(entry.get("data", {}).get("rdf_types", [])) & type_kinds.keys()
                if observed_types and observed_types != types & type_kinds.keys():
                    raise SubmissionInputError("binding_kind_mismatch", "The current full RDF type differs from the observed resource; refresh the resource and recheck its intended kind", reference["path"])
                kinds = {type_kinds[value] for value in types if value in type_kinds}
                if not kinds:
                    # An externally typed resource may still fill an existing
                    # IRI-only slot. It supplies no verified native ID.
                    return result
                # Broad CQ categories and the old ObjectProperty fallback do
                # not distinguish platform Property from relation_type. Use
                # full RDF types plus the original native creation namespace.
                declared_kind = entry.get("resource_kind")
                if command or request.get("model_name") in {
                    "entities", "entity-list", "entity-detail", "classes", "class-hierarchy",
                }:
                    declared_kind = result.get("resource_kind")
                if "http://www.w3.org/2002/07/owl#ObjectProperty" in types:
                    kinds.add("property")
                    native_kinds = {value for value in {"property", "relation_type"}
                                    if self.namespace.resource_identifier(
                                        CREATE_RESOURCES["create_" + value][1], iri) is not None}
                    # External ObjectProperties retain the existing IRI-slot
                    # interpretation; their namespace never supplies an ID.
                    selected = native_kinds or {declared_kind or result.get("resource_kind", "relation_type")}
                    kinds = (kinds - {"property", "relation_type"}) | selected
                if len(kinds) != 1 or (declared_kind is not None and declared_kind not in kinds):
                    raise SubmissionInputError("binding_kind_mismatch", "Read the full resource with an unambiguous RDF type matching its intended kind", reference["path"])
                kind = kinds.pop()
                result["resource_kind"] = kind
                native = CREATE_RESOURCES.get("create_" + kind)
                if native:
                    identity = self.namespace.resource_identifier(native[1], iri)
                    if identity is not None:
                        result["resource_id"] = identity
        return result

    def prepare_delete(self, reference: Mapping[str, Any], submission_digest: str) -> None:
        from .r23003_contract import build_delete_impact_receipt

        binding = self.resolve(reference)
        iri, identity = binding.get("resource_iri"), binding.get("resource_id")
        if not isinstance(iri, str) or not isinstance(identity, str):
            raise SubmissionInputError("delete_identity_missing", "Delete needs an observed entity IRI and semantic ID")
        pages, cursor = [], None
        while True:
            envelope = self.read("get_entity_statement_context", {
                "ontology_id": binding["ontology_id"], "entity_iri": iri,
                "model_revision": binding["model_revision"], "page_size": 500, "cursor": cursor,
            })
            if envelope.get("ok") is not True:
                raise SubmissionInputError("delete_impact_read_failed", "Refresh the complete authorized entity impact read")
            page = envelope.get("data", {})
            pages.append(page)
            if page.get("complete") is True:
                break
            next_cursor = page.get("next_cursor")
            if not isinstance(next_cursor, str) or next_cursor == cursor:
                raise SubmissionInputError("delete_impact_incomplete", "The entity impact page chain is incomplete")
            cursor = next_cursor
        try:
            receipt = build_delete_impact_receipt(
                pages, target_semantic_id=identity, candidate_digest=submission_digest,
                project_id=self.project_id, ontology_id=binding["ontology_id"],
                model_revision=binding["model_revision"],
            )
        except ValueError as exc:
            raise SubmissionInputError("delete_impact_invalid", str(exc)) from exc
        self._delete_bindings[json.dumps(dict(reference), sort_keys=True)] = {
            **binding, "impact_receipt": receipt,
        }


def candidate_snapshot(root: Path, reference: str | None) -> dict[str, Any] | None:
    if reference is None:
        return None
    if not isinstance(reference, str):
        raise SubmissionInputError("candidate_reference_invalid", "Use a run-relative immutable candidate reference", "/candidate_ref")
    path = root / reference
    directory = root / "stage3-neutral-graph/candidates"
    if Path(reference).is_absolute() or ".." in Path(reference).parts or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise SubmissionInputError("candidate_reference_invalid", "Candidate reference is outside the authorized candidate directory", "/candidate_ref")
    try:
        result = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise SubmissionInputError("candidate_reference_unavailable", str(exc), "/candidate_ref") from exc
    if not isinstance(result, dict):
        raise SubmissionInputError("candidate_reference_invalid", "Candidate must be a JSON object", "/candidate_ref")
    # Submitted inputs already retain the immutable candidate. Reusing that
    # reference or candidate revision with changed bytes must not create a new
    # execution identity and silently recreate previously applied resources.
    for retained in (root / "value-semantics/submission-intents").glob("*-inputs.json"):
        previous = json.loads(retained.read_bytes())
        old = previous.get("candidate")
        if not isinstance(old, dict):
            continue
        same_ref = previous.get("request", {}).get("candidate_ref") == reference
        same_revision = (old.get("candidate_id"), old.get("revision")) == (
            result.get("candidate_id"), result.get("revision"))
        if (same_ref or same_revision) and old != result:
            raise SubmissionInputError(
                "candidate_revision_changed", "Publish changed content under a new candidate revision and reference",
                "/candidate_ref",
            )
    return result


def retained_submission_plan(root: Path, request: Mapping[str, Any], candidate: Any,
                             project_id: str, ontology_ids: list[str],
                             placement_binding: Any = None,
                             topology_digest: str | None = None) -> tuple[dict[str, Any], str] | None:
    """Reuse the bound inputs before stale target reads can reject a retry."""
    for path in (root / "value-semantics/submission-intents").glob("*-inputs.json"):
        snapshot = json.loads(path.read_bytes())
        if (snapshot.get("request") != request or snapshot.get("candidate") != candidate
                or snapshot.get("project_id") != project_id
                or snapshot.get("placement_binding") != placement_binding
                or snapshot.get("topology_digest", topology_digest) != topology_digest
                or not set(snapshot.get("ontology_placement", {}).values()).issubset(ontology_ids)):
            continue
        digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        plan = path.with_name(f"submission-{digest}-plan.json")
        if plan.is_file():
            return json.loads(plan.read_bytes()), digest
    return None
