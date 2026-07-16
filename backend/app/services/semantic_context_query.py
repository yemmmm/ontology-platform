"""Deterministic unified semantic context retrieval for external Agents."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import re
import unicodedata
from typing import Any, Iterable

from rdflib import Literal, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import SemanticRuleDefinitionModel, SemanticRuleModel
from app.repositories.rdf_store import RdfStoreRepository
from app.services.ontology_lineage import LineageTargetNotFound, OntologyLineageService
from app.services.semantic_lineage_identity import statement_id_for_quad
from app.services.semantic_query_scope import SemanticQueryScope, SemanticQueryScopeResolver
from app.services.semantic_shape_endpoint_service import SemanticShapeEndpointService
from app.services.semantic_sparql_templates import (
    semantic_context_candidates_query,
    semantic_context_neighborhood_query,
)


RESOURCE_TYPE_ORDER = ("concept", "instance", "relation", "fact", "rule", "operation")
RESOURCE_TYPES = set(RESOURCE_TYPE_ORDER)
ASSERTION_TYPES = {"asserted", "derived"}
_KIND_ORDER = {kind: index for index, kind in enumerate(RESOURCE_TYPE_ORDER)}
_CLASS_TYPES = {
    "http://www.w3.org/2002/07/owl#Class",
    "http://www.w3.org/2000/01/rdf-schema#Class",
}
_RELATION_TYPES = {
    "http://www.w3.org/2002/07/owl#ObjectProperty",
    "http://www.w3.org/2002/07/owl#DatatypeProperty",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
}
_METADATA_PREDICATES = {
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://www.w3.org/2004/02/skos/core#altLabel",
    "http://purl.org/dc/terms/description",
}


class SemanticContextQueryError(RuntimeError):
    status_code = 400
    code = "invalid_query"


class SemanticContextQueryService:
    """Run one lexical candidate, ranking, neighborhood, and lineage pipeline."""

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticQueryScopeResolver,
        lineage_service: OntologyLineageService | None = None,
        shape_endpoint: SemanticShapeEndpointService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.lineage_service = lineage_service or OntologyLineageService(session, rdf_store)
        self.shape_endpoint = shape_endpoint or SemanticShapeEndpointService(
            session, rdf_store, scope_resolver.settings
        )

    def query(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        query: str,
        resource_types: list[str] | None = None,
        assertion_types: list[str] | None = None,
        depth: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        text, terms = normalize_query_text(query)
        _validate_filters(resource_types, assertion_types, depth, limit)
        selected_resource_types = set(resource_types or RESOURCE_TYPES)
        selected_assertion_types = set(assertion_types or ASSERTION_TYPES)
        scope = self.scope_resolver.resolve(
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids,
        )
        warnings = [*scope.warnings, *_ontology_warnings(scope)]
        if not scope.graph_iris:
            return self._response(text, terms, scope, [], [], False, warnings)

        candidate_limit = min(5000, max(500, limit * 50))
        candidate_fetch_limit = candidate_limit + 1
        raw_result = self.rdf_store.query_sparql(
            semantic_context_candidates_query(
                scope.graph_to_ontology, terms, candidate_fetch_limit
            ),
            timeout_seconds=10,
            limit=candidate_fetch_limit,
        )
        rows = _bindings(raw_result.result)
        candidate_scan_truncated = raw_result.truncated or len(rows) > candidate_limit
        rows = rows[:candidate_limit]
        candidates = self._rdf_candidates(rows, scope, text, terms)
        candidates.extend(self._rule_candidates(scope, text, terms))
        candidates = [
            item
            for item in candidates
            if item["kind"] in selected_resource_types
            and _assertion_filter_value(item["assertion_kind"]) in selected_assertion_types
        ]
        candidates.sort(key=lambda item: _sort_key(item, scope))
        candidates = _dedupe_items(candidates)

        primary = candidates[:limit]
        related: list[dict[str, Any]] = []
        remaining = limit - len(primary)
        related_truncated = False
        if (
            depth
            and primary
            and "fact" in selected_resource_types
            and "asserted" in selected_assertion_types
        ):
            shape_items = self._shape_constraint_items(primary, scope, limit=remaining + 1)
            related_truncated = len(shape_items) > remaining
            related = shape_items[:remaining]
            remaining -= len(related)
        if depth and primary and not related_truncated:
            neighborhood = self._expand_neighborhood(
                primary,
                scope,
                depth=depth,
                limit=remaining + 1,
                resource_types=selected_resource_types,
                assertion_types=selected_assertion_types,
            )
            related_truncated = len(neighborhood) > remaining
            related.extend(neighborhood[:remaining])

        truncated = bool(
            candidate_scan_truncated
            or len(candidates) > len(primary)
            or related_truncated
        )
        if truncated:
            warnings.append(
                {"code": "context_truncated", "message": "Semantic context was truncated."}
            )
        if _has_ambiguous_match(primary):
            warnings.append(
                {
                    "code": "ambiguous_match",
                    "message": "Multiple primary matches share the same normalized label.",
                }
            )
        decorated_primary = [self._decorate(item, scope) for item in primary]
        decorated_related = [self._decorate(item, scope) for item in related]
        warnings.extend(
            warning
            for item in [*decorated_primary, *decorated_related]
            for warning in item["warnings"]
        )
        return self._response(
            text,
            terms,
            scope,
            decorated_primary,
            decorated_related,
            truncated,
            warnings,
        )

    def _rdf_candidates(
        self,
        rows: list[dict[str, Any]],
        scope: SemanticQueryScope,
        text: str,
        terms: list[str],
    ) -> list[dict[str, Any]]:
        resources: dict[tuple[str, str], dict[str, Any]] = {}
        statements: list[dict[str, Any]] = []
        for row in rows:
            graph = _value(row, "graph")
            subject = _value(row, "subject")
            predicate = _value(row, "predicate")
            if not graph or not subject or graph not in scope.graph_to_ontology:
                continue
            ontology_id = scope.graph_to_ontology[graph]
            assertion_kind = scope.graph_assertion_kinds.get(graph, "asserted")
            if _binding_type(row, "subject") == "uri":
                key = (ontology_id, subject)
                resource = resources.setdefault(
                    key,
                    {
                        "id": subject,
                        "kind": "instance",
                        "ontology_id": ontology_id,
                        "iri": subject,
                        "label": None,
                        "aliases": [],
                        "description": None,
                        "types": set(),
                        "distance": 0,
                        "assertion_kind": assertion_kind,
                        "data": {},
                    },
                )
                resource["label"] = resource["label"] or _value(row, "subjectLabel")
                for alias in _split_aggregate(_value(row, "aliases")):
                    if alias not in resource["aliases"]:
                        resource["aliases"].append(alias)
                resource["description"] = resource["description"] or _value(row, "description")
                resource["types"].update(_split_aggregate(_value(row, "subjectTypes")))

                matched_field = _value(row, "matchedField")
                matched_value = _value(row, "matchedValue")
                if matched_field == "label" and matched_value:
                    resource["label"] = resource["label"] or matched_value
                elif matched_field == "alias" and matched_value:
                    if matched_value not in resource["aliases"]:
                        resource["aliases"].append(matched_value)
                elif matched_field == "description" and matched_value:
                    resource["description"] = resource["description"] or matched_value

            if not predicate or predicate in _METADATA_PREDICATES:
                continue
            statement = self._statement_item(row, scope, distance=0)
            if statement is None:
                continue
            predicate_label = (
                _value(row, "matchedValue")
                if _value(row, "matchedField") == "predicate"
                else None
            ) or _local_name(predicate)
            object_value = _value(row, "object")
            score = _best_match(
                text,
                terms,
                [
                    ("predicate", predicate_label, 550, "property_name"),
                    ("identifier", _local_name(predicate), 600, "identifier"),
                    ("value", object_value, 400, "fact_value"),
                ],
            )
            if score:
                statement["match"] = score
                statements.append(statement)

        candidates: list[dict[str, Any]] = []
        for resource in resources.values():
            types = resource.pop("types")
            if types & _CLASS_TYPES:
                resource["kind"] = "concept"
            elif types & _RELATION_TYPES:
                resource["kind"] = "relation"
            resource["data"] = {"rdf_types": sorted(types)}
            resource["label"] = resource["label"] or _local_name(resource["iri"])
            match = _best_match(
                text,
                terms,
                [
                    ("label", resource["label"], 1000, "exact_label"),
                    *(
                        ("alias", alias, 900, "exact_alias")
                        for alias in resource["aliases"]
                    ),
                    ("identifier", resource["iri"], 600, "identifier"),
                    ("description", resource["description"], 450, "description"),
                ],
            )
            if match:
                resource["match"] = match
                candidates.append(resource)
        candidates.extend(statements)
        return candidates

    def _shape_constraint_items(
        self,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        scope_by_ontology = {item.ontology_id: item for item in scope.ontologies}
        for match in primary:
            if match["kind"] not in {"concept", "instance"}:
                continue
            target_classes = (
                [match["iri"]]
                if match["kind"] == "concept"
                else list(match.get("data", {}).get("rdf_types", []))
            )
            ontology_scope = scope_by_ontology[match["ontology_id"]]
            for target_class in target_classes:
                try:
                    guidance = self.shape_endpoint.read_merged_guidance(
                        ontology_scope.graph_set_id, target_class
                    )
                except Exception:
                    continue
                for field in guidance.get("fields", []):
                    if not isinstance(field, dict):
                        continue
                    path = str(field.get("path") or field.get("name") or "constraint")
                    item_id = hashlib.sha256(
                        f"{match['ontology_id']}:{target_class}:{path}".encode("utf-8")
                    ).hexdigest()
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                    public_constraint = {
                        key: value
                        for key, value in field.items()
                        if key
                        in {
                            "path",
                            "name",
                            "label",
                            "datatype",
                            "class_iri",
                            "min_count",
                            "max_count",
                            "pattern",
                            "enumeration",
                            "description",
                            "required",
                            "provenance",
                        }
                    }
                    items.append(
                        {
                            "id": item_id,
                            "kind": "fact",
                            "ontology_id": match["ontology_id"],
                            "iri": path if path.startswith(("http://", "https://", "urn:")) else None,
                            "label": str(field.get("label") or field.get("name") or _local_name(path)),
                            "aliases": [],
                            "description": field.get("description"),
                            "data": {
                                "target_class": target_class,
                                "constraint": public_constraint,
                            },
                            "distance": 1,
                            "assertion_kind": "asserted",
                            "match": {
                                "score": 275,
                                "matched_terms": [],
                                "matched_fields": ["constraint"],
                                "reasons": ["shape_constraint"],
                            },
                        }
                    )
                    if len(items) >= limit:
                        return items
        return items

    def _rule_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str]
    ) -> list[dict[str, Any]]:
        ontology_ids = [item.ontology_id for item in scope.ontologies]
        if not ontology_ids:
            return []
        rows = self.session.execute(
            select(SemanticRuleModel, SemanticRuleDefinitionModel)
            .join(
                SemanticRuleDefinitionModel,
                SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
            )
            .where(
                SemanticRuleModel.ontology_id.in_(ontology_ids),
                SemanticRuleModel.status == "active",
                SemanticRuleDefinitionModel.status == "active",
            )
            .order_by(SemanticRuleModel.ontology_id, SemanticRuleModel.rule_iri)
        )
        candidates: list[dict[str, Any]] = []
        for rule, definition in rows:
            description = (definition.rule_metadata or {}).get("description")
            match = _best_match(
                text,
                terms,
                [
                    ("label", definition.name, 1000, "exact_label"),
                    ("identifier", rule.rule_iri, 600, "identifier"),
                    ("description", description, 450, "description"),
                ],
            )
            if not match:
                continue
            candidates.append(
                {
                    "id": rule.rule_iri,
                    "kind": "rule",
                    "ontology_id": rule.ontology_id,
                    "iri": rule.rule_iri,
                    "label": definition.name,
                    "aliases": [],
                    "description": description,
                    "data": {
                        "definition_id": definition.id,
                        "version": definition.version,
                        "language": definition.language,
                        "input_roles": definition.input_roles,
                        "output_kind": definition.output_kind,
                    },
                    "distance": 0,
                    "assertion_kind": "asserted",
                    "match": match,
                }
            )
        return candidates

    def _expand_neighborhood(
        self,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        *,
        depth: int,
        limit: int,
        resource_types: set[str],
        assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        frontier = sorted(
            {
                item["iri"]
                for item in primary
                if item.get("iri") and str(item["iri"]).startswith(("http://", "https://", "urn:"))
            }
        )
        seen_anchors = set(frontier)
        seen_items = {item["id"] for item in primary}
        related: list[dict[str, Any]] = []
        for distance in range(1, depth + 1):
            if not frontier or len(related) >= limit:
                break
            query_limit = min(5000, max(100, (limit - len(related)) * 20))
            result = self.rdf_store.query_sparql(
                semantic_context_neighborhood_query(scope.graph_iris, frontier, query_limit),
                timeout_seconds=10,
                limit=query_limit,
            )
            next_frontier: set[str] = set()
            for row in _bindings(result.result):
                item = self._statement_item(row, scope, distance=distance)
                if item is None or item["id"] in seen_items:
                    continue
                if item["kind"] not in resource_types:
                    continue
                if _assertion_filter_value(item["assertion_kind"]) not in assertion_types:
                    continue
                item["match"] = {
                    "score": max(1, 300 - distance * 50),
                    "matched_terms": [],
                    "matched_fields": ["neighborhood"],
                    "reasons": ["relation_neighborhood"],
                }
                related.append(item)
                seen_items.add(item["id"])
                for key in ("subject", "object"):
                    value = item["data"].get(key)
                    if isinstance(value, str) and value.startswith(("http://", "https://", "urn:")):
                        if value not in seen_anchors:
                            next_frontier.add(value)
                if len(related) >= limit:
                    break
            seen_anchors.update(next_frontier)
            frontier = sorted(next_frontier)
        return related

    def _statement_item(
        self, row: dict[str, Any], scope: SemanticQueryScope, *, distance: int
    ) -> dict[str, Any] | None:
        graph = _value(row, "graph")
        subject = _value(row, "subject")
        predicate = _value(row, "predicate")
        object_value = _value(row, "object")
        if not graph or not subject or not predicate or object_value is None:
            return None
        if graph not in scope.graph_to_ontology or predicate in _METADATA_PREDICATES:
            return None
        object_ntriples = _binding_n3(row.get("object"))
        try:
            statement_id = statement_id_for_quad(subject, predicate, object_ntriples, graph)
        except ValueError:
            return None
        is_relation = _binding_type(row, "object") in {"uri", "bnode"}
        subject_label = _value(row, "subjectLabel") or _local_name(subject)
        predicate_label = _value(row, "predicateLabel") or _local_name(predicate)
        return {
            "id": statement_id,
            "kind": "relation" if is_relation else "fact",
            "ontology_id": scope.graph_to_ontology[graph],
            "iri": predicate,
            "label": f"{subject_label} {predicate_label}".strip(),
            "aliases": [],
            "description": None,
            "data": {
                "subject": subject,
                "predicate": predicate,
                "object": object_value,
                "object_type": _binding_type(row, "object"),
                "object_datatype": _binding_attribute(row, "object", "datatype"),
                "object_language": _binding_attribute(row, "object", "xml:lang"),
            },
            "distance": distance,
            "assertion_kind": scope.graph_assertion_kinds.get(graph, "asserted"),
        }

    def _decorate(self, item: dict[str, Any], scope: SemanticQueryScope) -> dict[str, Any]:
        target_type = "statement" if item["kind"] in {"fact", "relation"} else item["kind"]
        if target_type not in {"statement", "rule"}:
            target_type = "resource"
        try:
            lineage = self.lineage_service.get_lineage(
                ontology_id=item["ontology_id"],
                target_type=target_type,
                target_id=item["id"],
                include_history=False,
                max_depth=1,
                limit=50,
            )
            evidence_ids = sorted(set(_collect_evidence_ids(lineage.get("items", []))))
            lineage_status = lineage.get("lineage_status", "missing")
            evidence_status = lineage.get("evidence_status", "missing")
            dependency_status = lineage.get("dependency_evidence_status")
            proof_level = _find_first(lineage.get("items", []), "proof_level")
            lineage_warnings = lineage.get("warnings", [])
        except LineageTargetNotFound:
            evidence_ids = []
            lineage_status = "missing"
            evidence_status = (
                "not_applicable" if item["assertion_kind"] != "asserted" else "missing"
            )
            dependency_status = "missing" if item["assertion_kind"] != "asserted" else None
            proof_level = None
            lineage_warnings = []

        derived_state = None
        if item["assertion_kind"] != "asserted":
            ontology = next(
                entry for entry in scope.ontologies if entry.ontology_id == item["ontology_id"]
            )
            derived_kind = "reasoning" if item["assertion_kind"] == "owl_inferred" else "rule"
            descriptor = ontology.derived_state.get(derived_kind, {})
            derived_state = {
                "kind": derived_kind,
                "status": descriptor.get("status"),
                "run_id": descriptor.get("run_id"),
                "proof_level": proof_level,
                "dependency_evidence_status": dependency_status,
            }
            evidence_ids = []
            evidence_status = "not_applicable"

        item_warnings: list[dict[str, str]] = []
        if evidence_status == "missing":
            item_warnings.append({"code": "evidence_missing", "message": "Evidence is missing."})
        if lineage_status in {"missing", "partial"}:
            item_warnings.append(
                {
                    "code": f"lineage_{lineage_status}",
                    "message": f"Lineage is {lineage_status}.",
                }
            )
        if derived_state and derived_state.get("status") == "stale":
            item_warnings.append(
                {"code": "derived_result_stale", "message": "Derived result is stale."}
            )
        item_warnings.extend(
            {"code": str(code), "message": str(code).replace("_", " ").capitalize() + "."}
            for code in lineage_warnings
            if code in {"lineage_truncated", "legacy_lineage_unavailable"}
        )
        return {
            **item,
            "assertion_type": _assertion_filter_value(item["assertion_kind"]),
            "evidence_reference_ids": evidence_ids,
            "evidence_status": evidence_status,
            "lineage": {
                "target_type": target_type,
                "target_id": item["id"],
                "status": lineage_status,
            },
            "derived_state": derived_state,
            "warnings": _dedupe_warnings(item_warnings),
        }

    @staticmethod
    def _response(
        text: str,
        terms: list[str],
        scope: SemanticQueryScope,
        primary: list[dict[str, Any]],
        related: list[dict[str, Any]],
        truncated: bool,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "query": {"text": text, "normalized_terms": terms},
            "result_status": "matched" if primary else "no_match",
            "scope": scope.public_dict(),
            "primary_matches": primary,
            "related_context": related,
            "truncated": truncated,
            "warnings": _dedupe_warnings(warnings),
        }


def normalize_query_text(query: str) -> tuple[str, list[str]]:
    if not isinstance(query, str):
        raise SemanticContextQueryError("query must be a string")
    text = query.strip()
    if not text:
        raise SemanticContextQueryError("query must be non-empty")
    if len(text) > 2000:
        raise SemanticContextQueryError("query may contain at most 2000 characters")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    identifier_split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    identifier_split = unicodedata.normalize("NFKC", identifier_split).casefold()
    tokens = re.findall(r"[\w]+", identifier_split.replace("_", " ").replace("-", " "))
    terms: list[str] = [normalized]
    terms.extend(tokens)
    for token in tokens:
        if not re.search(r"[\u3400-\u9fff]", token):
            continue
        for size in range(min(6, len(token)), 1, -1):
            terms.extend(token[index : index + size] for index in range(len(token) - size + 1))
    unique = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    unique.sort(key=lambda term: (-len(term), normalized.find(term), term))
    return text, unique[:64]


def _validate_filters(
    resource_types: list[str] | None,
    assertion_types: list[str] | None,
    depth: int,
    limit: int,
) -> None:
    if resource_types is not None and (
        not resource_types or not set(resource_types) <= RESOURCE_TYPES
    ):
        raise SemanticContextQueryError("resource_types contains an unsupported value")
    if assertion_types is not None and (
        not assertion_types or not set(assertion_types) <= ASSERTION_TYPES
    ):
        raise SemanticContextQueryError("assertion_types contains an unsupported value")
    if not 0 <= depth <= 3:
        raise SemanticContextQueryError("depth must be between 0 and 3")
    if not 1 <= limit <= 100:
        raise SemanticContextQueryError("limit must be between 1 and 100")


def _best_match(
    text: str,
    terms: list[str],
    fields: Iterable[tuple[str, Any, int, str]],
) -> dict[str, Any] | None:
    normalized_query = _normalize_value(text)
    matches: list[tuple[int, str, str, str]] = []
    for field, raw_value, base_score, exact_reason in fields:
        value = _normalize_value(raw_value)
        if not value:
            continue
        matched_terms = [term for term in terms if term == value or term in value or value in term]
        if not matched_terms:
            continue
        exact = value == normalized_query or value in terms
        score = base_score if exact else max(1, base_score - 250)
        reason = exact_reason if exact else f"{field}_contains"
        for term in matched_terms:
            matches.append((score, term, field, reason))
    if not matches:
        return None
    score = max(item[0] for item in matches)
    return {
        "score": score,
        "matched_terms": sorted({item[1] for item in matches}, key=lambda value: (-len(value), value)),
        "matched_fields": sorted({item[2] for item in matches}),
        "reasons": sorted({item[3] for item in matches if item[0] == score}),
    }


def _normalize_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _bindings(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results", {}).get("bindings", [])
    return rows if isinstance(rows, list) else []


def _value(row: dict[str, Any], key: str) -> str | None:
    binding = row.get(key)
    if not isinstance(binding, dict):
        return None
    value = binding.get("value")
    return str(value) if value is not None else None


def _binding_type(row: dict[str, Any], key: str) -> str | None:
    binding = row.get(key)
    return str(binding.get("type")) if isinstance(binding, dict) and binding.get("type") else None


def _binding_attribute(row: dict[str, Any], key: str, attribute: str) -> str | None:
    binding = row.get(key)
    if not isinstance(binding, dict) or binding.get(attribute) is None:
        return None
    return str(binding[attribute])


def _split_aggregate(value: str | None) -> list[str]:
    return [item for item in (value or "").split("|") if item]


def _binding_n3(binding: Any) -> str:
    if not isinstance(binding, dict):
        return Literal("").n3()
    value = str(binding.get("value", ""))
    if binding.get("type") == "uri":
        return URIRef(value).n3()
    if binding.get("type") == "bnode":
        return f"_:{value}"
    return Literal(
        value,
        lang=binding.get("xml:lang"),
        datatype=URIRef(binding["datatype"]) if binding.get("datatype") else None,
    ).n3()


def _local_name(iri: str) -> str:
    return re.split(r"[/#:]", iri.rstrip("/#:"))[-1] or iri


def _assertion_filter_value(assertion_kind: str) -> str:
    return "asserted" if assertion_kind == "asserted" else "derived"


def _sort_key(item: dict[str, Any], scope: SemanticQueryScope) -> tuple[Any, ...]:
    ontology_order = {entry.ontology_id: index for index, entry in enumerate(scope.ontologies)}
    stale_penalty = 100 if _item_is_stale(item, scope) else 0
    return (
        -(item["match"]["score"] - stale_penalty),
        ontology_order.get(item["ontology_id"], len(ontology_order)),
        _KIND_ORDER.get(item["kind"], 99),
        _normalize_value(item.get("label")),
        item["id"],
    )


def _item_is_stale(item: dict[str, Any], scope: SemanticQueryScope) -> bool:
    if item["assertion_kind"] == "asserted":
        return False
    ontology = next(entry for entry in scope.ontologies if entry.ontology_id == item["ontology_id"])
    kind = "reasoning" if item["assertion_kind"] == "owl_inferred" else "rule"
    return ontology.derived_state.get(kind, {}).get("status") == "stale"


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["ontology_id"], item["id"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _has_ambiguous_match(items: list[dict[str, Any]]) -> bool:
    labels: dict[str, set[str]] = defaultdict(set)
    for item in items:
        label = _normalize_value(item.get("label"))
        if label:
            labels[label].add(f"{item['ontology_id']}:{item['id']}")
    return any(len(ids) > 1 for ids in labels.values())


def _collect_evidence_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        references = value.get("evidence_references")
        if isinstance(references, list):
            result.extend(
                str(reference["id"])
                for reference in references
                if isinstance(reference, dict) and reference.get("id")
            )
        for nested in value.values():
            result.extend(_collect_evidence_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            result.extend(_collect_evidence_ids(nested))
    return result


def _find_first(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value and value[key] is not None:
            return value[key]
        for nested in value.values():
            found = _find_first(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_first(nested, key)
            if found is not None:
                return found
    return None


def _ontology_warnings(scope: SemanticQueryScope) -> list[dict[str, str]]:
    return [warning for ontology in scope.ontologies for warning in ontology.warnings]


def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning["code"], warning["message"])
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result
