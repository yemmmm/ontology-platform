"""Runtime-neutral ordinary retrieval gate for formal modeling runs.

The gate consumes only facts observed by the host Runtime: the accepted semantic
candidate, the original query arguments, and the immutable MCP result artifacts.
It deliberately has no Agent, backend, or adapter dependency.  Codex and Pi can
therefore share the same completion decision by feeding the carrier's common
artifact-registration callback.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


ORDINARY_RETRIEVAL_RECEIPT_SCHEMA = "r2-3-005-ordinary-retrieval-receipt/v1"
_FROZEN_QUERY_FIELDS = (
    "query",
    "project_id",
    "scope_mode",
    "ontology_ids",
    "resource_types",
    "assertion_types",
    "search_mode",
    "depth",
    "limit",
    "context_limit",
)
_RESOURCE_TYPES = frozenset({"relation", "fact"})


class ProtocolRetrievalGateError(ValueError):
    """The host-observed ordinary retrieval evidence is incomplete or invalid."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolRetrievalGateError("ordinary retrieval value is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _local_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    value = value.strip().strip("<>")
    if not value:
        return None
    # RDF IRIs commonly use '#', '/', or ':' as their namespace separator.  A
    # local name is intentionally the final component, not a fuzzy substring.
    return re.split(r"[#/:]", value)[-1] or None


def _copy(value: Any) -> Any:
    # Canonical JSON is the only input accepted by the formal carrier.  A
    # round-trip keeps this module independent of the carrier's private helper.
    return json.loads(_canonical(value).decode("utf-8"))


def _safe_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ProtocolRetrievalGateError(f"{field} is not a SHA-256 digest")
    return value


class ProtocolRetrievalGate:
    """Validate all candidate-bound ordinary retrieval chains from host evidence."""

    def __init__(
        self,
        candidate: Mapping[str, Any],
        *,
        candidate_revision: Any,
        candidate_digest: str,
    ) -> None:
        if not isinstance(candidate, Mapping):
            raise ProtocolRetrievalGateError("accepted candidate is unavailable")
        self.candidate_revision = candidate_revision
        self.candidate_digest = _safe_digest(candidate_digest, "candidate_digest")
        if candidate.get("candidate_revision") != candidate_revision:
            raise ProtocolRetrievalGateError("accepted candidate revision binding is invalid")
        if _digest(dict(candidate)) != self.candidate_digest:
            raise ProtocolRetrievalGateError("accepted candidate digest binding is invalid")
        self.plan = self._extract_plan(candidate)
        self._observed_paths: list[tuple[dict[str, Any], Path]] = []

    @staticmethod
    def _range_datatype(value: Any) -> str | None:
        """Map the compact candidate range names to RDF datatype IRIs.

        The candidate currently uses ``string``, ``boolean`` and ``number``.
        ``number`` intentionally remains unconstrained because the candidate does
        not distinguish integer/decimal/float.  The actual row still has to be a
        literal and match the declared value exactly.
        """

        if not isinstance(value, str):
            return None
        return {
            "string": "http://www.w3.org/2001/XMLSchema#string",
            "boolean": "http://www.w3.org/2001/XMLSchema#boolean",
        }.get(value)

    @staticmethod
    def _binding_key(binding: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            binding.get("binding_kind"),
            binding.get("subject"),
            binding.get("object"),
            binding.get("object_type"),
            binding.get("object_datatype"),
            binding.get("object_language"),
        )

    @classmethod
    def _candidate_declarations(
        cls,
        candidate: Mapping[str, Any],
        predicate_kinds: Mapping[str, str],
        predicate_datatypes: Mapping[str, str | None],
    ) -> dict[str, list[dict[str, Any]]]:
        """Extract graph bindings declared by the accepted semantic candidate.

        Consumer-query questions and expected answer text are deliberately not
        consulted.  Relations provide a resource-to-resource edge; entity and
        explicit-unknown values provide fact bindings from the entity ID to a
        literal.  A direct fact item is accepted for small synthetic/legacy
        candidates as well.
        """

        declarations: dict[str, list[dict[str, Any]]] = {}

        def add(path: Any, binding: dict[str, Any]) -> None:
            local = _local_name(path)
            if local is None or predicate_kinds.get(local) not in _RESOURCE_TYPES:
                return
            binding["predicate"] = local
            bucket = declarations.setdefault(local, [])
            key = cls._binding_key(binding)
            if not any(cls._binding_key(existing) == key for existing in bucket):
                bucket.append(binding)

        for item in candidate.get("items", []):
            if not isinstance(item, Mapping):
                continue
            item_kind = item.get("item_kind")
            semantic = item.get("semantic")
            if not isinstance(semantic, Mapping):
                continue
            item_id = item.get("item_id")
            source_item_id = item_id if isinstance(item_id, str) and item_id else None
            if item_kind == "relation":
                subject = semantic.get("subject")
                object_value = semantic.get("object")
                predicate = semantic.get("predicate")
                if isinstance(subject, str) and subject and isinstance(object_value, str) and object_value:
                    add(
                        predicate,
                        {
                            "binding_kind": "relation",
                            "subject": subject,
                            "object": object_value,
                            "object_type": "resource",
                            "object_datatype": None,
                            "object_language": None,
                            "source_item_id": source_item_id,
                        },
                    )
            elif item_kind in {"entity", "explicit_unknown"}:
                subject = semantic.get("entity_id")
                values = semantic.get("values")
                if not isinstance(subject, str) or not subject or not isinstance(values, Mapping):
                    continue
                for predicate, object_value in values.items():
                    # ``label`` is descriptive metadata, not a declared graph
                    # predicate and therefore cannot satisfy a required path.
                    if predicate == "label" or isinstance(object_value, (Mapping, list, tuple)):
                        continue
                    add(
                        predicate,
                        {
                            "binding_kind": "fact",
                            "subject": subject,
                            "object": object_value,
                            "object_type": "literal",
                            "object_datatype": predicate_datatypes.get(_local_name(predicate) or ""),
                            "object_language": None,
                            "source_item_id": source_item_id,
                        },
                    )
            elif item_kind == "fact":
                subject = semantic.get("subject")
                object_value = semantic.get("object", semantic.get("value"))
                predicate = semantic.get("predicate")
                if isinstance(subject, str) and subject and object_value is not None:
                    add(
                        predicate,
                        {
                            "binding_kind": "fact",
                            "subject": subject,
                            "object": object_value,
                            "object_type": "literal",
                            "object_datatype": predicate_datatypes.get(_local_name(predicate) or ""),
                            "object_language": semantic.get("object_language"),
                            "source_item_id": source_item_id,
                        },
                    )
        return declarations

    @staticmethod
    def _resource_endpoint(value: Any) -> tuple[str, str] | None:
        local = _local_name(value)
        return ("resource", local) if local is not None else None

    @classmethod
    def _binding_endpoints(cls, binding: Mapping[str, Any]) -> set[tuple[str, str]]:
        endpoints: set[tuple[str, str]] = set()
        subject = cls._resource_endpoint(binding.get("subject"))
        if subject is not None:
            endpoints.add(subject)
        if binding.get("binding_kind") == "relation":
            object_endpoint = cls._resource_endpoint(binding.get("object"))
            if object_endpoint is not None:
                endpoints.add(object_endpoint)
        return endpoints

    @classmethod
    def _connected_assignment(cls, assignment: list[dict[str, Any]]) -> bool:
        if len(assignment) < 2:
            return True
        endpoint_sets = [cls._binding_endpoints(binding) for binding in assignment]
        if any(not endpoints for endpoints in endpoint_sets):
            return False
        connected = {0}
        while True:
            before = len(connected)
            for index, endpoints in enumerate(endpoint_sets):
                if index in connected:
                    continue
                if any(endpoints & endpoint_sets[other] for other in connected):
                    connected.add(index)
            if len(connected) == before:
                return len(connected) == len(assignment)

    @classmethod
    def _resolve_bindings(
        cls,
        required_paths: list[str],
        declarations: Mapping[str, list[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        options: list[list[dict[str, Any]]] = []
        for path in required_paths:
            path_options = declarations.get(path, [])
            if not path_options:
                raise ProtocolRetrievalGateError(
                    f"consumer_query required_path has no candidate binding: {path}"
                )
            options.append(path_options)

        assignments: list[list[dict[str, Any]]] = []

        def visit(index: int, selected: list[dict[str, Any]]) -> None:
            if len(assignments) > 128:
                return
            if index == len(options):
                if cls._connected_assignment(selected):
                    assignments.append(list(selected))
                return
            for binding in options[index]:
                visit(index + 1, [*selected, binding])

        visit(0, [])
        unique: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for assignment in assignments:
            signature = tuple(cls._binding_key(binding) for binding in assignment)
            unique.setdefault(signature, assignment)
        if len(unique) != 1:
            raise ProtocolRetrievalGateError(
                "consumer_query required paths do not resolve to one connected candidate binding"
            )
        selected = next(iter(unique.values()))
        return {path: dict(binding) for path, binding in zip(required_paths, selected)}

    @classmethod
    def _extract_plan(cls, candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
        predicate_kinds: dict[str, str] = {}
        predicate_datatypes: dict[str, str | None] = {}
        for item in candidate.get("items", []):
            if not isinstance(item, Mapping) or item.get("item_kind") != "predicate":
                continue
            semantic = item.get("semantic")
            if not isinstance(semantic, Mapping):
                continue
            local = _local_name(semantic.get("predicate"))
            kind = semantic.get("predicate_kind")
            if local is None or kind not in _RESOURCE_TYPES:
                continue
            previous = predicate_kinds.get(local)
            if previous is not None and previous != kind:
                raise ProtocolRetrievalGateError(
                    f"candidate predicate kind is ambiguous for required path {local}"
                )
            predicate_kinds[local] = kind
            predicate_datatypes[local] = cls._range_datatype(semantic.get("range"))
        declarations = cls._candidate_declarations(candidate, predicate_kinds, predicate_datatypes)

        plan: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in candidate.get("items", []):
            if not isinstance(item, Mapping) or item.get("item_kind") != "consumer_query":
                continue
            semantic = item.get("semantic")
            if not isinstance(semantic, Mapping):
                raise ProtocolRetrievalGateError("consumer_query semantic payload is invalid")
            query_id = semantic.get("query_id")
            question = semantic.get("question")
            required_paths = semantic.get("required_paths")
            if (
                not isinstance(query_id, str)
                or not query_id
                or not isinstance(question, str)
                or not question
                or not isinstance(required_paths, list)
                or not required_paths
                or any(not isinstance(path, str) or not path or _local_name(path) != path for path in required_paths)
            ):
                raise ProtocolRetrievalGateError("consumer_query plan is incomplete")
            if len(set(required_paths)) != len(required_paths):
                raise ProtocolRetrievalGateError("consumer_query required_path is duplicated")
            if any(
                (query_id, path) in seen
                for path in required_paths
                if isinstance(path, str)
            ):
                raise ProtocolRetrievalGateError("consumer_query required_path is duplicated")
            bindings = cls._resolve_bindings(required_paths, declarations)
            for path in required_paths:
                key = (query_id, path)
                if key in seen:
                    raise ProtocolRetrievalGateError(
                        f"consumer_query required_path is duplicated: {path}"
                    )
                kind = predicate_kinds.get(path)
                if kind not in _RESOURCE_TYPES:
                    raise ProtocolRetrievalGateError(
                        f"consumer_query required_path has no relation/fact predicate: {path}"
                    )
                seen.add(key)
                plan.append(
                    {
                        "query_id": query_id,
                        "required_path": path,
                        "resource_type": kind,
                        "binding": bindings[path],
                    }
                )
        return plan

    @property
    def required_paths(self) -> tuple[str, ...]:
        return tuple(item["required_path"] for item in self.plan)

    @property
    def enabled(self) -> bool:
        return bool(self.plan)

    def observe(self, record: Mapping[str, Any], artifact_path: Path) -> None:
        """Register one immutable carrier artifact without trusting Agent input."""

        if not isinstance(record, Mapping) or not isinstance(artifact_path, Path):
            raise ProtocolRetrievalGateError("observed retrieval artifact is invalid")
        self._observed_paths.append((_copy(dict(record)), artifact_path))

    @staticmethod
    def _frozen_key(arguments: Mapping[str, Any]) -> str | None:
        if any(field not in arguments for field in _FROZEN_QUERY_FIELDS):
            return None
        values = {field: arguments.get(field) for field in _FROZEN_QUERY_FIELDS}
        return _canonical(values).decode("utf-8")

    @staticmethod
    def _cursor(arguments: Mapping[str, Any]) -> tuple[Any, Any]:
        return arguments.get("context_cursor"), arguments.get("match_cursor")

    @staticmethod
    def _page_cursor(data: Mapping[str, Any]) -> tuple[Any, Any, bool]:
        matches_page = data.get("matches_page")
        context_page = data.get("context_page")
        if not isinstance(matches_page, Mapping) or not isinstance(context_page, Mapping):
            raise ProtocolRetrievalGateError("retrieval response pages are unavailable")
        next_match = matches_page.get("next_match_cursor")
        next_context = context_page.get("next_context_cursor")
        if next_match is not None and not isinstance(next_match, str):
            raise ProtocolRetrievalGateError("retrieval match cursor is invalid")
        if next_context is not None and not isinstance(next_context, str):
            raise ProtocolRetrievalGateError("retrieval context cursor is invalid")
        if bool(matches_page.get("truncated")) != (next_match is not None):
            raise ProtocolRetrievalGateError("retrieval match pagination cursor binding is invalid")
        if bool(context_page.get("truncated")) != (next_context is not None):
            raise ProtocolRetrievalGateError("retrieval context pagination cursor binding is invalid")
        truncated = bool(data.get("truncated"))
        if bool(matches_page.get("truncated")) or bool(context_page.get("truncated")):
            truncated = True
        return next_context, next_match, truncated

    @staticmethod
    def _read_result(record: Mapping[str, Any], artifact_path: Path) -> Mapping[str, Any]:
        response_digest = record.get("response_digest")
        _safe_digest(response_digest, "response_digest")
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ProtocolRetrievalGateError("retrieval artifact is not a regular file")
        try:
            payload = artifact_path.read_bytes()
        except OSError as exc:
            raise ProtocolRetrievalGateError("retrieval artifact is unreadable") from exc
        if hashlib.sha256(payload).hexdigest() != response_digest:
            raise ProtocolRetrievalGateError("retrieval artifact digest does not match")
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolRetrievalGateError("retrieval artifact is not canonical JSON") from exc
        if not isinstance(result, Mapping):
            raise ProtocolRetrievalGateError("retrieval result is not an object")
        structured = result.get("structuredContent")
        if isinstance(structured, Mapping):
            if structured.get("ok") is not True:
                raise ProtocolRetrievalGateError("retrieval MCP result did not report success")
            data = structured.get("data")
        else:
            data = result.get("data")
        if not isinstance(data, Mapping):
            raise ProtocolRetrievalGateError("retrieval result data is unavailable")
        return data

    @staticmethod
    def _validate_response_quality(data: Mapping[str, Any], *, search_mode: str) -> None:
        if data.get("result_status") != "matched":
            raise ProtocolRetrievalGateError("retrieval response is not matched")
        recall = data.get("recall")
        if not isinstance(recall, Mapping) or recall.get("completeness") != "complete":
            raise ProtocolRetrievalGateError("retrieval recall is incomplete or degraded")
        warnings = data.get("warnings", [])
        if warnings is None:
            warnings = []
        if not isinstance(warnings, list):
            raise ProtocolRetrievalGateError("retrieval warnings are invalid")
        for warning in warnings:
            if not isinstance(warning, Mapping):
                continue
            code = str(warning.get("code", "")).lower()
            message = str(warning.get("message", "")).lower()
            # ``matches_truncated`` is a normal page-level pagination signal
            # when the page advertises a valid continuation cursor.  A generic
            # truncated/degraded/incomplete/evidence/lineage warning is not.
            if code == "matches_truncated":
                continue
            if any(token in code or token in message for token in ("lineage", "evidence")):
                # Retrieval warnings are aggregate over all returned resources.
                # A lexical chain may carry an unrelated missing-evidence warning
                # while its candidate-bound statement is fully supported; the
                # row-level evidence/lineage checks below decide that case.  For
                # hybrid, however, keep the conservative fallback contract.
                if search_mode == "hybrid":
                    raise ProtocolRetrievalGateError(
                        f"retrieval response has blocking warning: {code or message}"
                    )
                continue
            if any(
                token in code or token in message
                for token in ("vector_index_missing", "degraded", "incomplete", "truncated")
            ):
                raise ProtocolRetrievalGateError(
                    f"retrieval response has blocking warning: {code or message}"
                )

    @classmethod
    def _split_observed_chains(
        cls,
        entries: list[tuple[dict[str, Any], Path]],
    ) -> list[list[tuple[dict[str, Any], Path]]]:
        """Split repeated path-only requests into independent cursor chains.

        The public retrieval request intentionally carries only one semantic path,
        not a business CQ ID.  If two CQs reuse that path, the Runtime therefore
        cannot label the calls with the CQ.  A fresh ``(None, None)`` request is
        the deterministic chain boundary; each chain is later matched against its
        CQ-specific candidate binding.
        """

        chains: list[list[tuple[dict[str, Any], Path]]] = []
        current: list[tuple[dict[str, Any], Path]] = []
        for item in sorted(entries, key=lambda value: cls._sequence(value[0])):
            arguments = item[0].get("request_arguments")
            cursor = cls._cursor(arguments) if isinstance(arguments, Mapping) else (None, None)
            if current and cursor == (None, None):
                chains.append(current)
                current = []
            current.append(item)
        if current:
            chains.append(current)
        return chains

    @staticmethod
    def _selected_rows(
        data: Mapping[str, Any],
        *,
        required_path: str,
        resource_type: str,
        ontology_id: str,
        binding: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        def resource_matches(actual: Any, expected: Any) -> bool:
            actual_local = _local_name(actual)
            expected_local = _local_name(expected)
            return actual_local is not None and expected_local is not None and actual_local == expected_local

        def literal_matches(actual: Any, expected: Any, datatype: Any) -> bool:
            if isinstance(expected, bool):
                if isinstance(actual, bool):
                    return actual is expected
                if isinstance(actual, str) and actual.strip().lower() in {"true", "false"}:
                    return (actual.strip().lower() == "true") is expected and (
                        datatype is None or str(datatype).endswith("#boolean")
                    )
                return False
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                try:
                    actual_number = float(actual)
                except (TypeError, ValueError):
                    return False
                return actual_number == float(expected)
            return isinstance(actual, str) and actual == expected

        rows: list[dict[str, Any]] = []
        for field in ("primary_matches", "related_context"):
            values = data.get(field, [])
            if not isinstance(values, list):
                raise ProtocolRetrievalGateError(f"retrieval {field} is invalid")
            for row in values:
                if not isinstance(row, Mapping):
                    continue
                # Structural rows, resources, and warnings are intentionally
                # ignored; only selected statement rows can satisfy a path.
                if row.get("target_kind") != "statement":
                    continue
                if row.get("ontology_id") != ontology_id or row.get("kind") != resource_type:
                    continue
                data_row = row.get("data")
                if not isinstance(data_row, Mapping) or _local_name(data_row.get("predicate")) != required_path:
                    continue
                subject = data_row.get("subject")
                object_value = data_row.get("object", data_row.get("value"))
                if not resource_matches(subject, binding.get("subject")):
                    continue
                if binding.get("binding_kind") == "relation":
                    if str(data_row.get("object_type", "")).lower() not in {"uri", "iri", "resource", "bnode"}:
                        continue
                    if not resource_matches(object_value, binding.get("object")):
                        continue
                elif binding.get("binding_kind") == "fact":
                    object_type = data_row.get("object_type")
                    if not isinstance(object_type, str) or object_type.lower() not in {"literal", "value"}:
                        continue
                    if not literal_matches(object_value, binding.get("object"), data_row.get("object_datatype")):
                        continue
                else:
                    continue
                if row.get("evidence_status") != "supported":
                    continue
                evidence_ids = row.get("evidence_reference_ids")
                lineage = row.get("lineage")
                if (
                    not isinstance(evidence_ids, list)
                    or not evidence_ids
                    or any(not isinstance(value, str) or not value for value in evidence_ids)
                    or not isinstance(lineage, Mapping)
                    or lineage.get("status") != "complete"
                ):
                    continue
                statement_id = row.get("id")
                if not isinstance(statement_id, str) or not statement_id:
                    continue
                rows.append(
                    {
                        "id": statement_id,
                        "ontology_id": ontology_id,
                        "predicate": data_row["predicate"],
                        "subject": subject,
                        "object": object_value,
                        "object_type": data_row.get("object_type"),
                        "object_datatype": data_row.get("object_datatype"),
                        "object_language": data_row.get("object_language"),
                        "evidence_reference_ids": sorted(set(evidence_ids)),
                    }
                )
        return rows

    def _candidate_scope(self, model_state: Mapping[str, Any]) -> tuple[str, str]:
        if not isinstance(model_state, Mapping):
            raise ProtocolRetrievalGateError("ordinary retrieval model state is unavailable")
        project_id = model_state.get("project_id")
        ontology_id = model_state.get("ontology_id")
        state_digest = model_state.get("state_digest")
        if (
            not isinstance(project_id, str)
            or not project_id
            or not isinstance(ontology_id, str)
            or not ontology_id
            or not isinstance(state_digest, str)
        ):
            raise ProtocolRetrievalGateError("ordinary retrieval model scope is invalid")
        expected_digest = _digest(
            {
                "schema_version": "r2-3-005-model-state/v1",
                "fields": {
                    field: model_state.get(field)
                    for field in (
                        "project_id",
                        "ontology_id",
                        "workspace_version",
                        "source_signature",
                        "build_session_id",
                        "graph_set_id",
                    )
                },
            }
        )
        if state_digest != expected_digest:
            raise ProtocolRetrievalGateError("ordinary retrieval model state digest is invalid")
        return project_id, ontology_id

    def build_receipt(
        self,
        *,
        runtime_root: Path,
        model_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Validate observed chains and return the canonical typed receipt."""

        if not self.enabled:
            raise ProtocolRetrievalGateError("candidate has no ordinary consumer_query plan")
        project_id, ontology_id = self._candidate_scope(model_state)
        by_path: dict[str, list[tuple[dict[str, Any], Path]]] = {
            path: [] for path in self.required_paths
        }
        expected_kind = {item["required_path"]: item["resource_type"] for item in self.plan}

        # Only exact candidate-bound path queries are eligible.  Broad question
        # queries remain harmlessly unselected rather than becoming accidental
        # evidence for a required path.
        for record, artifact_path in self._observed_paths:
            if record.get("tool") != "query_semantic_context":
                continue
            arguments = record.get("request_arguments")
            if not isinstance(arguments, Mapping):
                continue
            path = arguments.get("query")
            if path not in by_path:
                continue
            if record.get("successful") is not True:
                continue
            if arguments.get("project_id") != project_id or arguments.get("scope_mode") != "ontologies":
                continue
            if arguments.get("ontology_ids") != [ontology_id]:
                continue
            if arguments.get("resource_types") != [expected_kind[path]]:
                continue
            if arguments.get("assertion_types") != ["asserted"]:
                continue
            if arguments.get("search_mode") not in {"hybrid", "lexical"}:
                continue
            # The public MCP accepts either ``query`` or ``queries``.  The
            # ordinary gate binds the singular candidate path explicitly;
            # accepting a second query field would make the request ambiguous.
            if "queries" in arguments:
                continue
            request_digest = record.get("request_digest")
            if not isinstance(request_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", request_digest):
                continue
            if request_digest != _digest(
                {"tool": "query_semantic_context", "arguments": dict(arguments)}
            ):
                continue
            if self._frozen_key(arguments) is None:
                continue
            by_path[path].append((record, artifact_path))

        chains: list[dict[str, Any]] = []
        for plan_item in self.plan:
            path = plan_item["required_path"]
            path_artifacts = by_path[path]
            # Hybrid and lexical requests have distinct frozen tuples and are
            # independent chains.  A degraded hybrid chain may therefore be
            # replaced by a complete lexical chain without weakening the gate.
            grouped: dict[str, list[tuple[dict[str, Any], Path]]] = {}
            for record, artifact_path in path_artifacts:
                arguments = record["request_arguments"]
                key = self._frozen_key(arguments)
                assert key is not None
                grouped.setdefault(key, []).append((record, artifact_path))
            if grouped:
                frozen_without_mode = {
                    _canonical(
                        {
                            key: value
                            for key, value in json.loads(chain_key).items()
                            if key != "search_mode"
                        }
                    ).decode("utf-8")
                    for chain_key in grouped
                }
                if len(frozen_without_mode) != 1:
                    raise ProtocolRetrievalGateError(
                        f"required retrieval path {path} changed its frozen query tuple"
                    )
            completed_chain: dict[str, Any] | None = None
            chain_error: str | None = None
            try:
                grouped_entries = sorted(
                    grouped.values(),
                    key=lambda value: min(self._sequence(item[0]) for item in value),
                )
            except ProtocolRetrievalGateError as exc:
                raise ProtocolRetrievalGateError(
                    f"required retrieval path {path} failed: {exc}"
                ) from exc
            for entries in grouped_entries:
                for chain_entries in self._split_observed_chains(entries):
                    try:
                        candidate_chain = self._validate_chain(
                            chain_entries,
                            required_path=path,
                            resource_type=plan_item["resource_type"],
                            binding=plan_item["binding"],
                            project_id=project_id,
                            ontology_id=ontology_id,
                            runtime_root=runtime_root,
                        )
                    except ProtocolRetrievalGateError as exc:
                        chain_error = str(exc)
                        continue
                    if candidate_chain is not None:
                        completed_chain = candidate_chain
                        break
                if completed_chain is not None:
                    break
            if completed_chain is None:
                detail = chain_error or "no candidate-bound query chain was observed"
                raise ProtocolRetrievalGateError(f"required retrieval path {path} failed: {detail}")
            chains.append(
                {
                    "query_id": plan_item["query_id"],
                    "required_path": path,
                    "resource_type": plan_item["resource_type"],
                    **completed_chain,
                }
            )

        receipt: dict[str, Any] = {
            "schema_version": ORDINARY_RETRIEVAL_RECEIPT_SCHEMA,
            "candidate_revision": self.candidate_revision,
            "candidate_digest": self.candidate_digest,
            "model_state_digest": model_state.get("state_digest"),
            "chains": chains,
            "receipt_digest": None,
        }
        receipt["receipt_digest"] = _digest(receipt)
        return _copy(receipt)

    def _validate_chain(
        self,
        entries: list[tuple[dict[str, Any], Path]],
        *,
        required_path: str,
        resource_type: str,
        binding: Mapping[str, Any],
        project_id: str,
        ontology_id: str,
        runtime_root: Path,
    ) -> dict[str, Any] | None:
        if not entries:
            return None
        first_arguments = entries[0][0].get("request_arguments")
        if not isinstance(first_arguments, Mapping):
            raise ProtocolRetrievalGateError("retrieval request arguments are unavailable")
        expected_frozen = self._frozen_key(first_arguments)
        if expected_frozen is None:
            raise ProtocolRetrievalGateError("retrieval frozen query tuple is incomplete")
        if self._cursor(first_arguments) != (None, None):
            raise ProtocolRetrievalGateError("retrieval chain does not start without a cursor")
        selected: dict[str, dict[str, Any]] = {}
        expected_cursor: tuple[str | None, str | None] = (None, None)
        pending_match_cursor: str | None = None
        artifact_paths: list[str] = []
        terminal = False
        for index, (record, artifact_path) in enumerate(entries):
            sequence = self._sequence(record)
            if index and sequence <= self._sequence(entries[index - 1][0]):
                raise ProtocolRetrievalGateError("retrieval observation sequence is invalid")
            arguments = record.get("request_arguments")
            if not isinstance(arguments, Mapping) or self._frozen_key(arguments) != expected_frozen:
                raise ProtocolRetrievalGateError("retrieval frozen query tuple changed")
            cursor = self._cursor(arguments)
            if cursor != expected_cursor:
                raise ProtocolRetrievalGateError("retrieval cursor continuation is invalid")
            if cursor[0] is not None and cursor[1] is not None:
                raise ProtocolRetrievalGateError("retrieval request exposes both cursors")
            if terminal:
                raise ProtocolRetrievalGateError("retrieval chain continued after terminal cursor")
            expected_path = runtime_root / str(record.get("artifact_path", ""))
            try:
                expected_path.relative_to(runtime_root)
            except ValueError as exc:
                raise ProtocolRetrievalGateError("retrieval artifact is foreign to this run") from exc
            if artifact_path != expected_path:
                raise ProtocolRetrievalGateError("retrieval artifact path is not Runner-owned")
            request_digest = record.get("request_digest")
            response_digest = record.get("response_digest")
            _safe_digest(request_digest, "request_digest")
            _safe_digest(response_digest, "response_digest")
            if str(record.get("artifact_path")) != (
                f"evidence/platform-responses/{request_digest}-{response_digest}.json"
            ):
                raise ProtocolRetrievalGateError("retrieval artifact digest binding is invalid")
            data = self._read_result(record, artifact_path)
            self._validate_response_quality(data, search_mode=str(first_arguments["search_mode"]))
            next_context, next_match, _truncated = self._page_cursor(data)
            rows = self._selected_rows(
                data,
                required_path=required_path,
                resource_type=resource_type,
                ontology_id=ontology_id,
                binding=binding,
            )
            for row in rows:
                selected.setdefault(row["id"], row)
            artifact_paths.append(str(record.get("artifact_path")))
            if next_context is not None:
                # Context expansion always has priority.  The match cursor is
                # retained as a pending cursor and begins the next match page
                # only after the context sub-chain terminates.
                expected_cursor = (next_context, None)
                if next_match is not None:
                    pending_match_cursor = next_match
            elif next_match is not None:
                expected_cursor = (None, next_match)
                pending_match_cursor = None
            elif pending_match_cursor is not None:
                # Some servers omit the pending match cursor on the final
                # context page; the cursor from the match page that opened this
                # context chain remains authoritative.
                expected_cursor = (None, pending_match_cursor)
                pending_match_cursor = None
            else:
                expected_cursor = (None, None)
                terminal = True
            if terminal and data.get("truncated") not in {False, None}:
                raise ProtocolRetrievalGateError("retrieval terminal page is truncated")
            if index == len(entries) - 1 and not terminal:
                raise ProtocolRetrievalGateError("retrieval chain did not reach a terminal cursor")
        if not terminal:
            raise ProtocolRetrievalGateError("retrieval chain did not reach a terminal cursor")
        if not selected:
            raise ProtocolRetrievalGateError("retrieval chain returned no supported statement for path")
        evidence_ids = sorted(
            {
                evidence_id
                for row in selected.values()
                for evidence_id in row["evidence_reference_ids"]
            }
        )
        return {
            "artifact_paths": artifact_paths,
            "statement_ids": sorted(selected),
            "evidence_reference_ids": evidence_ids,
            "ontology_id": ontology_id,
            "project_id": project_id,
            "search_mode": first_arguments["search_mode"],
            "binding": {
                key: binding.get(key)
                for key in (
                    "binding_kind",
                    "subject",
                    "object",
                    "object_type",
                    "object_datatype",
                    "object_language",
                )
            },
            "binding_digest": _digest(
                {
                    key: binding.get(key)
                    for key in (
                        "binding_kind",
                        "subject",
                        "object",
                        "object_type",
                        "object_datatype",
                        "object_language",
                    )
                }
            ),
        }

    @staticmethod
    def _sequence(record: Mapping[str, Any]) -> int:
        value = record.get("observation_sequence")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProtocolRetrievalGateError("retrieval observation sequence is invalid")
        return value
