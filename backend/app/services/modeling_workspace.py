"""Authoritative R-004 workspace version shared by every Agent surface."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import SemanticRuleDefinitionModel, SemanticRuleModel
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_graph_set import SemanticGraphSetService


class ModelingWorkspaceVersionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def version_for(self, ontology_id: str) -> str:
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        graph_set_id = workspace.get("default_graph_set_id")
        if workspace.get("state") != "ready" or not graph_set_id:
            raise LookupError("Ontology workspace is incomplete")
        graph_signature = SemanticGraphSetService(self.session, self.settings).source_signature_for(
            graph_set_id
        )
        payload = f"{graph_signature}:{self.rule_signature_for(ontology_id)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def rule_signature_for(self, ontology_id: str) -> str:
        rows = self.session.execute(
            select(SemanticRuleModel, SemanticRuleDefinitionModel)
            .outerjoin(
                SemanticRuleDefinitionModel,
                SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
            )
            .where(SemanticRuleModel.ontology_id == ontology_id)
            .order_by(SemanticRuleModel.id)
        )
        values = []
        for rule, definition in rows:
            values.append(
                {
                    "rule_id": rule.id,
                    "rule_iri": rule.rule_iri,
                    "status": rule.status,
                    "definition_id": definition.id if definition else None,
                    "version": definition.version if definition else None,
                    "name": definition.name if definition else None,
                    "language": definition.language if definition else None,
                    "body": definition.body if definition else None,
                    "input_roles": definition.input_roles if definition else None,
                    "output_kind": definition.output_kind if definition else None,
                    "uses_inferred_facts": definition.uses_inferred_facts if definition else None,
                    "requires_review": definition.requires_review if definition else None,
                    "priority": definition.priority if definition else None,
                    "safety_profile": definition.safety_profile if definition else None,
                    "metadata": definition.rule_metadata if definition else None,
                }
            )
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
