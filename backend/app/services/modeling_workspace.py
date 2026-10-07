"""Authoritative R-004 workspace version shared by every Agent surface."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.config import Settings
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
        payload = graph_signature
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
