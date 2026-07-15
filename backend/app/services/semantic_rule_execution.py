"""Phase 5 rule execution: SPARQL CONSTRUCT, platform DSL, and workflow rules.

A rule run resolves the graph set, picks compatible rule definitions, executes
them in deterministic order (priority, then rule_iri, then version), attaches
provenance and assertion-kind annotations to the generated statements, writes
the result graph to ``graph/rule-result/{run_id}``, optionally writes run
metadata to ``graph/rule-run/{run_id}``, persists ``semantic_rule_runs``
metadata, and promotes a Phase 4 rule pointer when the run is requested to
become current.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticRuleDefinitionModel,
    SemanticRuleRunModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_construct import (
    ConstructExecution,
    execute_construct_template,
    referenced_graph_iris,
)
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_dsl import (
    DslExecution,
    execute_dsl,
)
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder


RULE_RESULT_PREFIX_SEGMENT = "rule-result"
RULE_RUN_PREFIX_SEGMENT = "rule-run"


class RuleExecutionError(RuntimeError):
    status_code = 400


class RuleExecutionNotFound(RuleExecutionError):
    status_code = 404


ALLOWED_RESULT_OUTPUT_KINDS: frozenset[str] = frozenset(
    {"assertion", "validation", "workflow", "annotation"}
)


class SemanticRuleExecutionService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        graph_set_service: SemanticGraphSetService | None = None,
        derived_state_service: SemanticDerivedStateService | None = None,
        lineage_recorder: SemanticLineageRecorder | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)
        self.derived_state_service = derived_state_service or SemanticDerivedStateService(
            session, settings
        )
        self.lineage_recorder = lineage_recorder or SemanticLineageRecorder(session)

    def execute_construct_template(
        self,
        graph_set_id: str,
        template: str,
        rule_definition_id: str | None = None,
        rule_version: str | None = None,
        promote_pointer: bool = True,
        actor: str | None = None,
        engine_version: str | None = None,
    ) -> dict[str, Any]:
        graph_set = self.graph_set_service.get_graph_set(graph_set_id)
        graph_set_iris = [member.graph_iri for member in graph_set.members]
        rule_definition = self._maybe_resolve_rule(rule_definition_id)
        if rule_definition is not None:
            if rule_definition.language != "sparql_construct":
                raise RuleExecutionError("Rule definition is not a sparql_construct rule")
            rule_version = rule_definition.version
            rule_definition_id = rule_definition.id
        source_signature = graph_set.source_signature
        run_id = str(uuid4())
        result_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RESULT_PREFIX_SEGMENT}/{run_id}"
        )
        rule_run_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RUN_PREFIX_SEGMENT}/{run_id}"
        )
        safety_profile = self._safety_profile(rule_definition)
        from app.services.semantic_construct import (
            ConstructTemplateError,
            validate_approved_construct,
        )

        try:
            validate_approved_construct(
                template,
                graph_set_iris=graph_set_iris,
                statement_limit=safety_profile["max_generated_statements"],
            )
        except ConstructTemplateError as exc:
            raise RuleExecutionError(str(exc)) from exc
        run = self._create_run(
            run_id=run_id,
            graph_set_id=graph_set_id,
            rule_definition_id=rule_definition_id,
            rule_version=rule_version,
            result_graph_iri=result_graph_iri,
            rule_run_graph_iri=rule_run_graph_iri,
            engine_name="sparql_construct",
            engine_version=engine_version,
            source_signature=source_signature,
            actor=actor,
        )
        try:
            execution = execute_construct_template(
                self.rdf_store,
                template,
                graph_set_iris,
                timeout_seconds=safety_profile["timeout_seconds"],
                statement_limit=safety_profile["max_generated_statements"],
            )
            self._write_result_graph(
                result_graph_iri,
                execution.statements,
                assertion_kind="construct_derived",
                rule_id=rule_definition.id if rule_definition else None,
                rule_version=rule_definition.version if rule_definition else None,
            )
            self._write_run_metadata_graph(rule_run_graph_iri, run, execution)
            self._finalise_run(
                run=run,
                execution=execution,
            )
            self._record_lineage(
                run=run,
                execution=execution,
                assertion_kind="construct_derived",
                rule_definition=rule_definition,
            )
            promoted_pointer = self._maybe_promote_pointer(
                run=run,
                promote_pointer=promote_pointer,
                rule_definition=rule_definition,
            )
            self.session.commit()
            return self._build_response(
                run=run,
                execution=execution,
                promoted_pointer=promoted_pointer,
            )
        except Exception as exc:
            self.session.rollback()
            run = self.session.get(SemanticRuleRunModel, run_id)
            if run is None:
                raise
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "engine_name": run.engine_name,
                "rule_definition_id": rule_definition_id,
                "rule_version": rule_version,
                "graph_set_id": graph_set_id,
                "result_graph_iri": result_graph_iri,
                "rule_run_graph_iri": rule_run_graph_iri,
                "generated_statement_count": 0,
                "error": run.error,
                "warnings": [],
            }

    def execute_rule(
        self,
        graph_set_id: str,
        rule_definition_id: str | None = None,
        rule_iri: str | None = None,
        promote_pointer: bool = True,
        actor: str | None = None,
        engine_version: str | None = None,
    ) -> dict[str, Any]:
        graph_set = self.graph_set_service.get_graph_set(graph_set_id)
        graph_set_iris = [member.graph_iri for member in graph_set.members]
        rule_definition = self._resolve_rule(rule_definition_id, rule_iri)
        if rule_definition.language not in {"sparql_construct", "platform_dsl"}:
            raise RuleExecutionError(
                f"Rule language not executable in the first Phase 5 pass: {rule_definition.language}"
            )
        source_signature = graph_set.source_signature
        run_id = str(uuid4())
        result_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RESULT_PREFIX_SEGMENT}/{run_id}"
        )
        rule_run_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RUN_PREFIX_SEGMENT}/{run_id}"
        )
        run = self._create_run(
            run_id=run_id,
            graph_set_id=graph_set_id,
            rule_definition_id=rule_definition.id,
            rule_version=rule_definition.version,
            result_graph_iri=result_graph_iri,
            rule_run_graph_iri=rule_run_graph_iri,
            engine_name=rule_definition.language,
            engine_version=engine_version,
            source_signature=source_signature,
            actor=actor,
        )
        try:
            safety_profile = self._safety_profile(rule_definition)
            if rule_definition.language == "sparql_construct":
                template = rule_definition.body.get("template") or rule_definition.body.get(
                    "query", ""
                )
                execution = execute_construct_template(
                    self.rdf_store,
                    template,
                    graph_set_iris,
                    timeout_seconds=safety_profile["timeout_seconds"],
                    statement_limit=safety_profile["max_generated_statements"],
                )
                result_kind = _result_kind_for(rule_definition, "construct_derived")
            else:
                execution = execute_dsl(
                    self.rdf_store,
                    rule_definition.body,
                    graph_set_iris=graph_set_iris,
                    timeout_seconds=safety_profile["timeout_seconds"],
                    statement_limit=safety_profile["max_generated_statements"],
                )
                result_kind = _result_kind_for(rule_definition, "rule_derived")
            self._write_result_graph(
                result_graph_iri,
                execution.statements,
                assertion_kind=result_kind,
                rule_id=rule_definition.id,
                rule_version=rule_definition.version,
            )
            self._write_run_metadata_graph(rule_run_graph_iri, run, execution)
            self._finalise_run(
                run=run,
                execution=execution,
            )
            self._record_lineage(
                run=run,
                execution=execution,
                assertion_kind=result_kind,
                rule_definition=rule_definition,
            )
            promoted_pointer = self._maybe_promote_pointer(
                run=run,
                promote_pointer=promote_pointer,
                rule_definition=rule_definition,
            )
            self.session.commit()
            return self._build_response(
                run=run,
                execution=execution,
                promoted_pointer=promoted_pointer,
            )
        except Exception as exc:
            self.session.rollback()
            run = self.session.get(SemanticRuleRunModel, run_id)
            if run is None:
                raise
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "engine_name": run.engine_name,
                "rule_definition_id": rule_definition.id,
                "rule_version": rule_definition.version,
                "graph_set_id": graph_set_id,
                "result_graph_iri": result_graph_iri,
                "rule_run_graph_iri": rule_run_graph_iri,
                "generated_statement_count": 0,
                "error": run.error,
                "warnings": [],
            }

    def execute_rule_group(
        self,
        graph_set_id: str,
        rule_definition_ids: list[str] | None = None,
        promote_pointer: bool = True,
        actor: str | None = None,
        engine_version: str | None = None,
    ) -> dict[str, Any]:
        graph_set = self.graph_set_service.get_graph_set(graph_set_id)
        graph_set_iris = [member.graph_iri for member in graph_set.members]
        if rule_definition_ids:
            rules = [self._require_rule(rule_id) for rule_id in rule_definition_ids]
        else:
            rules = list(
                self.session.scalars(
                    select(SemanticRuleDefinitionModel).order_by(
                        SemanticRuleDefinitionModel.priority.asc(),
                        SemanticRuleDefinitionModel.rule_iri.asc(),
                        SemanticRuleDefinitionModel.version.asc(),
                    )
                )
            )
        rules = [
            rule
            for rule in rules
            if rule.language in {"sparql_construct", "platform_dsl"}
            and self._rule_is_compatible_with_graph_set(rule, graph_set_iris)
        ]
        run_id = str(uuid4())
        result_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RESULT_PREFIX_SEGMENT}/{run_id}"
        )
        rule_run_graph_iri = (
            f"{self.settings.semantic_graph_iri_prefix}{RULE_RUN_PREFIX_SEGMENT}/{run_id}"
        )
        run = self._create_run(
            run_id=run_id,
            graph_set_id=graph_set_id,
            rule_definition_id=None,
            rule_version=None,
            result_graph_iri=result_graph_iri,
            rule_run_graph_iri=rule_run_graph_iri,
            engine_name="rule_group",
            engine_version=engine_version,
            source_signature=graph_set.source_signature,
            actor=actor,
        )
        if not rules:
            warning = "No executable rules matched the request"
            self._finalise_run(
                run=run,
                execution=_GroupExecution(statements=[], warnings=[warning]),
                extra_metadata={
                    "rule_ids": [],
                    "rule_versions": {},
                    "explanations": [],
                },
            )
            promoted_pointer = None
            if promote_pointer:
                pointer = self.derived_state_service.promote_rule_pointer(
                    graph_set_id=graph_set_id,
                    run_id=run_id,
                    result_graph_iri=result_graph_iri,
                    source_signature=graph_set.source_signature,
                    engine_name="rule_group",
                    engine_version=engine_version,
                    metadata={
                        "rule_ids": [],
                        "rule_versions": {},
                        "actor": actor,
                        "warnings": [warning],
                    },
                )
                promoted_pointer = {
                    "graph_set_id": pointer.graph_set_id,
                    "result_kind": pointer.result_kind,
                    "result_graph_iri": pointer.result_graph_iri,
                    "status": pointer.status,
                    "became_current_at": pointer.became_current_at,
                }
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "engine_name": run.engine_name,
                "engine_version": run.engine_version,
                "graph_set_id": graph_set_id,
                "result_graph_iri": result_graph_iri,
                "rule_run_graph_iri": rule_run_graph_iri,
                "rule_definition_id": None,
                "rule_version": None,
                "rule_count": 0,
                "explanations": [],
                "generated_statement_count": 0,
                "warnings": [warning],
                "derived_pointer": promoted_pointer,
                "error": None,
            }
        run.run_metadata = {
            **(run.run_metadata or {}),
            "rule_ids": [rule.id for rule in rules],
            "rule_versions": {rule.id: rule.version for rule in rules},
        }
        self.session.commit()
        try:
            aggregated: list[dict[str, Any]] = []
            explanations: list[dict[str, Any]] = []
            for rule in rules:
                safety_profile = self._safety_profile(rule)
                if rule.language == "sparql_construct":
                    template = (
                        rule.definition
                        if hasattr(rule, "definition")
                        else (rule.body.get("template") or rule.body.get("query", ""))
                    )
                    execution = execute_construct_template(
                        self.rdf_store,
                        template,
                        graph_set_iris,
                        timeout_seconds=safety_profile["timeout_seconds"],
                        statement_limit=safety_profile["max_generated_statements"],
                    )
                    result_kind = _result_kind_for(rule, "construct_derived")
                else:
                    execution = execute_dsl(
                        self.rdf_store,
                        rule.body,
                        graph_set_iris=graph_set_iris,
                        timeout_seconds=safety_profile["timeout_seconds"],
                        statement_limit=safety_profile["max_generated_statements"],
                    )
                    result_kind = _result_kind_for(rule, "rule_derived")
                exact_premises = (
                    _dsl_premises(rule.body, execution) if rule.language == "platform_dsl" else None
                )
                for statement_index, statement in enumerate(execution.statements):
                    proof_level = (
                        "exact"
                        if exact_premises is not None and statement_index in exact_premises
                        else "coarse"
                    )
                    coarse_reason = None
                    if proof_level == "coarse":
                        coarse_reason = (
                            "dsl_binding_incomplete"
                            if rule.language == "platform_dsl"
                            else "construct_binding_to_premise_unavailable"
                        )
                    aggregated.append(
                        {
                            **statement,
                            "rule_id": rule.id,
                            "rule_version": rule.version,
                            "assertion_kind": result_kind,
                            "lineage_proof_level": proof_level,
                            "lineage_premises": (
                                exact_premises.get(statement_index, [])
                                if exact_premises is not None
                                else []
                            ),
                            "lineage_origin_metadata": {
                                "rule_sources": [
                                    {
                                        "rule_definition_id": rule.id,
                                        "rule_version": rule.version,
                                        "rule_iri": rule.rule_iri,
                                        "language": rule.language,
                                        "proof_level": proof_level,
                                        "coarse_reason": coarse_reason,
                                    }
                                ]
                            },
                        }
                    )
                explanations.append(
                    {
                        "rule_id": rule.id,
                        "rule_iri": rule.rule_iri,
                        "statement_count": len(execution.statements),
                        "truncated": execution.truncated,
                        "warnings": list(execution.warnings),
                    }
                )
            self._write_result_graph(
                result_graph_iri,
                aggregated,
                assertion_kind="rule_derived",
                rule_id=None,
                rule_version=None,
            )
            self._finalise_run(
                run=run,
                execution=_GroupExecution(statements=aggregated, warnings=[]),
                extra_metadata={"explanations": explanations},
            )
            self._record_lineage(
                run=run,
                execution=_GroupExecution(statements=aggregated, warnings=[]),
                assertion_kind="rule_derived",
                rule_definition=None,
            )
            promoted_pointer = None
            if promote_pointer:
                pointer = self.derived_state_service.promote_rule_pointer(
                    graph_set_id=graph_set_id,
                    run_id=run_id,
                    result_graph_iri=result_graph_iri,
                    source_signature=graph_set.source_signature,
                    engine_name="rule_group",
                    engine_version=engine_version,
                    metadata={
                        "rule_ids": [rule.id for rule in rules],
                        "rule_versions": {rule.id: rule.version for rule in rules},
                        "actor": actor,
                    },
                )
                promoted_pointer = {
                    "graph_set_id": pointer.graph_set_id,
                    "result_kind": pointer.result_kind,
                    "result_graph_iri": pointer.result_graph_iri,
                    "status": pointer.status,
                    "became_current_at": pointer.became_current_at,
                }
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "engine_name": run.engine_name,
                "engine_version": run.engine_version,
                "graph_set_id": graph_set_id,
                "result_graph_iri": result_graph_iri,
                "rule_run_graph_iri": rule_run_graph_iri,
                "rule_definition_id": None,
                "rule_version": None,
                "rule_count": len(rules),
                "explanations": explanations,
                "generated_statement_count": run.generated_statement_count,
                "warnings": run.run_metadata.get("warnings", []),
                "derived_pointer": promoted_pointer,
                "error": None,
            }
        except Exception as exc:
            self.session.rollback()
            run = self.session.get(SemanticRuleRunModel, run_id)
            if run is None:
                raise
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "engine_name": run.engine_name,
                "graph_set_id": graph_set_id,
                "result_graph_iri": result_graph_iri,
                "rule_run_graph_iri": rule_run_graph_iri,
                "generated_statement_count": 0,
                "error": run.error,
                "warnings": [],
            }

    def _dispatch(
        self,
        *,
        graph_set_id: str,
        rule_definition_id: str | None,
        rule_iri: str | None,
        rule_definition_ids: list[str] | None,
        promote_pointer: bool,
        actor: str | None,
        engine_version: str | None,
    ) -> dict[str, Any]:
        """Pick the right execution path for MCP and other callers.

        This helper is intentionally thin: it only chooses between the group
        and single-rule paths so MCP tools don't need to encode routing logic.
        """
        if rule_definition_ids or (not rule_definition_id and not rule_iri):
            return self.execute_rule_group(
                graph_set_id=graph_set_id,
                rule_definition_ids=rule_definition_ids,
                promote_pointer=promote_pointer,
                actor=actor,
                engine_version=engine_version,
            )
        return self.execute_rule(
            graph_set_id=graph_set_id,
            rule_definition_id=rule_definition_id,
            rule_iri=rule_iri,
            promote_pointer=promote_pointer,
            actor=actor,
            engine_version=engine_version,
        )

    def get_rule_run(self, run_id: str) -> dict[str, Any]:
        run = self.session.scalar(
            select(SemanticRuleRunModel).where(SemanticRuleRunModel.id == run_id)
        )
        if run is None:
            raise RuleExecutionNotFound(f"Rule run not found: {run_id}")
        return self._serialize_run(run)

    def list_rule_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        graph_set_id: str | None = None,
        kind: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Stage 5 §4.1 — list rule runs with optional filters.

        ``graph_set_id`` filters on the dedicated column (rule runs always
        carry it). ``kind`` filters on ``engine_name`` (e.g.
        ``sparql_construct``, ``platform_dsl``) since rule runs do not have a
        separate "task" notion.
        """
        bounded_limit = max(1, min(limit, 200))
        bounded_offset = max(0, offset)
        statement = select(SemanticRuleRunModel)
        if graph_set_id:
            statement = statement.where(SemanticRuleRunModel.graph_set_id == graph_set_id)
        if kind:
            statement = statement.where(SemanticRuleRunModel.engine_name == kind)
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.session.scalars(
            statement.order_by(SemanticRuleRunModel.started_at.desc())
            .offset(bounded_offset)
            .limit(bounded_limit)
        )
        return [self._serialize_run(run) for run in rows], int(total)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_run(
        self,
        *,
        run_id: str,
        graph_set_id: str,
        rule_definition_id: str | None,
        rule_version: str | None,
        result_graph_iri: str,
        rule_run_graph_iri: str,
        engine_name: str,
        engine_version: str | None,
        source_signature: str,
        actor: str | None,
    ) -> SemanticRuleRunModel:
        run = SemanticRuleRunModel(
            id=run_id,
            graph_set_id=graph_set_id,
            rule_definition_id=rule_definition_id,
            rule_version=rule_version,
            result_graph_iri=result_graph_iri,
            rule_run_graph_iri=rule_run_graph_iri,
            engine_name=engine_name,
            engine_version=engine_version,
            source_signature=source_signature,
            status="running",
            started_at=datetime.now(UTC),
            run_metadata={
                "actor": actor,
                "input_graph_revisions": self._input_graph_revisions(graph_set_id),
                "input_derived_pointers": self._input_derived_pointers(graph_set_id),
            },
        )
        self.session.add(run)
        self.session.commit()
        return run

    def _record_lineage(
        self,
        *,
        run: SemanticRuleRunModel,
        execution: ConstructExecution | DslExecution | "_GroupExecution",
        assertion_kind: str,
        rule_definition: SemanticRuleDefinitionModel | None,
    ) -> None:
        if not run.result_graph_iri or not execution.statements:
            return
        ontology_id = self.lineage_recorder.ontology_id_for_graph_set(run.graph_set_id)
        if ontology_id is None:
            return
        proof_level = "coarse"
        premises_by_output: dict[int, list[tuple[str, str, str, str]]] = {}
        coarse_reason = "construct_binding_to_premise_unavailable"
        if rule_definition is not None and rule_definition.language == "platform_dsl":
            exact = _dsl_premises(rule_definition.body, execution)
            if exact is not None:
                proof_level = "exact"
                premises_by_output = exact
                coarse_reason = ""
            else:
                coarse_reason = "dsl_binding_incomplete"
        elif run.engine_name == "rule_group":
            if any(
                statement.get("lineage_proof_level") == "exact"
                for statement in execution.statements
            ):
                proof_level = "exact"
                coarse_reason = ""
        self.lineage_recorder.record_derived_statements(
            ontology_id=ontology_id,
            graph_set_id=run.graph_set_id,
            result_graph_iri=run.result_graph_iri,
            statements=execution.statements,
            assertion_kind=assertion_kind,
            origin_kind="rule_run",
            run_id=run.id,
            proof_level=proof_level,
            input_graph_revisions=(run.run_metadata or {}).get("input_graph_revisions", {}),
            premises_by_output=premises_by_output,
            origin_metadata={
                "coarse_reason": coarse_reason or None,
                "rule_definition_id": (rule_definition.id if rule_definition is not None else None),
                "rule_version": (rule_definition.version if rule_definition is not None else None),
                "source_signature": run.source_signature,
            },
        )

    def _input_graph_revisions(self, graph_set_id: str) -> dict[str, int]:
        graph_iris = list(
            self.session.scalars(
                select(SemanticGraphSetMemberModel.graph_iri).where(
                    SemanticGraphSetMemberModel.graph_set_id == graph_set_id
                )
            )
        )
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: int(row.revision or 0) for row in rows}

    def _input_derived_pointers(self, graph_set_id: str) -> dict[str, Any]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id,
                SemanticDerivedResultPointerModel.status == "current",
            )
        )
        return {
            row.result_kind: {
                "run_id": row.run_id,
                "result_graph_iri": row.result_graph_iri,
            }
            for row in rows
        }

    def _finalise_run(
        self,
        *,
        run: SemanticRuleRunModel,
        execution: ConstructExecution | DslExecution | "_GroupExecution",
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        warnings: list[str] = list(execution.warnings)
        run.status = "succeeded"
        run.generated_statement_count = len(execution.statements)
        run.finished_at = datetime.now(UTC)
        run.run_metadata = {
            **(run.run_metadata or {}),
            "statements": execution.statements,
            "bindings": getattr(execution, "bindings", []),
            "truncated": execution.truncated,
            "warnings": warnings,
            "audit_status": "system_accepted",
            **(extra_metadata or {}),
        }

    def _write_result_graph(
        self,
        graph_iri: str,
        statements: list[dict[str, str]],
        *,
        assertion_kind: str = "rule_derived",
        rule_id: str | None,
        rule_version: str | None,
    ) -> None:
        if not statements:
            return
        from rdflib import Graph

        graph = Graph()
        for statement in statements:
            subject = _coerce_term(statement["s"])
            predicate = _coerce_term(statement["p"])
            obj = _coerce_term(statement["o"])
            graph.add((subject, predicate, obj))
        from app.services.semantic import _triples_to_insert_data

        self.rdf_store.update_sparql(_triples_to_insert_data(graph_iri, graph))

    def _write_run_metadata_graph(
        self,
        graph_iri: str,
        run: SemanticRuleRunModel,
        execution: ConstructExecution | DslExecution,
    ) -> None:
        from rdflib import BNode, Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF

        op = Namespace("http://ontology-platform.local/ops#")
        graph = Graph()
        graph.bind("op", op)
        run_node = BNode()
        graph.add((run_node, RDF.type, URIRef(f"{op}RuleRun")))
        graph.add((run_node, op.runId, Literal(run.id)))
        if run.rule_definition_id:
            graph.add((run_node, op.ruleDefinitionId, Literal(run.rule_definition_id)))
        graph.add((run_node, op.engineName, Literal(run.engine_name)))
        if run.engine_version:
            graph.add((run_node, op.engineVersion, Literal(run.engine_version)))
        graph.add((run_node, op.generatedStatementCount, Literal(len(execution.statements))))
        graph.add((run_node, op.sourceSignature, Literal(run.source_signature)))
        from app.services.semantic import _triples_to_insert_data

        self.rdf_store.update_sparql(_triples_to_insert_data(graph_iri, graph))

    def _maybe_promote_pointer(
        self,
        *,
        run: SemanticRuleRunModel,
        promote_pointer: bool,
        rule_definition: SemanticRuleDefinitionModel | None,
    ) -> dict[str, Any] | None:
        if not promote_pointer or not run.result_graph_iri:
            return None
        pointer = self.derived_state_service.promote_rule_pointer(
            graph_set_id=run.graph_set_id,
            run_id=run.id,
            result_graph_iri=run.result_graph_iri,
            source_signature=run.source_signature,
            engine_name=run.engine_name,
            engine_version=run.engine_version,
            rule_version=run.rule_version,
            metadata={
                "rule_definition_id": rule_definition.id if rule_definition else None,
                "rule_iri": rule_definition.rule_iri if rule_definition else None,
            },
        )
        return {
            "graph_set_id": pointer.graph_set_id,
            "result_kind": pointer.result_kind,
            "result_graph_iri": pointer.result_graph_iri,
            "status": pointer.status,
            "became_current_at": pointer.became_current_at,
        }

    def _maybe_resolve_rule(
        self, rule_definition_id: str | None
    ) -> SemanticRuleDefinitionModel | None:
        if rule_definition_id is None:
            return None
        return self._require_rule(rule_definition_id)

    @staticmethod
    def _rule_is_compatible_with_graph_set(
        rule: SemanticRuleDefinitionModel,
        graph_set_iris: list[str],
    ) -> bool:
        if rule.language != "sparql_construct":
            return True
        template = rule.body.get("template") or rule.body.get("query", "")
        graph_refs = referenced_graph_iris(template)
        return not graph_refs or graph_refs.issubset(set(graph_set_iris))

    def _resolve_rule(
        self,
        rule_definition_id: str | None,
        rule_iri: str | None,
    ) -> SemanticRuleDefinitionModel:
        if rule_definition_id:
            return self._require_rule(rule_definition_id)
        if rule_iri:
            rule = self.session.scalar(
                select(SemanticRuleDefinitionModel)
                .where(SemanticRuleDefinitionModel.rule_iri == rule_iri)
                .order_by(SemanticRuleDefinitionModel.updated_at.desc())
            )
            if rule is None:
                raise RuleExecutionError(f"Rule not found for IRI: {rule_iri}")
            return rule
        raise RuleExecutionError("rule_definition_id or rule_iri is required")

    def _require_rule(self, rule_id: str) -> SemanticRuleDefinitionModel:
        rule = self.session.scalar(
            select(SemanticRuleDefinitionModel).where(SemanticRuleDefinitionModel.id == rule_id)
        )
        if rule is None:
            raise RuleExecutionNotFound(f"Rule definition not found: {rule_id}")
        return rule

    def _safety_profile(
        self, rule_definition: SemanticRuleDefinitionModel | None
    ) -> dict[str, Any]:
        if rule_definition is None:
            return {
                "max_generated_statements": 10000,
                "timeout_seconds": 30.0,
                "allowed_predicates": [],
            }
        profile = rule_definition.safety_profile or {}
        return {
            "max_generated_statements": int(profile.get("max_generated_statements", 10000)),
            "timeout_seconds": float(profile.get("timeout_seconds", 30.0)),
            "allowed_predicates": list(profile.get("allowed_predicates", [])),
        }

    def _build_response(
        self,
        *,
        run: SemanticRuleRunModel,
        execution: ConstructExecution | DslExecution,
        promoted_pointer: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = {
            "run_id": run.id,
            "status": run.status,
            "engine_name": run.engine_name,
            "engine_version": run.engine_version,
            "graph_set_id": run.graph_set_id,
            "rule_definition_id": run.rule_definition_id,
            "rule_version": run.rule_version,
            "result_graph_iri": run.result_graph_iri,
            "rule_run_graph_iri": run.rule_run_graph_iri,
            "generated_statement_count": run.generated_statement_count,
            "warnings": run.run_metadata.get("warnings", []),
            "bindings": getattr(execution, "bindings", []),
            "statements": run.run_metadata.get("statements", []),
            "truncated": execution.truncated,
            "error": None,
        }
        if promoted_pointer:
            response["derived_pointer"] = promoted_pointer
        return response

    def _serialize_run(self, run: SemanticRuleRunModel) -> dict[str, Any]:
        metadata = run.run_metadata or {}
        return {
            "run_id": run.id,
            "status": run.status,
            "engine_name": run.engine_name,
            "engine_version": run.engine_version,
            "graph_set_id": run.graph_set_id,
            "rule_definition_id": run.rule_definition_id,
            "rule_version": run.rule_version,
            "result_graph_iri": run.result_graph_iri,
            "rule_run_graph_iri": run.rule_run_graph_iri,
            "generated_statement_count": run.generated_statement_count,
            "statements": metadata.get("statements", []),
            "bindings": metadata.get("bindings", []),
            "warnings": metadata.get("warnings", []),
            "truncated": metadata.get("truncated", False),
            "audit_status": metadata.get("audit_status", "system_accepted"),
            "explanations": metadata.get("explanations", []),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
        }


def _result_kind_for(
    rule_definition: SemanticRuleDefinitionModel,
    default: str,
) -> str:
    output_kind = rule_definition.output_kind
    if output_kind == "workflow":
        return "workflow_derived"
    if output_kind == "annotation":
        return "rule_derived"
    return default


def _dsl_premises(
    body: dict[str, Any],
    execution: DslExecution | "_GroupExecution" | ConstructExecution,
) -> dict[int, list[tuple[str, str, str, str]]] | None:
    """Resolve exact DSL premise quads from projected bindings.

    Returning ``None`` is an explicit downgrade to coarse proof; callers never
    create guessed premise edges.
    """
    bindings = getattr(execution, "bindings", [])
    when = [clause for clause in body.get("when", []) if "filter" not in clause]
    if not when or not bindings:
        return None
    resolved: dict[int, list[tuple[str, str, str, str]]] = {}
    for output_index, statement in enumerate(execution.statements):
        try:
            binding = bindings[int(statement["binding_index"])]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        graph_iri = str(binding.get("g", ""))
        if graph_iri.startswith("<") and graph_iri.endswith(">"):
            graph_iri = graph_iri[1:-1]
        if not graph_iri:
            return None
        n3_values = binding.get("__n3__", {})
        premises: list[tuple[str, str, str, str]] = []
        for clause in when:
            terms: list[str] = []
            for field in ("s", "p", "o"):
                term = str(clause[field])
                if term.startswith("?"):
                    name = term[1:]
                    value = n3_values.get(name) or binding.get(name)
                    if value is None:
                        return None
                    term = str(value)
                terms.append(term)
            premises.append((terms[0], terms[1], terms[2], graph_iri))
        resolved[output_index] = premises
    return resolved


def _coerce_term(term: str):
    from rdflib import Literal, URIRef

    if not isinstance(term, str):
        return Literal(term)
    if term.startswith("<") and term.endswith(">"):
        return URIRef(term[1:-1])
    if term.startswith('"'):
        return Literal(term[1:-1])
    if term.startswith("_:"):
        from rdflib import BNode

        return BNode(term[2:])
    if term.startswith(("http://", "https://", "urn:")):
        return URIRef(term)
    return Literal(term)


class _GroupExecution:
    def __init__(self, statements: list[dict[str, Any]], warnings: list[str]) -> None:
        self.statements = statements
        self.warnings = warnings
        self.bindings: list[dict[str, str]] = []
        self.truncated = False
