"""Authoritative model version shared by write, retrieval and read receipts."""
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.services.ontology_workspace import OntologyWorkspaceService


class ModelingWorkspaceVersionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def version_for(self, ontology_id: str) -> str:
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        if workspace["state"] != "ready":
            raise LookupError("Ontology model is incomplete")
        return workspace["source_signature"]
