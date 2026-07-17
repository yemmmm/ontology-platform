"""Phase 5 rule definition service: versioned, validated rule records.

Rule definitions are operational control records that hold the executable source
for SPARQL CONSTRUCT templates, platform DSL programs, or workflow state
machines. Saved rule definitions are immediately executable; later edits create
a new version when executable content changes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import OntologyModel, SemanticRuleDefinitionModel, SemanticRuleModel


class RuleDefinitionError(RuntimeError):
    status_code = 400


class RuleDefinitionNotFound(RuleDefinitionError):
    status_code = 404


ALLOWED_LANGUAGES: frozenset[str] = frozenset(
    {"sparql_construct", "platform_dsl", "workflow_state_machine"}
)
ALLOWED_OUTPUT_KINDS: frozenset[str] = frozenset(
    {"assertion", "validation", "workflow", "annotation"}
)
ALLOWED_INPUT_ROLES: frozenset[str] = frozenset(
    {
        "asserted_ontology",
        "asserted_data",
        "shape",
        "import",
        "evidence",
        "policy",
        "reasoning_result",
        "rule_result",
    }
)


def compute_rule_version(body: dict[str, Any], language: str) -> str:
    """Deterministic version hash for a rule body and language."""
    payload = json.dumps({"body": body, "language": language}, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"sha256:{digest[:16]}"


class SemanticRuleDefinitionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create_rule(
        self,
        rule_iri: str,
        name: str,
        language: str,
        body: dict[str, Any],
        input_roles: list[str],
        output_kind: str = "assertion",
        uses_inferred_facts: bool = False,
        requires_review: bool = False,
        priority: int = 0,
        safety_profile: dict[str, Any] | None = None,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
        ontology_id: str | None = None,
    ) -> SemanticRuleDefinitionModel:
        if language not in ALLOWED_LANGUAGES:
            raise RuleDefinitionError(f"Unsupported rule language: {language}")
        if output_kind not in ALLOWED_OUTPUT_KINDS:
            raise RuleDefinitionError(f"Unsupported output kind: {output_kind}")
        if not name:
            raise RuleDefinitionError("Rule name is required")
        if not rule_iri:
            raise RuleDefinitionError("rule_iri is required")
        if not input_roles:
            raise RuleDefinitionError("Rule must declare at least one input role")
        unknown_roles = [role for role in input_roles if role not in ALLOWED_INPUT_ROLES]
        if unknown_roles:
            raise RuleDefinitionError(f"Unknown input roles: {sorted(set(unknown_roles))}")
        if uses_inferred_facts and "reasoning_result" not in input_roles:
            input_roles = [*input_roles, "reasoning_result"]
        if language == "sparql_construct":
            validate_construct_template(body)
        elif language == "platform_dsl":
            validate_platform_dsl(body)
        elif language == "workflow_state_machine":
            validate_workflow_state_machine(body)
        version = compute_rule_version(body, language)
        semantic_rule = None
        if ontology_id is not None:
            if self.session.get(OntologyModel, ontology_id) is None:
                raise RuleDefinitionError("Ontology not found")
            semantic_rule = self.session.scalar(
                select(SemanticRuleModel).where(
                    SemanticRuleModel.ontology_id == ontology_id,
                    SemanticRuleModel.rule_iri == rule_iri,
                )
            )
            if semantic_rule is None:
                semantic_rule = SemanticRuleModel(
                    id=str(uuid4()),
                    ontology_id=ontology_id,
                    rule_iri=rule_iri,
                    status="active",
                )
                self.session.add(semantic_rule)
                self.session.flush()
        statement = select(SemanticRuleDefinitionModel).where(
            SemanticRuleDefinitionModel.rule_iri == rule_iri,
            SemanticRuleDefinitionModel.version == version,
        )
        if semantic_rule is None:
            statement = statement.where(SemanticRuleDefinitionModel.semantic_rule_id.is_(None))
        else:
            statement = statement.where(
                SemanticRuleDefinitionModel.semantic_rule_id == semantic_rule.id
            )
        existing = self.session.scalar(statement)
        if existing is not None:
            return existing
        record = SemanticRuleDefinitionModel(
            id=str(uuid4()),
            semantic_rule_id=semantic_rule.id if semantic_rule else None,
            rule_iri=rule_iri,
            name=name,
            language=language,
            version=version,
            status="active",
            body=body,
            input_roles=list(dict.fromkeys(input_roles)),
            output_kind=output_kind,
            uses_inferred_facts=bool(uses_inferred_facts),
            requires_review=bool(requires_review),
            priority=int(priority),
            safety_profile=self._normalise_safety_profile(safety_profile or {}),
            created_by=created_by,
            rule_metadata=metadata or {},
        )
        self.session.add(record)
        if semantic_rule is not None:
            semantic_rule.current_definition_id = record.id
        self.session.commit()
        return record

    def get_rule(self, rule_id: str) -> SemanticRuleDefinitionModel:
        record = self.session.scalar(
            select(SemanticRuleDefinitionModel).where(SemanticRuleDefinitionModel.id == rule_id)
        )
        if record is None:
            raise RuleDefinitionNotFound(f"Rule definition not found: {rule_id}")
        return record

    def delete_rule(self, rule_id: str) -> None:
        record = self.get_rule(rule_id)
        self.session.delete(record)
        self.session.commit()

    def get_rule_by_iri(
        self,
        rule_iri: str,
    ) -> SemanticRuleDefinitionModel | None:
        statement = select(SemanticRuleDefinitionModel).where(
            SemanticRuleDefinitionModel.rule_iri == rule_iri
        )
        statement = statement.order_by(SemanticRuleDefinitionModel.updated_at.desc())
        return self.session.scalar(statement)

    def list_rules(
        self,
        language: str | None = None,
        rule_iri: str | None = None,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[SemanticRuleDefinitionModel]:
        bounded_limit = max(1, min(limit, 500))
        statement = select(SemanticRuleDefinitionModel).order_by(
            SemanticRuleDefinitionModel.priority.asc(),
            SemanticRuleDefinitionModel.rule_iri.asc(),
            SemanticRuleDefinitionModel.version.asc(),
        )
        if language:
            statement = statement.where(SemanticRuleDefinitionModel.language == language)
        if rule_iri:
            statement = statement.where(SemanticRuleDefinitionModel.rule_iri == rule_iri)
        if project_id is not None:
            statement = (
                statement.join(
                    SemanticRuleModel,
                    SemanticRuleModel.id == SemanticRuleDefinitionModel.semantic_rule_id,
                )
                .join(OntologyModel, OntologyModel.id == SemanticRuleModel.ontology_id)
                .where(OntologyModel.project_id == project_id)
            )
        return list(self.session.scalars(statement.limit(bounded_limit)))

    def _normalise_safety_profile(self, safety_profile: dict[str, Any]) -> dict[str, Any]:
        normalised = {
            "max_generated_statements": int(safety_profile.get("max_generated_statements", 10000)),
            "timeout_seconds": float(safety_profile.get("timeout_seconds", 30.0)),
            "allowed_predicates": list(safety_profile.get("allowed_predicates", [])),
        }
        if normalised["max_generated_statements"] <= 0:
            raise RuleDefinitionError("safety_profile.max_generated_statements must be positive")
        if normalised["timeout_seconds"] <= 0:
            raise RuleDefinitionError("safety_profile.timeout_seconds must be positive")
        return normalised


# ---------------------------------------------------------------------------
# Body validators
# ---------------------------------------------------------------------------


CONSTRUCT_FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "service",
    "insert",
    "delete",
    "load",
    "clear",
    "create",
    "drop",
    "copy",
    "move",
    "add",
    "using",
    "with",
)


def validate_construct_template(body: dict[str, Any]) -> None:
    if not isinstance(body, dict):
        raise RuleDefinitionError("SPARQL CONSTRUCT body must be a JSON object")
    template = body.get("template") or body.get("query")
    if not isinstance(template, str) or not template.strip():
        raise RuleDefinitionError(
            "SPARQL CONSTRUCT body must include a non-empty 'template' string"
        )
    lowered = template.lower()
    if not re_construct_search(lowered, r"\bconstruct\b"):
        raise RuleDefinitionError("SPARQL CONSTRUCT template must include a CONSTRUCT clause")
    if not re_construct_search(lowered, r"\bwhere\b"):
        raise RuleDefinitionError("SPARQL CONSTRUCT template must include a WHERE clause")
    for keyword in CONSTRUCT_FORBIDDEN_KEYWORDS:
        if re_construct_search(lowered, rf"\b{keyword}\b"):
            raise RuleDefinitionError(f"SPARQL CONSTRUCT template may not use '{keyword.upper()}'")
    import re as _re

    sanitised = _re.sub(r"<[^>]*>", " <iri> ", lowered)
    sanitised = _re.sub(r'"[^"]*"', ' "literal" ', sanitised)
    property_paths = _re.search(r"\w\s*(/|\||\^)\s*\w", sanitised)
    if property_paths:
        raise RuleDefinitionError(
            "SPARQL CONSTRUCT templates may not use property path operators in the first Phase 5 pass"
        )
    if _re.search(r"[\w>]\s*(\*|\+)\s", sanitised) or _re.search(
        r"[\w>]\s*(\*|\+)\s*[\w<{]", sanitised
    ):
        raise RuleDefinitionError(
            "SPARQL CONSTRUCT templates may not use property path cardinality operators"
        )


def re_construct_search(text: str, pattern: str) -> bool:
    import re

    return re.search(pattern, text) is not None


PLATFORM_DSL_ALLOWED_FILTER_OPS: frozenset[str] = frozenset(
    {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"}
)


def validate_platform_dsl(body: dict[str, Any]) -> None:
    if not isinstance(body, dict):
        raise RuleDefinitionError("Platform DSL body must be a JSON object")
    when = body.get("when")
    then = body.get("then")
    if not isinstance(when, list) or not when:
        raise RuleDefinitionError("Platform DSL body must include a non-empty 'when' list")
    if not isinstance(then, list) or not then:
        raise RuleDefinitionError("Platform DSL body must include a non-empty 'then' list")
    for clause in when:
        if not isinstance(clause, dict):
            raise RuleDefinitionError("Platform DSL 'when' entries must be JSON objects")
        if "filter" in clause:
            filter_clause = clause["filter"]
            if not isinstance(filter_clause, dict) or len(filter_clause) != 1:
                raise RuleDefinitionError(
                    "Platform DSL filter clause must have exactly one operator"
                )
            operator = next(iter(filter_clause))
            if operator not in PLATFORM_DSL_ALLOWED_FILTER_OPS:
                raise RuleDefinitionError(f"Platform DSL filter operator not supported: {operator}")
            args = filter_clause[operator]
            if not isinstance(args, list) or len(args) < 2:
                raise RuleDefinitionError(
                    f"Platform DSL filter '{operator}' needs at least two operands"
                )
        elif "s" not in clause or "p" not in clause or "o" not in clause:
            raise RuleDefinitionError(
                "Platform DSL 'when' entries must include 's', 'p', and 'o' bindings or a 'filter' block"
            )
    for clause in then:
        if not isinstance(clause, dict):
            raise RuleDefinitionError("Platform DSL 'then' entries must be JSON objects")
        if "s" not in clause or "p" not in clause or "o" not in clause:
            raise RuleDefinitionError(
                "Platform DSL 'then' entries must include 's', 'p', and 'o' templates"
            )


def validate_workflow_state_machine(body: dict[str, Any]) -> None:
    if not isinstance(body, dict):
        raise RuleDefinitionError("Workflow state-machine body must be a JSON object")
    states = body.get("states")
    transitions = body.get("transitions")
    if not isinstance(states, list) or not states:
        raise RuleDefinitionError(
            "Workflow state-machine body must include a non-empty 'states' list"
        )
    if not isinstance(transitions, list):
        raise RuleDefinitionError(
            "Workflow state-machine body must include a 'transitions' list (may be empty)"
        )
    for transition in transitions:
        if not isinstance(transition, dict):
            raise RuleDefinitionError("Workflow state-machine transitions must be JSON objects")
        if not {"from", "to"}.issubset(transition):
            raise RuleDefinitionError(
                "Workflow state-machine transitions must include 'from' and 'to' states"
            )
