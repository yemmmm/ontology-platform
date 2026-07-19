"""Authorized Project/Ontology discovery for semantic query consumers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import OntologyModel, OntologyStatus, ProjectModel
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_read_scope import ScopeResolution, SemanticReadScopeResolver


_EPHEMERAL_CURSOR_KEY = secrets.token_bytes(32)


class ScopeDiscoveryError(RuntimeError):
    status_code = 400
    code = "invalid_discovery_request"


class ScopeDiscoveryCursorError(ScopeDiscoveryError):
    code = "invalid_cursor"


@dataclass(frozen=True)
class OntologyQueryReadiness:
    queryable: bool
    unavailable_reason: str | None
    workspace_version: str | None
    derived_warnings: tuple[dict[str, str], ...] = ()
    graph_set_id: str | None = None
    read_scope: ScopeResolution | None = None


class OntologyQueryReadinessEvaluator:
    """Evaluate the current public query readiness of one Ontology."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.workspace_service = OntologyWorkspaceService(session, settings)
        self.read_scope_resolver = SemanticReadScopeResolver(session)
        self.version_service = ModelingWorkspaceVersionService(session, settings)

    def evaluate(self, ontology: OntologyModel) -> OntologyQueryReadiness:
        if ontology.status == OntologyStatus.ARCHIVED.value:
            return OntologyQueryReadiness(False, "ontology_archived", None)
        try:
            workspace = self.workspace_service.context(ontology.id)
            graph_set_id = workspace.get("default_graph_set_id")
            if workspace.get("state") != "ready" or not graph_set_id:
                return OntologyQueryReadiness(False, "workspace_not_ready", None)
            read_scope = self.read_scope_resolver.resolve(
                graph_set_id,
                include="full-working-view",
                allow_stale_derived=True,
            )
            workspace_version = self.version_service.version_for(ontology.id)
        except (LookupError, RuntimeError):
            return OntologyQueryReadiness(False, "workspace_not_ready", None)
        warnings = tuple(self._public_warning(item) for item in read_scope.warnings)
        return OntologyQueryReadiness(
            True,
            None,
            workspace_version,
            warnings,
            graph_set_id,
            read_scope,
        )

    @staticmethod
    def _public_warning(warning: dict[str, str]) -> dict[str, str]:
        code = warning.get("code", "derived_result_missing")
        if code.startswith("stale_"):
            public_code = "derived_result_stale"
        elif code.startswith("missing_"):
            public_code = "derived_result_missing"
        else:
            public_code = code
        return {"code": public_code, "message": warning.get("message", public_code)}


class AuthorizedScopeDiscoveryService:
    """Return a bounded, authorization-filtered semantic scope catalog."""

    _CURSOR_VERSION = 1
    _MAX_QUERY_LENGTH = 200

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.readiness = OntologyQueryReadinessEvaluator(session, settings)

    def discover(
        self,
        *,
        authorized_project_id: str | None,
        query: str | None = None,
        queryable: bool | str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        normalized_query = self._normalize_query(query)
        queryable_filter = self._normalize_queryable(queryable)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ScopeDiscoveryError("limit must be between 1 and 100")

        projects_statement = select(ProjectModel)
        ontologies_statement = select(OntologyModel)
        if authorized_project_id is not None:
            projects_statement = projects_statement.where(ProjectModel.id == authorized_project_id)
            ontologies_statement = ontologies_statement.where(
                OntologyModel.project_id == authorized_project_id
            )
        projects = list(self.session.scalars(projects_statement))
        ontologies = list(self.session.scalars(ontologies_statement))
        projects_by_id = {item.id: item for item in projects}
        ontologies = [item for item in ontologies if item.project_id in projects_by_id]

        readiness_by_id = {item.id: self.readiness.evaluate(item) for item in ontologies}
        children: dict[str, list[OntologyModel]] = {item.id: [] for item in projects}
        for ontology in ontologies:
            children[ontology.project_id].append(ontology)

        candidates: list[tuple[tuple[str, str, int, str, str], dict[str, Any]]] = []
        for project in projects:
            project_matches = self._matches(project.id, project.name, normalized_query)
            ontology_matches = {
                ontology.id: self._matches(ontology.id, ontology.name, normalized_query)
                for ontology in children[project.id]
            }
            project_selected = not normalized_query or bool(project_matches)
            selected_ontologies = [
                ontology
                for ontology in children[project.id]
                if not normalized_query or project_matches or ontology_matches[ontology.id]
            ]
            if queryable_filter is not None:
                selected_ontologies = [
                    ontology
                    for ontology in selected_ontologies
                    if readiness_by_id[ontology.id].queryable is queryable_filter
                ]
                project_selected = project_selected and bool(selected_ontologies)

            project_key = (project.name.casefold(), project.id, 0, "", "")
            if project_selected:
                candidates.append(
                    (
                        project_key,
                        self._project_item(
                            project,
                            children[project.id],
                            project_matches if normalized_query else [],
                            readiness_by_id,
                        ),
                    )
                )
            for ontology in selected_ontologies:
                matches = ontology_matches[ontology.id] if normalized_query else []
                if normalized_query and project_matches and not matches:
                    matches = ["project"]
                ontology_key = (
                    project.name.casefold(),
                    project.id,
                    1,
                    ontology.name.casefold(),
                    ontology.id,
                )
                candidates.append(
                    (
                        ontology_key,
                        self._ontology_item(
                            project, ontology, matches, readiness_by_id[ontology.id]
                        ),
                    )
                )

        candidates.sort(key=lambda item: item[0])
        fingerprint = self._filter_fingerprint(
            normalized_query,
            queryable_filter,
            authorized_project_id,
        )
        after_key = self._decode_cursor(cursor, fingerprint) if cursor else None
        if after_key is not None:
            candidates = [item for item in candidates if item[0] > after_key]
        page = candidates[: limit + 1]
        has_more = len(page) > limit
        page = page[:limit]
        next_cursor = self._encode_cursor(page[-1][0], fingerprint) if has_more and page else None
        generated_at = self.session.scalar(select(func.now()))
        if not isinstance(generated_at, datetime):
            generated_at = datetime.now(UTC)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        return {
            "items": [item for _key, item in page],
            "has_more": has_more,
            "next_cursor": next_cursor,
            "generated_at": generated_at,
        }

    @staticmethod
    def _matches(resource_id: str, name: str, query: str) -> list[str]:
        if not query:
            return []
        matches = []
        if resource_id == query:
            matches.append("id")
        if query.casefold() in name.casefold():
            matches.append("name")
        return matches

    def _project_item(
        self,
        project: ProjectModel,
        ontologies: list[OntologyModel],
        matched_on: list[str],
        readiness_by_id: dict[str, OntologyQueryReadiness],
    ) -> dict[str, Any]:
        available = [item for item in ontologies if readiness_by_id[item.id].queryable]
        if ontologies and len(available) == len(ontologies):
            query_status = "complete"
        elif available:
            query_status = "partial"
        else:
            query_status = "unavailable"
        excluded = [
            {
                "ontology_id": item.id,
                "ontology_name": item.name,
                "reason": readiness_by_id[item.id].unavailable_reason,
            }
            for item in sorted(ontologies, key=lambda value: (value.name.casefold(), value.id))
            if not readiness_by_id[item.id].queryable
        ]
        return {
            "resource_type": "project",
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "matched_on": matched_on,
            "query_status": query_status,
            "query_scope": {
                "project_id": project.id,
                "scope_mode": "project",
                "ontology_ids": [],
            },
            "excluded_ontologies": excluded,
        }

    @staticmethod
    def _ontology_item(
        project: ProjectModel,
        ontology: OntologyModel,
        matched_on: list[str],
        readiness: OntologyQueryReadiness,
    ) -> dict[str, Any]:
        return {
            "resource_type": "ontology",
            "id": ontology.id,
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
            "name": ontology.name,
            "description": ontology.description,
            "status": ontology.status,
            "queryable": readiness.queryable,
            "unavailable_reason": readiness.unavailable_reason,
            "workspace_version": readiness.workspace_version,
            "derived_warnings": list(readiness.derived_warnings),
            "matched_on": matched_on,
            "query_scope": {
                "project_id": project.id,
                "scope_mode": "ontologies",
                "ontology_ids": [ontology.id],
            },
        }

    def _normalize_query(self, query: str | None) -> str:
        if query is None:
            return ""
        if not isinstance(query, str):
            raise ScopeDiscoveryError("query must be a string")
        normalized = query.strip()
        if len(normalized) > self._MAX_QUERY_LENGTH:
            raise ScopeDiscoveryError("query may contain at most 200 characters")
        return normalized

    @staticmethod
    def _normalize_queryable(value: bool | str | None) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        raise ScopeDiscoveryError("queryable must be true or false")

    @staticmethod
    def _filter_fingerprint(
        query: str,
        queryable: bool | None,
        authorized_project_id: str | None,
    ) -> str:
        raw = json.dumps(
            {
                "authorized_project_id": authorized_project_id,
                "query": query,
                "queryable": queryable,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cursor_key(self) -> bytes:
        if self.settings.secret_key:
            return hashlib.sha256(self.settings.secret_key.encode()).digest()
        return _EPHEMERAL_CURSOR_KEY

    def _encode_cursor(self, key: tuple[str, str, int, str, str], fingerprint: str) -> str:
        payload = {"v": self._CURSOR_VERSION, "f": fingerprint, "k": list(key)}
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        signature = hmac.new(self._cursor_key(), raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")

    def _decode_cursor(self, cursor: str, fingerprint: str) -> tuple[str, str, int, str, str]:
        try:
            encoded = cursor.encode()
            decoded = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
            raw, signature = decoded[:-32], decoded[-32:]
            expected = hmac.new(self._cursor_key(), raw, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(raw)
            key = payload["k"]
            if (
                payload.get("v") != self._CURSOR_VERSION
                or payload.get("f") != fingerprint
                or not isinstance(key, list)
                or len(key) != 5
                or not isinstance(key[2], int)
                or not all(isinstance(key[index], str) for index in (0, 1, 3, 4))
            ):
                raise ValueError
            return key[0], key[1], key[2], key[3], key[4]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ScopeDiscoveryCursorError("Pagination cursor is invalid") from exc
