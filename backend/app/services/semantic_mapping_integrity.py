"""Pure RDF integrity checks for the R4.0-010 relational mapping view.

The compiler checks the shape of one command.  This module checks the final
RDF state after a batch (and, when supplied, its approved reference scope).
It deliberately has no database, settings, or write-path dependency so the
same function can be used by dry-run, canonical writes, and independent
focused tests.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

from rdflib import Graph, RDF, RDFS, URIRef
from rdflib.namespace import OWL


_MAPPING_TYPES = {
    "TableMapping",
    "JoinMapping",
    "EnumValueMeaning",
    "MetricDefinition",
}
_RESOURCE_TYPE_NAMES = _MAPPING_TYPES | {
    "RuleDefinition",
    "SemanticRule",
    "SemanticRuleDefinition",
    "GovernanceResource",
    "ProtectionSet",
}
_PROPERTY_TYPES = {
    str(OWL.ObjectProperty),
    str(OWL.DatatypeProperty),
    str(RDF.Property),
}
_CLASS_TYPES = {str(OWL.Class), str(RDFS.Class)}
_RELATION_TYPES = _PROPERTY_TYPES
_RULE_EXECUTABLE_TYPES = {
    "RuleDefinition",
    "SemanticRule",
    "SemanticRuleDefinition",
}


def _local_name(value: str) -> str:
    return value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _vocab_for(graphs: Iterable[Graph]) -> str | None:
    """Find the op vocabulary from a known mapping rdf:type predicate."""
    for graph in graphs:
        for _subject, predicate, obj in graph:
            if predicate != RDF.type:
                continue
            name = _local_name(str(obj))
            if name in _MAPPING_TYPES:
                return str(obj)[: -len(name)]
        for _subject, predicate, _obj in graph:
            name = _local_name(str(predicate))
            if name in {
                "mappingDefinition", "mappedDefinition", "mappedClass", "columnMappings",
                "joinPath", "mappedProperty", "tableMapping", "metricContexts",
                "semanticValue",
            }:
                return str(predicate)[: -len(name)]
    return None


def _iri(value: Any) -> URIRef | None:
    if isinstance(value, URIRef):
        return value
    if isinstance(value, str) and value:
        return URIRef(value)
    return None


def _objects(graph: Graph, subject: URIRef, predicate: URIRef) -> list[Any]:
    return list(graph.objects(subject, predicate))


def _first(graphs: Iterable[Graph], subject: URIRef, predicate: URIRef) -> Any | None:
    for graph in graphs:
        value = next(iter(graph.objects(subject, predicate)), None)
        if value is not None:
            return value
    return None


def _all_graphs(final_graph: Graph, reference_graph: Graph | None) -> list[Graph]:
    return [final_graph] + ([reference_graph] if reference_graph is not None else [])


def _union_graph(graphs: Iterable[Graph]) -> Graph:
    result = Graph()
    for graph in graphs:
        for triple in graph:
            result.add(triple)
    return result


def _subjects_of_type(graph: Graph, type_iri: URIRef) -> set[URIRef]:
    return {subject for subject in graph.subjects(RDF.type, type_iri) if isinstance(subject, URIRef)}


def _mapping_subjects(graph: Graph, vocab: str) -> dict[str, set[URIRef]]:
    return {
        name: _subjects_of_type(graph, URIRef(f"{vocab}{name}"))
        for name in _MAPPING_TYPES
    }


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return None


def _json_field(
    subject: URIRef,
    predicate: URIRef,
    graphs: list[Graph],
    findings: list[dict[str, Any]],
    path: list[str | int],
) -> tuple[Any | None, bool]:
    value = _first(graphs, subject, predicate)
    if value is None:
        return None, False
    parsed = _json_value(value)
    if parsed is None:
        _finding(
            findings,
            "invalid_mapping_definition",
            "Mapping JSON annotation is not valid JSON",
            subject,
            path,
        )
        return None, True
    return parsed, True


def _finding(
    findings: list[dict[str, Any]],
    code: str,
    message: str,
    subject: URIRef | str,
    path: list[str | int] | None = None,
    *,
    severity: str = "error",
) -> None:
    findings.append(
        {
            "code": code,
            "message": message,
            "subject": str(subject),
            "path": list(path or []),
            "severity": severity,
        }
    )


def _has_subject(graph: Graph, iri: str | URIRef) -> bool:
    subject = URIRef(str(iri))
    return any(graph.triples((subject, None, None)))


def _types(graph: Graph, iri: str | URIRef) -> set[str]:
    subject = URIRef(str(iri))
    return {str(value) for value in graph.objects(subject, RDF.type)}


def _is_mapping(graph: Graph, iri: str | URIRef) -> bool:
    return any(_local_name(value) in _MAPPING_TYPES for value in _types(graph, iri))


def _is_business_rule(graph: Graph, iri: str | URIRef) -> bool:
    """R4.0-005 rules are ordinary data resources, never executable Rules."""
    subject = URIRef(str(iri))
    for predicate in graph.predicates(subject=subject):
        if _local_name(str(predicate)) != "semanticDefinition":
            continue
        for value in graph.objects(subject, predicate):
            parsed = _json_value(value)
            if isinstance(parsed, dict) and parsed.get("semantic_role") == "rule":
                return True
    return False


def _reference_target(
    graph: Graph,
    iri: Any,
    expected: str,
    *,
    allow_class_for_definition: bool = False,
) -> tuple[bool, str]:
    """Resolve a reference without assigning business meaning to its label."""
    if not isinstance(iri, URIRef):
        return False, "reference is not an IRI"
    if not _has_subject(graph, iri):
        return False, "referenced resource does not exist"
    types = _types(graph, iri)
    if expected == "mapping":
        return _is_mapping(graph, iri), "reference is not a mapping resource"
    if expected == "table":
        ok = any(_local_name(value) == "TableMapping" for value in types)
        return ok, "reference is not a TableMapping"
    if expected == "join":
        ok = any(_local_name(value) == "JoinMapping" for value in types)
        return ok, "reference is not a JoinMapping"
    if expected == "class":
        return bool(types & _CLASS_TYPES), "reference is not a Class"
    if expected == "property":
        return bool(types & _PROPERTY_TYPES), "reference is not a Property"
    if expected == "relation":
        return bool(types & _RELATION_TYPES), "reference is not a relation type"
    if expected == "definition":
        if _is_mapping(graph, iri) or any(
            _local_name(value) in _RESOURCE_TYPE_NAMES - _MAPPING_TYPES for value in types
        ):
            return False, "mapped_definition must reference a business definition or Class"
        if allow_class_for_definition and types & _CLASS_TYPES:
            return True, ""
        return True, ""
    if expected == "rule":
        if any(_local_name(value) in _RULE_EXECUTABLE_TYPES for value in types):
            return False, "rule reference points to an executable platform RuleDefinition"
        if not _is_business_rule(graph, iri):
            return False, "reference is not a business rule data resource"
        return True, ""
    return _has_subject(graph, iri), "referenced resource does not exist"


def _validate_reference(
    findings: list[dict[str, Any]],
    graph: Graph,
    subject: URIRef,
    value: Any,
    expected: str,
    path: list[str | int],
    *,
    allow_class_for_definition: bool = False,
) -> bool:
    ok, reason = _reference_target(
        graph,
        value,
        expected,
        allow_class_for_definition=allow_class_for_definition,
    )
    if not ok:
        _finding(
            findings,
            "invalid_resource_reference",
            f"{'.'.join(str(part) for part in path)}: {reason}",
            subject,
            path,
        )
    return ok


def _columns_for_table(
    table: dict[str, Any] | None,
) -> set[str]:
    if not table:
        return set()
    return {
        str(entry.get("column"))
        for entry in table.get("column_mappings", [])
        if isinstance(entry, dict) and isinstance(entry.get("column"), str)
    }


def _column_property_for_table(table: dict[str, Any] | None, column: str) -> str | None:
    if not table:
        return None
    for entry in table.get("column_mappings", []):
        if isinstance(entry, dict) and entry.get("column") == column:
            value = entry.get("property_iri")
            return str(value) if isinstance(value, str) else None
    return None


def _parse_table_records(
    graphs: list[Graph], vocab: str
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Return mapping IRI records and table-name candidates.

    The first graph is the final owner graph, so an update in that graph wins
    over an approved reference copy of the same subject.
    """
    by_iri: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    type_iri = URIRef(f"{vocab}TableMapping")
    subjects: list[URIRef] = []
    seen: set[URIRef] = set()
    for graph in graphs:
        for subject in graph.subjects(RDF.type, type_iri):
            if not isinstance(subject, URIRef) or subject in seen:
                continue
            seen.add(subject)
            subjects.append(subject)
    for subject in subjects:
        table_name = _first(graphs, subject, URIRef(f"{vocab}tableName"))
        columns_value = _first(graphs, subject, URIRef(f"{vocab}columnMappings"))
        columns = _json_value(columns_value)
        record = {
            "iri": str(subject),
            "table_name": str(table_name) if table_name is not None else None,
            "column_mappings": columns if isinstance(columns, list) else [],
        }
        by_iri[str(subject)] = record
        if record["table_name"]:
            by_name[str(record["table_name"])].append(record)
    return by_iri, by_name


def _validate_mapping_definition(
    findings: list[dict[str, Any]],
    subject: URIRef,
    kind: str,
    value: Any,
    graph: Graph,
    tables: dict[str, dict[str, Any]],
    vocab: str,
    path: list[str | int],
) -> None:
    if not isinstance(value, dict):
        _finding(findings, "invalid_mapping_definition", "mapping_definition must be an object", subject, path)
        return
    allowed: dict[str, set[str]] = {
        "TableMapping": {
            "source_key", "schema_version", "row_grain", "record_key_columns",
            "object_key_columns", "identifiers", "field_meanings", "row_scope",
        },
        "JoinMapping": {
            "step_semantics", "relationship_meaning", "duplicate_risk", "execution_prerequisite",
        },
        "EnumValueMeaning": {"conversion_rule_iri"},
        "MetricDefinition": {"contexts"},
    }
    unknown = sorted(set(value) - allowed[kind])
    for field in unknown:
        _finding(
            findings,
            "invalid_mapping_definition",
            f"mapping_definition contains unsupported field: {field}",
            subject,
            [*path, field],
        )

    def nullable_string(field: str) -> None:
        if field in value and value[field] is not None and not isinstance(value[field], str):
            _finding(findings, "invalid_mapping_definition", f"{field} must be a string or null", subject, [*path, field])

    if kind == "TableMapping":
        if "source_key" not in value or not isinstance(value.get("source_key"), str) or not value.get("source_key"):
            _finding(findings, "invalid_mapping_definition", "table mapping source_key is required", subject, [*path, "source_key"])
        for field in ("schema_version", "row_grain", "row_scope"):
            nullable_string(field)
        columns = _columns_for_table(tables.get(str(subject)))
        for field in ("record_key_columns", "object_key_columns"):
            if field not in value:
                continue
            entries = value[field]
            if entries is not None and (
                not isinstance(entries, list)
                or any(not isinstance(entry, str) for entry in entries)
            ):
                _finding(findings, "invalid_mapping_definition", f"{field} must be an array of columns or null", subject, [*path, field])
            elif isinstance(entries, list):
                for index, column in enumerate(entries):
                    if column not in columns:
                        _finding(findings, "join_path_not_mapped", f"{field} column is not mapped: {column}", subject, [*path, field, index])
        identifiers = value.get("identifiers")
        if identifiers is not None:
            if not isinstance(identifiers, list):
                _finding(findings, "invalid_mapping_definition", "identifiers must be an array", subject, [*path, "identifiers"])
            else:
                for index, entry in enumerate(identifiers):
                    item_path = [*path, "identifiers", index]
                    if not isinstance(entry, dict):
                        _finding(findings, "invalid_mapping_definition", "identifier must be an object", subject, item_path)
                        continue
                    unknown_fields = set(entry) - {"columns", "kind", "property_iri", "scope", "correspondence"}
                    for field in sorted(unknown_fields):
                        _finding(findings, "invalid_mapping_definition", f"identifier has unsupported field: {field}", subject, [*item_path, field])
                    entry_columns = entry.get("columns")
                    if not isinstance(entry_columns, list) or not entry_columns:
                        _finding(findings, "invalid_mapping_definition", "identifier.columns must be non-empty", subject, [*item_path, "columns"])
                    else:
                        for col_index, column in enumerate(entry_columns):
                            if column not in columns:
                                _finding(findings, "join_path_not_mapped", f"identifier column is not mapped: {column}", subject, [*item_path, "columns", col_index])
                    if entry.get("kind") not in {"technical", "business", "external", "unknown"}:
                        _finding(findings, "invalid_mapping_definition", "identifier.kind is invalid", subject, [*item_path, "kind"])
                    if entry.get("property_iri") is not None:
                        _validate_reference(findings, graph, subject, _iri(entry.get("property_iri")), "property", [*item_path, "property_iri"])
                    for field in ("scope", "correspondence"):
                        if field in entry and entry[field] is not None and not isinstance(entry[field], str):
                            _finding(findings, "invalid_mapping_definition", f"identifier.{field} must be a string or null", subject, [*item_path, field])
        meanings = value.get("field_meanings")
        if meanings is not None:
            if not isinstance(meanings, list):
                _finding(findings, "invalid_mapping_definition", "field_meanings must be an array", subject, [*path, "field_meanings"])
            else:
                for index, entry in enumerate(meanings):
                    item_path = [*path, "field_meanings", index]
                    if not isinstance(entry, dict):
                        _finding(findings, "invalid_mapping_definition", "field meaning must be an object", subject, item_path)
                        continue
                    unknown_fields = set(entry) - {"column", "source_meaning", "source_unit", "target_unit", "time_semantics", "null_meaning", "conversion_rule_iri"}
                    for field in sorted(unknown_fields):
                        _finding(findings, "invalid_mapping_definition", f"field meaning has unsupported field: {field}", subject, [*item_path, field])
                    column = entry.get("column")
                    if not isinstance(column, str) or not column:
                        _finding(findings, "invalid_mapping_definition", "field meaning column is required", subject, [*item_path, "column"])
                    elif column not in columns:
                        _finding(findings, "join_path_not_mapped", f"field meaning column is not mapped: {column}", subject, [*item_path, "column"])
                    for field in ("source_meaning", "source_unit", "target_unit", "time_semantics", "null_meaning"):
                        if field in entry and entry[field] is not None and not isinstance(entry[field], str):
                            _finding(findings, "invalid_mapping_definition", f"field meaning {field} must be a string or null", subject, [*item_path, field])
                    if entry.get("conversion_rule_iri") is not None:
                        _validate_reference(findings, graph, subject, _iri(entry.get("conversion_rule_iri")), "rule", [*item_path, "conversion_rule_iri"])
    elif kind == "JoinMapping":
        for field in ("relationship_meaning", "duplicate_risk", "execution_prerequisite"):
            nullable_string(field)
        steps = value.get("step_semantics")
        if steps is not None:
            if not isinstance(steps, list):
                _finding(findings, "invalid_mapping_definition", "step_semantics must be an array", subject, [*path, "step_semantics"])
            else:
                seen_indices: set[int] = set()
                for index, entry in enumerate(steps):
                    item_path = [*path, "step_semantics", index]
                    if not isinstance(entry, dict):
                        _finding(findings, "invalid_mapping_definition", "step_semantics item must be an object", subject, item_path)
                        continue
                    allowed_step = {"step_index", "join_type", "cardinality", "additional_condition", "condition_rule_iri"}
                    for field in sorted(set(entry) - allowed_step):
                        _finding(findings, "invalid_mapping_definition", f"step_semantics has unsupported field: {field}", subject, [*item_path, field])
                    step_index = entry.get("step_index")
                    if not isinstance(step_index, int) or isinstance(step_index, bool) or step_index < 0 or step_index in seen_indices:
                        _finding(findings, "invalid_mapping_definition", "step_index must be a unique non-negative integer", subject, [*item_path, "step_index"])
                    elif step_index not in seen_indices:
                        seen_indices.add(step_index)
                    if entry.get("join_type") is not None and entry.get("join_type") not in {"inner", "left", "right", "full", "unknown"}:
                        _finding(findings, "invalid_mapping_definition", "join_type is invalid", subject, [*item_path, "join_type"])
                    if entry.get("cardinality") is not None and entry.get("cardinality") not in {"one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"}:
                        _finding(findings, "invalid_mapping_definition", "cardinality is invalid", subject, [*item_path, "cardinality"])
                    if entry.get("additional_condition") is not None and not isinstance(entry.get("additional_condition"), str):
                        _finding(findings, "invalid_mapping_definition", "additional_condition must be a string or null", subject, [*item_path, "additional_condition"])
                    if entry.get("condition_rule_iri") is not None:
                        _validate_reference(findings, graph, subject, _iri(entry.get("condition_rule_iri")), "rule", [*item_path, "condition_rule_iri"])
    elif kind == "EnumValueMeaning":
        if "conversion_rule_iri" in value and value.get("conversion_rule_iri") is not None:
            _validate_reference(findings, graph, subject, _iri(value.get("conversion_rule_iri")), "rule", [*path, "conversion_rule_iri"])
    elif kind == "MetricDefinition":
        contexts = value.get("contexts")
        if contexts is None:
            return
        if not isinstance(contexts, list):
            _finding(findings, "invalid_mapping_definition", "contexts must be an array", subject, [*path, "contexts"])
            return
        seen_keys: set[str] = set()
        for index, context in enumerate(contexts):
            context_path = [*path, "contexts", index]
            if not isinstance(context, dict):
                _finding(findings, "invalid_mapping_definition", "context must be an object", subject, context_path)
                continue
            allowed_context = {"context_key", "applicability", "base_mapping_iri", "base_role", "join_mapping_iris", "property_bindings", "counted_identity", "duplicate_handling", "conversion_rule_iris"}
            for field in sorted(set(context) - allowed_context):
                _finding(findings, "invalid_mapping_definition", f"context has unsupported field: {field}", subject, [*context_path, field])
            key = context.get("context_key")
            if not isinstance(key, str) or not key:
                _finding(findings, "invalid_mapping_definition", "context_key is required", subject, [*context_path, "context_key"])
            elif key in seen_keys:
                _finding(findings, "invalid_mapping_definition", "context_key must be unique", subject, [*context_path, "context_key"])
            else:
                seen_keys.add(key)
            for field in ("applicability", "base_role", "duplicate_handling"):
                if field in context and context[field] is not None and not isinstance(context[field], str):
                    _finding(findings, "invalid_mapping_definition", f"{field} must be a string or null", subject, [*context_path, field])
            base_mapping = context.get("base_mapping_iri")
            if base_mapping is not None:
                _validate_reference(findings, graph, subject, _iri(base_mapping), "table", [*context_path, "base_mapping_iri"])
            joins = context.get("join_mapping_iris")
            if joins is not None:
                if not isinstance(joins, list):
                    _finding(findings, "invalid_mapping_definition", "join_mapping_iris must be an array", subject, [*context_path, "join_mapping_iris"])
                else:
                    for join_index, join in enumerate(joins):
                        _validate_reference(findings, graph, subject, _iri(join), "join", [*context_path, "join_mapping_iris", join_index])
            for field, required_fields in (
                ("property_bindings", {"property_iri", "table_mapping_iri", "role", "column"}),
                ("counted_identity", {"table_mapping_iri", "role", "columns"}),
            ):
                if field not in context:
                    continue
                members = context[field]
                if members is None:
                    continue
                if not isinstance(members, list):
                    _finding(findings, "invalid_mapping_definition", f"{field} must be an array or null", subject, [*context_path, field])
                    continue
                for member_index, member in enumerate(members):
                    member_path = [*context_path, field, member_index]
                    if not isinstance(member, dict):
                        _finding(findings, "invalid_mapping_definition", f"{field} item must be an object", subject, member_path)
                        continue
                    for missing in sorted(required_fields - set(member)):
                        _finding(findings, "invalid_mapping_definition", f"{field} item is missing {missing}", subject, [*member_path, missing])
                    table_iri = _iri(member.get("table_mapping_iri"))
                    table_ok = _validate_reference(findings, graph, subject, table_iri, "table", [*member_path, "table_mapping_iri"])
                    table = tables.get(str(table_iri)) if table_ok and table_iri is not None else None
                    role = member.get("role")
                    if not isinstance(role, str) or not role:
                        _finding(findings, "invalid_mapping_definition", "role must be a non-empty string", subject, [*member_path, "role"])
                    if field == "property_bindings":
                        _validate_reference(findings, graph, subject, _iri(member.get("property_iri")), "property", [*member_path, "property_iri"])
                        column = member.get("column")
                        if not isinstance(column, str) or not column:
                            _finding(findings, "invalid_mapping_definition", "column is required", subject, [*member_path, "column"])
                        elif column not in _columns_for_table(table):
                            _finding(findings, "join_path_not_mapped", f"column is not mapped: {column}", subject, [*member_path, "column"])
                        elif _column_property_for_table(table, column) not in {None, str(member.get("property_iri"))}:
                            _finding(findings, "invalid_resource_reference", "property binding does not match the mapped column property", subject, [*member_path, "property_iri"])
                    else:
                        columns = member.get("columns")
                        if not isinstance(columns, list) or not columns:
                            _finding(findings, "invalid_mapping_definition", "columns must be a non-empty array", subject, [*member_path, "columns"])
                        elif table is not None:
                            for column_index, column in enumerate(columns):
                                if column not in _columns_for_table(table):
                                    _finding(findings, "join_path_not_mapped", f"column is not mapped: {column}", subject, [*member_path, "columns", column_index])
            conversions = context.get("conversion_rule_iris")
            if conversions is not None:
                if not isinstance(conversions, list):
                    _finding(findings, "invalid_mapping_definition", "conversion_rule_iris must be an array", subject, [*context_path, "conversion_rule_iris"])
                else:
                    for conversion_index, conversion in enumerate(conversions):
                        _validate_reference(findings, graph, subject, _iri(conversion), "rule", [*context_path, "conversion_rule_iris", conversion_index])


def _validate_table_columns(
    findings: list[dict[str, Any]],
    subject: URIRef,
    table: dict[str, Any],
    graph: Graph,
    vocab: str,
) -> None:
    mappings = table.get("column_mappings")
    if not isinstance(mappings, list) or not mappings:
        _finding(findings, "invalid_mapping_definition", "columnMappings must be a non-empty array", subject, ["column_mappings"])
        return
    seen_columns: set[str] = set()
    for index, entry in enumerate(mappings):
        path = ["column_mappings", index]
        if not isinstance(entry, dict):
            _finding(findings, "invalid_mapping_definition", "column mapping must be an object", subject, path)
            continue
        unknown = sorted(set(entry) - {"property_iri", "column", "role"})
        for field in unknown:
            _finding(findings, "invalid_mapping_definition", f"column mapping has unsupported field: {field}", subject, [*path, field])
        column = entry.get("column")
        if not isinstance(column, str) or not column:
            _finding(findings, "invalid_mapping_definition", "column is required", subject, [*path, "column"])
            continue
        if column in seen_columns:
            _finding(findings, "invalid_mapping_definition", f"column is repeated: {column}", subject, [*path, "column"])
        seen_columns.add(column)
        role = entry.get("role", "value")
        if role not in {"value", "business_key"}:
            _finding(findings, "invalid_mapping_definition", "column role is invalid", subject, [*path, "role"])
        if role == "business_key" and not entry.get("property_iri"):
            _finding(findings, "invalid_mapping_definition", "business_key requires property_iri", subject, [*path, "property_iri"])
        if entry.get("property_iri") is not None:
            _validate_reference(findings, graph, subject, _iri(entry.get("property_iri")), "property", [*path, "property_iri"])


def _validate_join_path(
    findings: list[dict[str, Any]],
    subject: URIRef,
    path_value: Any,
    graph: Graph,
    tables: dict[str, dict[str, Any]],
    tables_by_name: dict[str, list[dict[str, Any]]],
    vocab: str,
) -> None:
    path = ["join_path"]
    if not isinstance(path_value, list) or not path_value:
        _finding(findings, "invalid_mapping_definition", "joinPath must be a non-empty array", subject, path)
        return
    shape: str | None = None
    for index, step in enumerate(path_value):
        step_path = [*path, index]
        if not isinstance(step, dict):
            _finding(findings, "invalid_mapping_definition", "join path step must be an object", subject, step_path)
            continue
        old_keys = {"from_table", "to_table", "from_columns", "to_columns"}
        new_keys = {"from_mapping_iri", "to_mapping_iri", "from_role", "to_role", "from_columns", "to_columns"}
        keys = set(step)
        current_shape = "table" if keys == old_keys else "mapping" if keys == new_keys else None
        if current_shape is None:
            _finding(findings, "invalid_mapping_definition", "join path step has an unsupported shape", subject, step_path)
            continue
        if shape is None:
            shape = current_shape
        elif shape != current_shape:
            _finding(findings, "invalid_mapping_definition", "join path cannot mix table and mapping references", subject, step_path)
        from_columns = step.get("from_columns")
        to_columns = step.get("to_columns")
        if not isinstance(from_columns, list) or not from_columns:
            _finding(findings, "invalid_mapping_definition", "from_columns must be non-empty", subject, [*step_path, "from_columns"])
        if not isinstance(to_columns, list) or not to_columns:
            _finding(findings, "invalid_mapping_definition", "to_columns must be non-empty", subject, [*step_path, "to_columns"])
        if isinstance(from_columns, list) and isinstance(to_columns, list) and len(from_columns) != len(to_columns):
            _finding(findings, "invalid_mapping_definition", "join column arrays must have equal length", subject, step_path)
        if current_shape == "table":
            for side, table_name, columns_key in (
                ("from", step.get("from_table"), "from_columns"),
                ("to", step.get("to_table"), "to_columns"),
            ):
                candidates = tables_by_name.get(str(table_name), [])
                if len(candidates) == 0:
                    _finding(findings, "join_path_not_mapped", f"{side}_table is not mapped: {table_name}", subject, [*step_path, f"{side}_table"])
                    continue
                if len(candidates) > 1:
                    _finding(findings, "ambiguous_mapping_reference", f"{side}_table resolves to multiple TableMappings: {table_name}", subject, [*step_path, f"{side}_table"])
                    continue
                columns = _columns_for_table(candidates[0])
                for column_index, column in enumerate(step.get(columns_key, [])):
                    if column not in columns:
                        _finding(findings, "join_path_not_mapped", f"{side} column is not mapped: {column}", subject, [*step_path, columns_key, column_index])
        else:
            for side, mapping_key, role_key, columns_key in (
                ("from", "from_mapping_iri", "from_role", "from_columns"),
                ("to", "to_mapping_iri", "to_role", "to_columns"),
            ):
                mapping_iri = _iri(step.get(mapping_key))
                ok = _validate_reference(findings, graph, subject, mapping_iri, "table", [*step_path, mapping_key])
                table = tables.get(str(mapping_iri)) if ok and mapping_iri is not None else None
                role = step.get(role_key)
                if not isinstance(role, str) or not role:
                    _finding(findings, "invalid_mapping_definition", f"{role_key} must be a non-empty role", subject, [*step_path, role_key])
                for column_index, column in enumerate(step.get(columns_key, [])):
                    if column not in _columns_for_table(table):
                        _finding(findings, "join_path_not_mapped", f"{side} column is not mapped: {column}", subject, [*step_path, columns_key, column_index])
        if index + 1 < len(path_value):
            next_step = path_value[index + 1]
            if isinstance(next_step, dict) and current_shape == "table" and set(next_step) == old_keys:
                if step.get("to_table") != next_step.get("from_table"):
                    _finding(findings, "join_path_not_mapped", "join path steps are not adjacent", subject, step_path)
            elif isinstance(next_step, dict) and current_shape == "mapping" and set(next_step) == new_keys:
                if step.get("to_mapping_iri") != next_step.get("from_mapping_iri") or step.get("to_role") != next_step.get("from_role"):
                    _finding(findings, "join_path_not_mapped", "join path mapping/role steps are not adjacent", subject, step_path)


def _validate_rule_ref_fields(
    findings: list[dict[str, Any]],
    subject: URIRef,
    graph: Graph,
    vocab: str,
    predicate_name: str,
) -> None:
    predicate = URIRef(f"{vocab}{predicate_name}")
    for value in graph.objects(subject, predicate):
        _validate_reference(findings, graph, subject, value, "rule", [predicate_name])


def _join_roles_by_mapping(
    graph: Graph, join_iri: URIRef, vocab: str
) -> dict[str, set[str]]:
    """Return the explicit mapping/role endpoints declared by a join path."""
    path_value = _json_value(
        _first([graph], join_iri, URIRef(f"{vocab}joinPath"))
    )
    roles: dict[str, set[str]] = defaultdict(set)
    if not isinstance(path_value, list):
        return roles
    new_keys = {
        "from_mapping_iri", "to_mapping_iri", "from_role", "to_role",
        "from_columns", "to_columns",
    }
    for step in path_value:
        if not isinstance(step, dict) or set(step) != new_keys:
            continue
        from_mapping = _iri(step.get("from_mapping_iri"))
        to_mapping = _iri(step.get("to_mapping_iri"))
        from_role = step.get("from_role")
        to_role = step.get("to_role")
        if from_mapping is not None and isinstance(from_role, str) and from_role:
            roles[str(from_mapping)].add(from_role)
        if to_mapping is not None and isinstance(to_role, str) and to_role:
            roles[str(to_mapping)].add(to_role)
    return roles


def _validate_metric_context_roles(
    findings: list[dict[str, Any]],
    subject: URIRef,
    definition: Any,
    graph: Graph,
    vocab: str,
    path: list[str | int],
) -> None:
    """Ensure context bindings use roles selected by the context's paths."""
    if not isinstance(definition, dict):
        return
    contexts = definition.get("contexts")
    if not isinstance(contexts, list):
        return
    for index, context in enumerate(contexts):
        if not isinstance(context, dict):
            continue
        context_path = [*path, "contexts", index]
        base_mapping = _iri(context.get("base_mapping_iri"))
        base_role = context.get("base_role")
        roles: dict[str, set[str]] = defaultdict(set)
        if base_mapping is not None and isinstance(base_role, str) and base_role:
            roles[str(base_mapping)].add(base_role)
        joins = context.get("join_mapping_iris")
        if isinstance(joins, list):
            for join in joins:
                join_iri = _iri(join)
                if join_iri is None:
                    continue
                for mapping, mapping_roles in _join_roles_by_mapping(
                    graph, join_iri, vocab
                ).items():
                    roles[mapping].update(mapping_roles)
        for field in ("property_bindings", "counted_identity"):
            members = context.get(field)
            if not isinstance(members, list):
                continue
            for member_index, member in enumerate(members):
                if not isinstance(member, dict):
                    continue
                table_mapping = _iri(member.get("table_mapping_iri"))
                role = member.get("role")
                if table_mapping is None or not isinstance(role, str) or not role:
                    continue
                allowed_roles = roles.get(str(table_mapping), set())
                if role in allowed_roles:
                    continue
                _finding(
                    findings,
                    "invalid_mapping_definition",
                    "context role is not present in its base mapping or selected join paths",
                    subject,
                    [*context_path, field, member_index, "role"],
                )


def _validate_join_step_semantics(
    findings: list[dict[str, Any]],
    subject: URIRef,
    join_path_value: Any,
    definition: Any,
    path: list[str | int],
) -> None:
    """Check that declared step semantics point at actual join steps."""
    if not isinstance(definition, dict):
        return
    steps = definition.get("step_semantics")
    if not isinstance(steps, list) or not isinstance(join_path_value, list):
        return
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_index = step.get("step_index")
        if isinstance(step_index, int) and not isinstance(step_index, bool):
            if step_index >= len(join_path_value):
                _finding(
                    findings,
                    "invalid_mapping_definition",
                    "step_semantics.step_index does not reference a join_path step",
                    subject,
                    [*path, "step_semantics", index, "step_index"],
                )


def validate_mapping_graph(
    final_graph: Graph,
    original_graph: Graph | None = None,
    reference_graph: Graph | None = None,
) -> list[dict[str, Any]]:
    """Validate relational mapping resources in ``final_graph``.

    ``reference_graph`` supplies only approved/project-scoped definitions and
    mapping records used to resolve references.  Findings are emitted only for
    mapping subjects present in ``final_graph``; callers can therefore map a
    finding subject back to the current batch item.  ``original_graph`` is the
    pre-change owner view and is used for immutable mapped targets and reverse
    deletion checks.
    """
    if not isinstance(final_graph, Graph):
        raise TypeError("final_graph must be an rdflib.Graph")
    reference = reference_graph if isinstance(reference_graph, Graph) else None
    originals = original_graph if isinstance(original_graph, Graph) else None
    resolution_graph = _union_graph(_all_graphs(final_graph, reference))
    vocab = _vocab_for(
        [graph for graph in (final_graph, reference, originals) if graph is not None]
    )
    if vocab is None:
        return []
    final_subjects = _mapping_subjects(final_graph, vocab)
    tables, tables_by_name = _parse_table_records([final_graph] + ([reference] if reference is not None else []), vocab)
    findings: list[dict[str, Any]] = []

    def annotation(subject: URIRef, kind: str) -> None:
        value = _first([final_graph], subject, URIRef(f"{vocab}mappingDefinition"))
        if value is not None:
            parsed = _json_value(value)
            if parsed is None:
                _finding(findings, "invalid_mapping_definition", "mappingDefinition is not valid JSON", subject, ["mapping_definition"])
            else:
                _validate_mapping_definition(findings, subject, kind, parsed, resolution_graph, tables, vocab, ["mapping_definition"])

    # Target definitions and table column closure.
    for subject in sorted(final_subjects["TableMapping"], key=str):
        mapped_class = _objects(final_graph, subject, URIRef(f"{vocab}mappedClass"))
        mapped_definition = _objects(final_graph, subject, URIRef(f"{vocab}mappedDefinition"))
        if len(mapped_class) + len(mapped_definition) != 1:
            _finding(findings, "invalid_resource_reference", "TableMapping must declare exactly one mappedClass or mappedDefinition", subject, ["mapped_class_iri"])
        if mapped_class:
            _validate_reference(findings, resolution_graph, subject, mapped_class[0], "class", ["mapped_class_iri"])
        if mapped_definition:
            _validate_reference(findings, resolution_graph, subject, mapped_definition[0], "definition", ["mapped_definition_iri"], allow_class_for_definition=True)
        table = tables.get(str(subject))
        if table is None:
            table = {"iri": str(subject), "column_mappings": []}
        _validate_table_columns(findings, subject, table, resolution_graph, vocab)
        annotation(subject, "TableMapping")

    # Immutable target identity is a write-time invariant.  A mapping update
    # can replace ordinary fields, but it cannot retarget the same IRI.
    if originals is not None:
        for kind, subjects in final_subjects.items():
            predicate_names = ("mappedClass", "mappedDefinition") if kind == "TableMapping" else ()
            for subject in subjects:
                old_values = {
                    str(value)
                    for predicate_name in predicate_names
                    for value in originals.objects(subject, URIRef(f"{vocab}{predicate_name}"))
                }
                new_values = {
                    str(value)
                    for predicate_name in predicate_names
                    for value in final_graph.objects(subject, URIRef(f"{vocab}{predicate_name}"))
                }
                if old_values and old_values != new_values:
                    old_class_values = set(
                        str(item)
                        for item in originals.objects(
                            subject, URIRef(f"{vocab}mappedClass")
                        )
                    )
                    new_class_values = set(
                        str(item)
                        for item in final_graph.objects(
                            subject, URIRef(f"{vocab}mappedClass")
                        )
                    )
                    changed_path = (
                        ["mapped_class_iri"]
                        if old_class_values or new_class_values
                        else ["mapped_definition_iri"]
                    )
                    _finding(
                        findings,
                        "mapping_target_changed",
                        "mapped definition/class cannot change for an existing mapping IRI",
                        subject,
                        changed_path,
                    )

    for subject in sorted(final_subjects["JoinMapping"], key=str):
        relation_type = _first([final_graph], subject, URIRef(f"{vocab}mappedRelationType"))
        _validate_reference(findings, resolution_graph, subject, relation_type, "relation", ["relation_type_iri"])
        path_value = _first([final_graph], subject, URIRef(f"{vocab}joinPath"))
        parsed_path = _json_value(path_value)
        _validate_join_path(findings, subject, parsed_path, resolution_graph, tables, tables_by_name, vocab)
        annotation(subject, "JoinMapping")
        mapping_definition = _json_value(
            _first([final_graph], subject, URIRef(f"{vocab}mappingDefinition"))
        )
        _validate_join_step_semantics(
            findings,
            subject,
            parsed_path,
            mapping_definition,
            ["mapping_definition"],
        )

    for subject in sorted(final_subjects["EnumValueMeaning"], key=str):
        property_iri = _first([final_graph], subject, URIRef(f"{vocab}mappedProperty"))
        _validate_reference(findings, resolution_graph, subject, property_iri, "property", ["property_iri"])
        table_mapping = _objects(final_graph, subject, URIRef(f"{vocab}tableMapping"))
        column = _objects(final_graph, subject, URIRef(f"{vocab}columnName"))
        if bool(table_mapping) != bool(column):
            missing_field = "table_mapping_iri" if column else "column"
            _finding(
                findings,
                "invalid_mapping_definition",
                "tableMapping and columnName must be supplied together",
                subject,
                [missing_field],
            )
        if table_mapping and column:
            table_iri = table_mapping[0]
            if _validate_reference(findings, resolution_graph, subject, table_iri, "table", ["table_mapping_iri"]):
                table = tables.get(str(table_iri))
                column_name = str(column[0])
                if column_name not in _columns_for_table(table):
                    _finding(findings, "join_path_not_mapped", f"enum column is not mapped: {column_name}", subject, ["column"])
                elif _column_property_for_table(table, column_name) not in {None, str(property_iri)}:
                    _finding(findings, "invalid_resource_reference", "enum scoped column does not map to property_iri", subject, ["property_iri"])
        semantic_value = _objects(final_graph, subject, URIRef(f"{vocab}semanticValue"))
        if len(semantic_value) > 1:
            _finding(findings, "invalid_resource_reference", "EnumValueMeaning must carry at most one semanticValue", subject, ["semantic_value"])
        for value in semantic_value:
            if not _has_subject(resolution_graph, value):
                if originals is not None and _has_subject(originals, value):
                    _finding(findings, "semantic_value_dangling", "semanticValue target was deleted while the enum meaning remains", subject, ["semantic_value"])
                else:
                    _finding(
                        findings,
                        "invalid_resource_reference",
                        "semanticValue does not reference an existing semantic data resource",
                        subject,
                        ["semantic_value"],
                    )
            elif _is_mapping(resolution_graph, value):
                _finding(findings, "invalid_resource_reference", "semanticValue must reference a non-mapping semantic data resource", subject, ["semantic_value"])
        annotation(subject, "EnumValueMeaning")

    for subject in sorted(final_subjects["MetricDefinition"], key=str):
        for index, value in enumerate(_json_value(_first([final_graph], subject, URIRef(f"{vocab}metricGrain"))) or []):
            _validate_reference(findings, resolution_graph, subject, _iri(value), "property", ["grain", index])
        for field, expected, payload_field in (
            ("metricTimeField", "property", "time_field"),
            ("metricMeasure", "property", "measure_property_iri"),
        ):
            value = _first([final_graph], subject, URIRef(f"{vocab}{field}"))
            if value is not None:
                _validate_reference(findings, resolution_graph, subject, value, expected, [payload_field])
        filters = _json_value(_first([final_graph], subject, URIRef(f"{vocab}metricFilters")))
        if filters is not None:
            if not isinstance(filters, list):
                _finding(findings, "invalid_mapping_definition", "metricFilters must be an array", subject, ["filters"])
            else:
                for index, entry in enumerate(filters):
                    if isinstance(entry, dict):
                        _validate_reference(findings, resolution_graph, subject, _iri(entry.get("field")), "property", ["filters", index, "field"])
        annotation(subject, "MetricDefinition")
        mapping_definition = _json_value(
            _first([final_graph], subject, URIRef(f"{vocab}mappingDefinition"))
        )
        _validate_metric_context_roles(
            findings,
            subject,
            mapping_definition,
            resolution_graph,
            vocab,
            ["mapping_definition"],
        )

    # Scoped and legacy enum uniqueness.  Scope is intentionally a separate
    # key space so a legacy unscoped meaning never shadows a field-scoped one.
    enum_subjects = set().union(*(_mapping_subjects(resolution_graph, vocab).get("EnumValueMeaning", set()),)) if resolution_graph else set()
    groups: dict[tuple[str, ...], list[URIRef]] = defaultdict(list)
    for subject in enum_subjects:
        scope_graphs = _all_graphs(final_graph, reference)
        property_value = _first(scope_graphs, subject, URIRef(f"{vocab}mappedProperty"))
        enum_value = _first(scope_graphs, subject, URIRef(f"{vocab}enumValue"))
        if property_value is None or enum_value is None:
            continue
        table_value = _first(scope_graphs, subject, URIRef(f"{vocab}tableMapping"))
        column_value = _first(scope_graphs, subject, URIRef(f"{vocab}columnName"))
        if table_value is not None and column_value is not None:
            key = ("scoped", str(table_value), str(column_value), str(property_value), str(enum_value))
        else:
            key = ("unscoped", str(property_value), str(enum_value))
        groups[key].append(subject)
    for key, members in groups.items():
        if len(members) < 2:
            continue
        for subject in members:
            if subject in final_subjects["EnumValueMeaning"]:
                _finding(findings, "resource_already_exists", f"duplicate enum meaning for key {key[1:]}", subject, ["enum_value"])

    # Reverse references created by deleting a definition/table/column are
    # represented by the same final-state checks above.  This small scan adds
    # the precise reverse path for old table-name join references when the
    # deleted table only existed in the original owner view.
    if originals is not None:
        old_tables = _parse_table_records([originals], vocab)[0]
        deleted_tables = set(old_tables) - set(tables)
        for subject in final_subjects["JoinMapping"]:
            path_value = _json_value(_first([final_graph], subject, URIRef(f"{vocab}joinPath")))
            if not isinstance(path_value, list):
                continue
            for index, step in enumerate(path_value):
                if not isinstance(step, dict):
                    continue
                for key in ("from_mapping_iri", "to_mapping_iri"):
                    if step.get(key) in deleted_tables:
                        _finding(findings, "join_path_not_mapped", "join path references a deleted TableMapping", subject, ["join_path", index, key])
    return findings


__all__ = ["validate_mapping_graph"]
