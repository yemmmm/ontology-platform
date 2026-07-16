"""Ontology-scoped unified lineage query shared by REST and MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from rdflib import BNode, Literal, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    CompetencyQuestionModel,
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    FactEvidenceBindingModel,
    ModelingBatchModel,
    ModelingItemModel,
    OntologyModel,
    SemanticDerivedResultPointerModel,
    SemanticEditAuditModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticReasoningRunModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
    SemanticRuleRunModel,
    SemanticStatementOccurrenceModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.repositories.semantic_lineage_repository import SemanticLineageRepository
from app.services.semantic_lineage_identity import (
    canonical_iri,
    occurrence_id_for,
    statement_id_for_quad,
)


class OntologyLineageError(RuntimeError):
    status_code = 400


class LineageTargetNotFound(OntologyLineageError):
    status_code = 404


@dataclass
class _ExpansionState:
    max_depth: int
    limit: int
    seen: set[str] = field(default_factory=set)
    count: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


class OntologyLineageService:
    TARGET_TYPES = {"statement", "resource", "rule"}

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository | None = None,
        authorize_read: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.repository = SemanticLineageRepository(session)
        self._authorize_read = authorize_read or (lambda _ontology_id, _actor: None)

    def get_lineage(
        self,
        *,
        ontology_id: str,
        target_type: str,
        target_id: str,
        include_history: bool = False,
        max_depth: int = 3,
        limit: int = 100,
        actor: Any = None,
    ) -> dict[str, Any]:
        if target_type not in self.TARGET_TYPES:
            raise OntologyLineageError("target_type must be statement, resource, or rule")
        if not 0 <= max_depth <= 5:
            raise OntologyLineageError("max_depth must be between 0 and 5")
        if not 1 <= limit <= 200:
            raise OntologyLineageError("limit must be between 1 and 200")
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise LineageTargetNotFound("Ontology was not found")
        self._authorize_read(ontology_id, actor)
        scope = self._scope(ontology_id)
        state = _ExpansionState(max_depth=max_depth, limit=limit)

        if target_type == "rule":
            items = self._rule_items(
                ontology=ontology,
                rule_iri=target_id,
                include_history=include_history,
                state=state,
            )
        else:
            canonical_target = target_id
            if target_type == "resource":
                canonical_target = canonical_iri(target_id)
                rows = self.repository.list_occurrences(
                    ontology_id=ontology_id,
                    subject_iri=canonical_target,
                    include_history=include_history,
                    limit=limit + 1,
                )
            else:
                rows = self.repository.list_occurrences(
                    ontology_id=ontology_id,
                    statement_id=target_id,
                    include_history=include_history,
                    limit=limit + 1,
                )
            rows = self._filter_current(rows, scope, include_history)
            if len(rows) > limit:
                state.truncated = True
                rows = rows[:limit]
            items = [
                self._statement_item(row, ontology, state, depth=0)
                for row in rows
                if state.count < state.limit
            ]
            if not items:
                legacy = self._legacy_items(
                    ontology=ontology,
                    target_type=target_type,
                    target_id=canonical_target,
                    scope=scope,
                    limit=limit + 1,
                )
                if len(legacy) > limit:
                    state.truncated = True
                    legacy = legacy[:limit]
                items.extend(legacy)
                if legacy:
                    state.warnings.append("legacy_lineage_unavailable")
        if not items:
            raise LineageTargetNotFound("Lineage target was not found in this Ontology")

        lineage_status = self._aggregate_lineage_status(items)
        evidence_status = self._aggregate_evidence_status(items)
        dependency_status = self._aggregate_dependency_status(items)
        if state.truncated:
            state.warnings.append("lineage_truncated")
        warnings = list(dict.fromkeys([*state.warnings, *self._item_warnings(items)]))
        return {
            "ontology_id": ontology_id,
            "target": {"type": target_type, "id": target_id},
            "lineage_status": lineage_status,
            "evidence_status": evidence_status,
            "dependency_evidence_status": dependency_status,
            "items": items,
            "warnings": warnings,
            "truncated": state.truncated,
        }

    def _scope(self, ontology_id: str) -> dict[str, Any]:
        graph_set = self.session.scalar(
            select(SemanticGraphSetModel).where(
                SemanticGraphSetModel.scope_type == "ontology",
                SemanticGraphSetModel.scope_id == ontology_id,
                SemanticGraphSetModel.is_default.is_(True),
            )
        )
        asserted_graphs: set[str] = set()
        current_derived: set[str] = set()
        if graph_set is not None:
            asserted_graphs = set(
                self.session.scalars(
                    select(SemanticGraphSetMemberModel.graph_iri).where(
                        SemanticGraphSetMemberModel.graph_set_id == graph_set.id
                    )
                )
            )
            current_derived = set(
                self.session.scalars(
                    select(SemanticDerivedResultPointerModel.result_graph_iri).where(
                        SemanticDerivedResultPointerModel.graph_set_id == graph_set.id,
                        SemanticDerivedResultPointerModel.status == "current",
                    )
                )
            )
        return {
            "graph_set": graph_set,
            "asserted_graphs": asserted_graphs,
            "current_derived": current_derived,
            "current_graphs": asserted_graphs | current_derived,
        }

    @staticmethod
    def _filter_current(rows, scope, include_history):
        if include_history:
            return rows
        current_graphs = scope["current_graphs"]
        if not current_graphs:
            return rows
        return [row for row in rows if row.status == "active" and row.graph_iri in current_graphs]

    def _statement_item(
        self,
        occurrence: SemanticStatementOccurrenceModel,
        ontology: OntologyModel,
        state: _ExpansionState,
        *,
        depth: int,
    ) -> dict[str, Any]:
        if occurrence.id in state.seen:
            return {"item_kind": "statement_reference", "occurrence_id": occurrence.id}
        if state.count >= state.limit:
            state.truncated = True
            return {"item_kind": "statement_reference", "occurrence_id": occurrence.id}
        state.seen.add(occurrence.id)
        state.count += 1
        origins = self.repository.origins_for(occurrence.id)
        origin_payload, context, derivation, origin_warnings = self._resolve_origins(
            occurrence, origins, ontology
        )
        premise_ids = self.repository.premise_ids_for(occurrence.id)
        premise_items: list[dict[str, Any]] = []
        if premise_ids:
            if depth >= state.max_depth:
                state.truncated = True
                premise_items = [
                    {"item_kind": "statement_reference", "occurrence_id": premise_id}
                    for premise_id in premise_ids
                ]
            else:
                for premise_id in premise_ids:
                    premise = self.repository.get_occurrence(premise_id)
                    if premise is None or premise.ontology_id != ontology.id:
                        continue
                    premise_items.append(
                        self._statement_item(premise, ontology, state, depth=depth + 1)
                    )
        if derivation is not None:
            derivation["premises"] = premise_items
        derived = occurrence.assertion_kind != "asserted"
        evidence_status = (
            "not_applicable"
            if derived
            else ("supported" if context["evidence_references"] else "missing")
        )
        dependency_status = self._dependency_status(derivation, derived)
        has_legacy = any(origin.origin_kind == "legacy_unknown" for origin in origins)
        if not origins:
            lineage_status = "missing"
        elif has_legacy:
            lineage_status = "partial"
        elif derived and derivation is None:
            lineage_status = "partial"
        else:
            lineage_status = "complete"
        pointer = self.session.scalar(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.result_graph_iri == occurrence.graph_iri
            )
        )
        stale = bool(pointer is not None and pointer.status != "current")
        stale_reason = None
        if stale and pointer is not None:
            stale_reason = (pointer.pointer_metadata or {}).get("stale_reason") or pointer.status
        warnings = list(origin_warnings)
        if has_legacy:
            warnings.append("legacy_lineage_unavailable")
        return {
            "item_kind": "statement",
            "statement_id": occurrence.statement_id,
            "occurrence_id": occurrence.id,
            "statement": {
                "subject": occurrence.subject_iri,
                "predicate": occurrence.predicate_iri,
                "object": occurrence.object_ntriples,
            },
            "graph_revision": occurrence.graph_revision,
            "assertion_kind": occurrence.assertion_kind,
            "status": occurrence.status,
            "lifecycle": {
                "created_at": occurrence.created_at,
                "invalidated_at": occurrence.invalidated_at,
                "invalidated_revision": occurrence.invalidated_revision,
                "invalidated_by_audit_id": occurrence.invalidated_by_audit_id,
            },
            "origins": origin_payload,
            "supporting_context": context,
            "supporting_context_status": (
                "present" if any(context[key] for key in context) else "missing"
            ),
            "evidence_status": evidence_status,
            "dependency_evidence_status": dependency_status,
            "lineage_status": lineage_status,
            "derivation": derivation,
            "staleness": {"is_stale": stale, "reason": stale_reason},
            "technical_trace": {
                "graph_iri": occurrence.graph_iri,
                "graph_set_id": occurrence.graph_set_id,
            },
            "warnings": list(dict.fromkeys(warnings)),
        }

    def _resolve_origins(self, occurrence, origins, ontology):
        payload: list[dict[str, Any]] = []
        evidence: dict[str, dict[str, Any]] = {}
        rationales: list[dict[str, Any]] = []
        questions: dict[str, dict[str, Any]] = {}
        audits: dict[str, dict[str, Any]] = {}
        derivation: dict[str, Any] | None = None
        warnings: list[str] = []
        for origin in origins:
            entry = {
                "kind": origin.origin_kind,
                "id": origin.origin_id,
                "metadata": origin.origin_metadata or {},
            }
            if origin.origin_kind == "modeling_item":
                item = self.session.get(ModelingItemModel, origin.origin_id)
                batch = self.session.get(ModelingBatchModel, item.batch_id) if item else None
                if item is None or batch is None or batch.ontology_id != ontology.id:
                    warnings.append("origin_scope_mismatch")
                    continue
                entry["modeling_item"] = {
                    "id": item.id,
                    "client_item_id": item.client_item_id,
                    "command_kind": item.command_kind,
                    "batch_id": batch.id,
                }
                if item.rationale:
                    rationales.append({"modeling_item_id": item.id, "text": item.rationale})
                for question_id in item.competency_question_ids or []:
                    question = self.session.get(CompetencyQuestionModel, question_id)
                    if question and question.ontology_id == ontology.id:
                        questions[question.id] = {
                            "id": question.id,
                            "question": question.question,
                        }
                for reference in self._modeling_item_evidence(item.id, ontology):
                    evidence[reference["id"]] = reference
            elif origin.origin_kind == "edit_audit":
                audit = self.session.get(SemanticEditAuditModel, origin.origin_id)
                if audit is not None and occurrence.graph_iri in (audit.affected_graph_iris or []):
                    audit_payload = self._audit_payload(audit)
                    entry["edit_audit"] = audit_payload
                    audits[audit.id] = audit_payload
                else:
                    warnings.append("origin_scope_mismatch")
                    continue
            elif origin.origin_kind == "reasoning_run":
                run = self.session.get(SemanticReasoningRunModel, origin.origin_id)
                if run is None or not self._run_in_ontology(
                    (run.run_metadata or {}).get("graph_set_id"), ontology.id
                ):
                    warnings.append("origin_scope_mismatch")
                    continue
                entry["run"] = self._reasoning_run_payload(run)
                derivation = {
                    "proof_level": (origin.origin_metadata or {}).get("proof_level", "coarse"),
                    "run": entry["run"],
                    "definition": None,
                    "premises": [],
                }
            elif origin.origin_kind == "rule_run":
                run = self.session.get(SemanticRuleRunModel, origin.origin_id)
                if run is None or not self._run_in_ontology(run.graph_set_id, ontology.id):
                    warnings.append("origin_scope_mismatch")
                    continue
                entry["run"] = self._rule_run_payload(run)
                definition = (
                    self.session.get(SemanticRuleDefinitionModel, run.rule_definition_id)
                    if run.rule_definition_id
                    else None
                )
                source_metadata = (origin.origin_metadata or {}).get("rule_sources") or []
                if not source_metadata and definition is not None:
                    source_metadata = [
                        {
                            "rule_definition_id": definition.id,
                            "rule_version": definition.version,
                            "rule_iri": definition.rule_iri,
                            "language": definition.language,
                            "proof_level": (origin.origin_metadata or {}).get(
                                "proof_level", "coarse"
                            ),
                        }
                    ]
                definitions = []
                seen_definitions: set[str] = set()
                for source in source_metadata:
                    definition_id = source.get("rule_definition_id")
                    source_definition = (
                        self.session.get(SemanticRuleDefinitionModel, definition_id)
                        if definition_id
                        else None
                    )
                    if source_definition is None or source_definition.id in seen_definitions:
                        continue
                    seen_definitions.add(source_definition.id)
                    definitions.append(self._definition_payload(source_definition))
                entry["rule_sources"] = source_metadata
                entry["definitions"] = definitions
                derivation = {
                    "proof_level": (origin.origin_metadata or {}).get("proof_level", "coarse"),
                    "run": entry["run"],
                    "definition": definitions[0] if definitions else None,
                    "definitions": definitions,
                    "rule_sources": source_metadata,
                    "premises": [],
                }
            payload.append(entry)
        invalidation_audit_id = occurrence.invalidated_by_audit_id
        if invalidation_audit_id and invalidation_audit_id not in audits:
            audit = self.session.get(SemanticEditAuditModel, invalidation_audit_id)
            if audit is not None and self._audit_in_scope(audit, occurrence, ontology):
                audits[audit.id] = self._audit_payload(audit)
            else:
                warnings.append("origin_scope_mismatch")
        for reference in self._fact_evidence(occurrence, ontology):
            evidence[reference["id"]] = reference
        return (
            payload,
            {
                "evidence_references": list(evidence.values()),
                "rationales": rationales,
                "competency_questions": list(questions.values()),
                "edit_audits": list(audits.values()),
            },
            derivation,
            warnings,
        )

    def _modeling_item_evidence(self, item_id: str, ontology: OntologyModel):
        rows = self.session.execute(
            select(EvidenceAssociationModel, EvidenceReferenceModel)
            .join(
                EvidenceReferenceModel,
                EvidenceReferenceModel.id == EvidenceAssociationModel.evidence_reference_id,
            )
            .where(
                EvidenceAssociationModel.ontology_id == ontology.id,
                EvidenceAssociationModel.project_id == ontology.project_id,
                EvidenceAssociationModel.target_type == "modeling_item",
                EvidenceAssociationModel.target_id == item_id,
                EvidenceReferenceModel.project_id == ontology.project_id,
            )
        )
        return [self._evidence_payload(reference) for _association, reference in rows]

    def _fact_evidence(self, occurrence, ontology):
        if getattr(occurrence, "assertion_kind", "asserted") != "asserted":
            return []
        graph_set_ids = set(
            self.session.scalars(
                select(SemanticGraphSetMemberModel.graph_set_id)
                .join(
                    SemanticGraphSetModel,
                    SemanticGraphSetModel.id == SemanticGraphSetMemberModel.graph_set_id,
                )
                .where(
                    SemanticGraphSetModel.scope_type == "ontology",
                    SemanticGraphSetModel.scope_id == ontology.id,
                    SemanticGraphSetModel.status == "active",
                    SemanticGraphSetMemberModel.role == "asserted_data",
                    SemanticGraphSetMemberModel.graph_iri == occurrence.graph_iri,
                )
            )
        )
        occurrence_graph_set_id = getattr(occurrence, "graph_set_id", None)
        if occurrence_graph_set_id:
            graph_set_ids.intersection_update({occurrence_graph_set_id})
        if not graph_set_ids:
            return []
        rows = self.session.scalars(
            select(FactEvidenceBindingModel).where(
                FactEvidenceBindingModel.fact_id == occurrence.statement_id,
                FactEvidenceBindingModel.graph_iri == occurrence.graph_iri,
            )
        )
        result = []
        for binding in rows:
            if not binding.evidence_reference_id:
                continue
            reference = self.session.get(EvidenceReferenceModel, binding.evidence_reference_id)
            association = self.session.scalar(
                select(EvidenceAssociationModel).where(
                    EvidenceAssociationModel.project_id == ontology.project_id,
                    EvidenceAssociationModel.ontology_id == ontology.id,
                    EvidenceAssociationModel.graph_set_id.in_(graph_set_ids),
                    EvidenceAssociationModel.target_type == "fact",
                    EvidenceAssociationModel.target_id == occurrence.statement_id,
                    EvidenceAssociationModel.evidence_reference_id == binding.evidence_reference_id,
                )
            )
            if (
                reference is not None
                and reference.project_id == ontology.project_id
                and association is not None
            ):
                result.append(self._evidence_payload(reference))
        return result

    @staticmethod
    def _audit_in_scope(audit, occurrence, ontology) -> bool:
        return bool(
            occurrence.ontology_id == ontology.id
            and occurrence.graph_iri in (audit.affected_graph_iris or [])
        )

    @staticmethod
    def _evidence_payload(reference):
        return {
            "id": reference.id,
            "document_name": reference.document_name,
            "excerpt": reference.excerpt,
            "created_by": reference.created_by,
            "created_at": reference.created_at,
        }

    @staticmethod
    def _audit_payload(audit):
        return {
            "id": audit.id,
            "actor": audit.actor,
            "reason": audit.reason,
            "input_format": audit.input_format,
            "applied": audit.applied,
            "created_at": audit.created_at,
        }

    @staticmethod
    def _reasoning_run_payload(run):
        metadata = run.run_metadata or {}
        return {
            "id": run.id,
            "kind": "reasoning",
            "status": run.status,
            "engine_name": run.reasoner,
            "engine_version": metadata.get("engine_version"),
            "source_signature": metadata.get("source_signature", ""),
            "input_graph_revisions": metadata.get("input_graph_revisions", {}),
            "input_derived_pointers": metadata.get("input_derived_pointers", {}),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }

    @staticmethod
    def _rule_run_payload(run):
        metadata = run.run_metadata or {}
        return {
            "id": run.id,
            "kind": "rule",
            "status": run.status,
            "engine_name": run.engine_name,
            "engine_version": run.engine_version,
            "source_signature": run.source_signature,
            "input_graph_revisions": metadata.get("input_graph_revisions", {}),
            "input_derived_pointers": metadata.get("input_derived_pointers", {}),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }

    @staticmethod
    def _definition_payload(definition):
        return {
            "id": definition.id,
            "rule_iri": definition.rule_iri,
            "name": definition.name,
            "language": definition.language,
            "version": definition.version,
            "status": definition.status,
        }

    def _run_in_ontology(self, graph_set_id: str | None, ontology_id: str) -> bool:
        if not graph_set_id:
            return False
        graph_set = self.session.get(SemanticGraphSetModel, graph_set_id)
        return bool(
            graph_set and graph_set.scope_type == "ontology" and graph_set.scope_id == ontology_id
        )

    def _rule_items(self, *, ontology, rule_iri, include_history, state):
        rule = self.session.scalar(
            select(SemanticRuleModel).where(
                SemanticRuleModel.ontology_id == ontology.id,
                SemanticRuleModel.rule_iri == rule_iri,
            )
        )
        if rule is None:
            raise LineageTargetNotFound("Rule was not found in this Ontology")
        statement = select(SemanticRuleDefinitionModel).where(
            SemanticRuleDefinitionModel.semantic_rule_id == rule.id
        )
        if not include_history:
            if not rule.current_definition_id:
                raise LineageTargetNotFound("Rule has no current definition")
            statement = statement.where(
                SemanticRuleDefinitionModel.id == rule.current_definition_id
            )
        definitions = list(
            self.session.scalars(
                statement.order_by(SemanticRuleDefinitionModel.created_at.desc()).limit(
                    state.limit + 1
                )
            )
        )
        if len(definitions) > state.limit:
            state.truncated = True
            definitions = definitions[: state.limit]
        items = []
        for definition in definitions:
            state.count += 1
            metadata = definition.rule_metadata or {}
            item_id = metadata.get("modeling_item_id")
            audit_id = metadata.get("edit_audit_id")
            context = {
                "evidence_references": [],
                "rationales": [],
                "competency_questions": [],
                "edit_audits": [],
            }
            origins = []
            if item_id:
                item = self.session.get(ModelingItemModel, item_id)
                batch = self.session.get(ModelingBatchModel, item.batch_id) if item else None
                if item and batch and batch.ontology_id == ontology.id:
                    origins.append({"kind": "modeling_item", "id": item.id})
                    context["evidence_references"] = self._modeling_item_evidence(item.id, ontology)
                    if item.rationale:
                        context["rationales"].append(
                            {"modeling_item_id": item.id, "text": item.rationale}
                        )
                    for question_id in item.competency_question_ids or []:
                        question = self.session.get(CompetencyQuestionModel, question_id)
                        if question and question.ontology_id == ontology.id:
                            context["competency_questions"].append(
                                {"id": question.id, "question": question.question}
                            )
            if audit_id:
                audit = self.session.get(SemanticEditAuditModel, audit_id)
                if audit:
                    origins.append({"kind": "edit_audit", "id": audit.id})
                    context["edit_audits"].append(self._audit_payload(audit))
            evidence_status = "supported" if context["evidence_references"] else "missing"
            items.append(
                {
                    "item_kind": "rule_definition",
                    "rule": {"id": rule.id, "rule_iri": rule.rule_iri, "status": rule.status},
                    "definition": self._definition_payload(definition),
                    "origins": origins,
                    "supporting_context": context,
                    "supporting_context_status": (
                        "present" if any(context.values()) else "missing"
                    ),
                    "evidence_status": evidence_status,
                    "dependency_evidence_status": "not_applicable",
                    "lineage_status": "complete" if origins else "partial",
                    "derivation": None,
                    "staleness": {
                        "is_stale": definition.id != rule.current_definition_id,
                        "reason": (
                            "superseded_definition"
                            if definition.id != rule.current_definition_id
                            else None
                        ),
                    },
                    "warnings": [] if origins else ["legacy_lineage_unavailable"],
                }
            )
        return items

    def _legacy_items(self, *, ontology, target_type, target_id, scope, limit):
        statements = []
        if target_type == "statement":
            binding = self.session.scalar(
                select(FactEvidenceBindingModel).where(
                    FactEvidenceBindingModel.fact_id == target_id
                )
            )
            if binding and binding.graph_iri in scope["current_graphs"]:
                statements.append(
                    (
                        binding.subject_iri,
                        binding.predicate_iri,
                        binding.object_value,
                        binding.graph_iri,
                    )
                )
            if not statements:
                statements = [
                    quad
                    for quad in self._rdf_statements(scope["current_graphs"], None, limit)
                    if statement_id_for_quad(*quad) == target_id
                ]
        else:
            statements = self._rdf_statements(scope["current_graphs"], target_id, limit)
        result = []
        for subject, predicate, obj, graph_iri in statements:
            revision = (
                self.session.scalar(
                    select(SemanticGraphRevisionModel.revision).where(
                        SemanticGraphRevisionModel.graph_iri == graph_iri
                    )
                )
                or 0
            )
            statement_id = statement_id_for_quad(subject, predicate, obj, graph_iri)
            kind = "asserted" if graph_iri in scope["asserted_graphs"] else "rule_derived"
            evidence = []
            if kind == "asserted":
                fake = type(
                    "LegacyOccurrence",
                    (),
                    {"statement_id": statement_id, "graph_iri": graph_iri},
                )()
                evidence = self._fact_evidence(fake, ontology)
            result.append(
                {
                    "item_kind": "statement",
                    "statement_id": statement_id,
                    "occurrence_id": occurrence_id_for(statement_id, int(revision)),
                    "statement": {
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                    },
                    "graph_revision": int(revision),
                    "assertion_kind": kind,
                    "status": "active",
                    "lifecycle": {
                        "created_at": None,
                        "invalidated_at": None,
                        "invalidated_revision": None,
                        "invalidated_by_audit_id": None,
                    },
                    "origins": [
                        {
                            "kind": "legacy_unknown",
                            "id": f"{graph_iri}:{revision}",
                            "metadata": {"warning": "legacy_lineage_unavailable"},
                        }
                    ],
                    "supporting_context": {
                        "evidence_references": evidence,
                        "rationales": [],
                        "competency_questions": [],
                        "edit_audits": [],
                    },
                    "supporting_context_status": "present" if evidence else "missing",
                    "evidence_status": (
                        "not_applicable"
                        if kind != "asserted"
                        else ("supported" if evidence else "missing")
                    ),
                    "dependency_evidence_status": (
                        "unknown" if kind != "asserted" else "not_applicable"
                    ),
                    "lineage_status": "partial",
                    "derivation": (
                        {
                            "proof_level": "unavailable",
                            "run": None,
                            "definition": None,
                            "premises": [],
                        }
                        if kind != "asserted"
                        else None
                    ),
                    "staleness": {"is_stale": False, "reason": None},
                    "technical_trace": {"graph_iri": graph_iri, "graph_set_id": None},
                    "warnings": ["legacy_lineage_unavailable"],
                }
            )
        return result

    def _rdf_statements(self, graph_iris, subject_iri, limit):
        if self.rdf_store is None or not graph_iris:
            return []
        graph_values = " ".join(f"<{iri}>" for iri in sorted(graph_iris))
        subject = f"<{subject_iri}>" if subject_iri else "?s"
        select_vars = "?p ?o ?g" if subject_iri else "?s ?p ?o ?g"
        query = (
            f"SELECT {select_vars} WHERE {{ VALUES ?g {{ {graph_values} }} "
            f"GRAPH ?g {{ {subject} ?p ?o }} }}"
        )
        try:
            response = self.rdf_store.query_sparql(query, timeout_seconds=10, limit=limit)
            bindings = (response.result or {}).get("results", {}).get("bindings", [])
        except Exception:
            return []
        result = []
        for row in bindings:
            if not all(name in row for name in ("p", "o", "g")):
                continue
            if row["p"].get("type") != "uri" or row["g"].get("type") != "uri":
                continue
            if subject_iri is None and row.get("s", {}).get("type") != "uri":
                continue
            subject_value = subject_iri or row.get("s", {}).get("value")
            if not subject_value:
                continue
            result.append(
                (
                    subject_value,
                    row["p"]["value"],
                    self._binding_n3(row["o"]),
                    row["g"]["value"],
                )
            )
        return result

    @staticmethod
    def _binding_n3(binding):
        value = binding.get("value", "")
        kind = binding.get("type")
        if kind == "uri":
            return URIRef(value).n3()
        if kind == "bnode":
            return BNode(value).n3()
        return Literal(
            value,
            lang=binding.get("xml:lang") or binding.get("lang"),
            datatype=URIRef(binding["datatype"]) if binding.get("datatype") else None,
        ).n3()

    @staticmethod
    def _dependency_status(derivation, derived):
        if not derived:
            return "not_applicable"
        if derivation is None or derivation.get("proof_level") != "exact":
            return "unknown"
        premises = derivation.get("premises", [])
        if not premises:
            return "unknown"
        statuses = []
        for premise in premises:
            if premise.get("item_kind") == "statement_reference":
                return "unknown"
            statuses.append(premise.get("evidence_status"))
            dependency = premise.get("dependency_evidence_status")
            if dependency not in {None, "not_applicable", "supported"}:
                statuses.append("missing")
        return "contains_missing" if "missing" in statuses else "supported"

    @staticmethod
    def _aggregate_lineage_status(items):
        statuses = {item.get("lineage_status", "missing") for item in items}
        if "missing" in statuses:
            return "missing"
        if "partial" in statuses:
            return "partial"
        return "complete"

    @staticmethod
    def _aggregate_evidence_status(items):
        statuses = [item.get("evidence_status") for item in items]
        asserted = [status for status in statuses if status != "not_applicable"]
        if not asserted:
            return "not_applicable"
        return "missing" if "missing" in asserted else "supported"

    @staticmethod
    def _aggregate_dependency_status(items):
        statuses = [item.get("dependency_evidence_status") for item in items]
        derived = [status for status in statuses if status != "not_applicable"]
        if not derived:
            return "not_applicable"
        if "contains_missing" in derived:
            return "contains_missing"
        if "unknown" in derived:
            return "unknown"
        return "supported"

    @staticmethod
    def _item_warnings(items):
        return [warning for item in items for warning in item.get("warnings", [])]


__all__ = [
    "LineageTargetNotFound",
    "OntologyLineageError",
    "OntologyLineageService",
]
