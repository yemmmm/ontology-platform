"""Project-scoped checkpoint data; never a backup of server credentials or leases."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from rdflib import Graph, URIRef
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.repositories import models as m
from app.core.config import Settings
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.checkpoint_archive import ARCHIVE_KEY


SNAPSHOT_SCHEMA = "r3-0-017-platform-data/v2"

# These columns remain in the relational schema for now, but they are not
# part of the new checkpoint contract. A checkpoint must not reintroduce the
# suspended source-evidence product through a copied row shape.
_SUSPENDED_TRACE_COLUMNS = {
    "modeling_items": frozenset({"evidence_reference_ids", "evidence"}),
    "modeling_attempt_item_results": frozenset(
        {"evidence_reference_ids", "evidence_association_ids"}
    ),
    "semantic_edit_audits": frozenset({"evidence_status"}),
}


class CheckpointDataError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def snapshot_digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "digest"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _row(record: Any) -> dict[str, Any]:
    result = {}
    omitted = _SUSPENDED_TRACE_COLUMNS.get(record.__tablename__, frozenset())
    for prop in inspect(type(record)).column_attrs:
        if prop.key in omitted:
            continue
        value = getattr(record, prop.key)
        if isinstance(value, datetime):
            value = {"datetime": value.isoformat()}
        elif isinstance(value, bytes):
            value = {"base64": base64.b64encode(value).decode("ascii")}
        result[prop.key] = value
    return result


class CheckpointDataService:
    def __init__(self, session: Session, rdf_store: Any):
        self.session = session
        self.rdf_store = rdf_store

    def capture(self, project_id: str, ontology_ids: list[str]) -> dict[str, Any]:
        """Establish the SQL snapshot AFTER acquiring the canonical writer locks."""
        if self.session.get_bind().dialect.name == "postgresql":
            if self.session.in_transaction():
                raise CheckpointDataError(
                    "snapshot_transaction_active", "Capture requires a fresh read transaction"
                )
            # SELECT FOR UPDATE inside a repeatable-read transaction would
            # establish its snapshot BEFORE waiting for an existing writer.
            # Keep the locks on a separate connection so SQL and RDF both see
            # the completed writer, not old SQL paired with its new RDF.
            with Session(bind=self.session.get_bind()) as writer_lock:
                list(
                    writer_lock.scalars(
                        select(m.OntologyModel.id)
                        .where(
                            m.OntologyModel.project_id == project_id,
                            m.OntologyModel.id.in_(sorted(set(ontology_ids))),
                        )
                        .order_by(m.OntologyModel.id)
                        .with_for_update()
                    )
                )
                self.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                return self._capture_locked(project_id, ontology_ids)
        return self._capture_locked(project_id, ontology_ids)

    def _capture_locked(self, project_id: str, ontology_ids: list[str]) -> dict[str, Any]:
        ids = sorted(set(ontology_ids))
        project = self.session.get(m.ProjectModel, project_id)
        if project is None or not ids:
            raise CheckpointDataError("snapshot_scope_missing", "Project/Ontology scope is missing")
        ontologies = list(
            self.session.scalars(
                select(m.OntologyModel)
                .where(m.OntologyModel.project_id == project_id, m.OntologyModel.id.in_(ids))
                .order_by(m.OntologyModel.id)
            )
        )
        if [item.id for item in ontologies] != ids:
            raise CheckpointDataError(
                "snapshot_scope_missing", "Ontology scope does not match Project"
            )
        if (
            self.session.scalar(
                select(m.OntologyWriteFenceModel).where(
                    m.OntologyWriteFenceModel.ontology_id.in_(ids)
                )
            )
            is not None
        ):
            raise CheckpointDataError("snapshot_write_unsettled", "An apply fence is still present")

        tables: dict[str, list[dict[str, Any]]] = {}

        def collect(model, condition):
            records = list(self.session.scalars(select(model).where(condition)))
            tables[model.__tablename__] = sorted(
                [_row(record) for record in records],
                key=lambda record: json.dumps(record, sort_keys=True),
            )
            return records

        tables["projects"] = [_row(project)]
        tables["ontologies"] = [_row(item) for item in ontologies]
        for model in (
            m.ProjectBriefModel,
            m.InterviewAnswerModel,
            m.DataSourceModel,
            m.DataResourceModel,
            m.ExternalFieldModel,
            m.SemanticProtectionSetModel,
        ):
            collect(model, model.project_id == project_id)
        for model in (
            m.CompetencyQuestionModel,
            m.SemanticMappingModel,
            m.SemanticRuleModel,
        ):
            collect(model, model.ontology_id.in_(ids))
        collect(
            m.SemanticProtectionSetMemberModel,
            m.SemanticProtectionSetMemberModel.protection_set_id.in_(
                [item["id"] for item in tables["semantic_protection_sets"]]
            ),
        )
        collect(
            m.SemanticRuleDefinitionModel,
            m.SemanticRuleDefinitionModel.semantic_rule_id.in_(
                [item["id"] for item in tables["semantic_rules"]]
            ),
        )
        registries = collect(
            m.SemanticGraphRegistryModel,
            (m.SemanticGraphRegistryModel.semantic_owner_type == "ontology")
            & m.SemanticGraphRegistryModel.semantic_owner_id.in_(ids),
        )
        graph_iris = sorted(item.graph_iri for item in registries)
        sets = collect(
            m.SemanticGraphSetModel,
            (m.SemanticGraphSetModel.scope_type == "ontology")
            & m.SemanticGraphSetModel.scope_id.in_(ids),
        )
        collect(
            m.SemanticGraphSetMemberModel,
            m.SemanticGraphSetMemberModel.graph_set_id.in_([item.id for item in sets]),
        )
        if any(
            item["graph_iri"] not in graph_iris for item in tables["semantic_graph_set_members"]
        ):
            raise CheckpointDataError(
                "snapshot_external_graph", "Graph Set includes an unowned graph"
            )
        for model in (
            m.SemanticGraphRevisionModel,
            m.SemanticGraphStateModel,
        ):
            collect(model, model.graph_iri.in_(graph_iris))
        # Edit audits are shared write records rather than lineage evidence.
        # Keep audits that belong to the captured graphs, including an audit
        # referenced as a graph revision's last edit, while dropping their
        # suspended evidence-status column through ``_row``.
        revision_audit_ids = {
            item.get("last_edit_audit_id")
            for item in tables["semantic_graph_revisions"]
            if item.get("last_edit_audit_id")
        }
        audit_rows = []
        for audit in self.session.scalars(select(m.SemanticEditAuditModel)):
            affected = set(audit.affected_graph_iris or [])
            if (
                audit.id in revision_audit_ids
                or audit.target_graph_iri in graph_iris
                or affected.intersection(graph_iris)
            ):
                audit_rows.append(_row(audit))
        tables["semantic_edit_audits"] = sorted(
            audit_rows,
            key=lambda record: json.dumps(record, sort_keys=True),
        )
        graphs = {
            iri: self.rdf_store.export_named_graph(iri, "turtle")
            if self.rdf_store.graph_exists(iri)
            else ""
            for iri in graph_iris
        }
        completed = []
        for batch in self.session.scalars(
            select(m.ModelingBatchModel)
            .where(m.ModelingBatchModel.ontology_id.in_(ids))
            .order_by(m.ModelingBatchModel.id)
        ):
            for attempt in batch.attempts:
                if attempt.mode == "dry_run":
                    continue
                for result in attempt.item_results:
                    if result.status == "applied":
                        completed.append(
                            {
                                "session_id": batch.build_session_id,
                                "batch_id": batch.id,
                                "attempt_id": attempt.id,
                                "client_item_id": result.client_item_id,
                                "client_batch_id": batch.client_batch_id,
                                "batch_complete": batch.status == "applied",
                                "content_hash": batch.content_hash,
                                "idempotency_key": attempt.idempotency_key,
                            }
                        )
        snapshot = {
            "schema_version": SNAPSHOT_SCHEMA,
            "project_id": project_id,
            "ontology_ids": ids,
            "tables": tables,
            "graphs": graphs,
            "completed_operations": completed,
        }
        snapshot["digest"] = snapshot_digest(snapshot)
        return snapshot

    def fork(
        self,
        snapshot: dict[str, Any],
        *,
        name: str,
        settings: Settings,
        target_project_id: str | None = None,
    ) -> dict[str, Any]:
        """Import only the captured data into fresh identities.

        No old Session, Attempt, lease, credential or execution queue is imported.
        The caller must retain the returned map with its checkpoint lineage.
        """
        if snapshot.get("schema_version") != SNAPSHOT_SCHEMA or snapshot.get(
            "digest"
        ) != snapshot_digest(snapshot):
            raise CheckpointDataError(
                "snapshot_invalid", "Snapshot schema or digest does not match"
            )
        tables = snapshot["tables"]
        model_types = (
            m.ProjectModel,
            m.OntologyModel,
            m.ProjectBriefModel,
            m.InterviewAnswerModel,
            m.DataSourceModel,
            m.DataResourceModel,
            m.ExternalFieldModel,
            m.SemanticGraphRegistryModel,
            m.SemanticGraphRevisionModel,
            m.SemanticGraphStateModel,
            m.SemanticGraphSetModel,
            m.SemanticGraphSetMemberModel,
            m.CompetencyQuestionModel,
            m.SemanticMappingModel,
            m.SemanticProtectionSetModel,
            m.SemanticProtectionSetMemberModel,
            m.SemanticRuleModel,
            m.SemanticRuleDefinitionModel,
            m.SemanticEditAuditModel,
        )
        if set(tables) != {model.__tablename__ for model in model_types}:
            raise CheckpointDataError("snapshot_invalid", "Snapshot table inventory does not match")
        target_project_id = target_project_id or str(uuid4())
        namespace = UUID(target_project_id)
        if self.session.get(m.ProjectModel, target_project_id) is not None:
            raise CheckpointDataError(
                "fork_target_exists", "Target Project already exists; inspect its receipt"
            )
        mapping = {
            row["id"]: str(uuid5(namespace, row["id"]))
            for rows in tables.values()
            for row in rows
            if "id" in row
        }
        source_project = snapshot["project_id"]
        mapping[source_project] = target_project_id
        source_ontologies = snapshot["ontology_ids"]
        if (
            len(tables["projects"]) != 1
            or tables["projects"][0]["id"] != source_project
            or sorted(row["id"] for row in tables["ontologies"]) != source_ontologies
        ):
            raise CheckpointDataError("snapshot_invalid", "Snapshot scope does not match its rows")
        graph_mapping = {}
        for row in tables["semantic_graph_registry"]:
            owner = row["semantic_owner_id"]
            if owner not in source_ontologies:
                raise CheckpointDataError("snapshot_invalid", "Snapshot graph has a foreign owner")
            old = row["graph_iri"]
            # Default workspace IRIs are deterministic from the new Ontology.
            source_prefix = (
                f"{settings.semantic_graph_iri_prefix.rstrip('/')}/{row['category']}/{owner}"
            )
            target_prefix = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/{row['category']}/{mapping[owner]}"
            graph_mapping[old] = (
                target_prefix + old[len(source_prefix) :]
                if old == source_prefix or old.startswith(source_prefix + "/")
                else f"{settings.semantic_graph_iri_prefix.rstrip('/')}/fork/{uuid4()}"
            )
        if set(graph_mapping) != set(snapshot["graphs"]):
            raise CheckpointDataError("snapshot_invalid", "Snapshot graph inventory does not match")
        mapping.update(graph_mapping)

        def remap(value):
            if isinstance(value, str):
                return mapping.get(value, value)
            if isinstance(value, list):
                return [remap(item) for item in value]
            if isinstance(value, dict):
                return {mapping.get(key, key): remap(item) for key, item in value.items()}
            return value

        prepared_graphs = {}
        for old, content in snapshot["graphs"].items():
            graph = Graph().parse(data=content, format="turtle")
            rewritten = Graph()
            for triple in graph:
                rewritten.add(
                    tuple(
                        URIRef(graph_mapping[str(term)])
                        if isinstance(term, URIRef) and str(term) in graph_mapping
                        else term
                        for term in triple
                    )
                )
            prepared_graphs[graph_mapping[old]] = rewritten.serialize(format="turtle")

        written_graphs = []
        try:
            for model in model_types:
                for original in tables[model.__tablename__]:
                    data = {
                        key: remap(value)
                        if (
                            key == "id"
                            or key.endswith(("_id", "_ids", "_iri", "_iris"))
                            or isinstance(value, (dict, list))
                        )
                        else value
                        for key, value in original.items()
                    }
                    for prop in inspect(model).column_attrs:
                        value = data.get(prop.key)
                        python_type = prop.columns[0].type.python_type
                        if python_type is datetime and value is not None:
                            data[prop.key] = datetime.fromisoformat(value["datetime"])
                        elif python_type is bytes and value is not None:
                            data[prop.key] = base64.b64decode(value["base64"], validate=True)
                    if model is m.ProjectModel:
                        data.update(name=name, normalized_label=name)
                    elif model is m.OntologyModel:
                        data["external_mappings"].pop(ARCHIVE_KEY, None)
                        data["external_mappings"]["checkpoint_fork_origin"] = {
                            "source_project_id": source_project,
                            "source_ontology_id": original["id"],
                            "snapshot_digest": snapshot["digest"],
                        }
                    elif model is m.SemanticRuleModel:
                        data["current_definition_id"] = None  # resolve FK cycle below
                    self.session.add(model(**data))
                self.session.flush()
            for original in tables["semantic_rules"]:
                if original["current_definition_id"]:
                    self.session.get(
                        m.SemanticRuleModel, mapping[original["id"]]
                    ).current_definition_id = mapping[original["current_definition_id"]]
            for iri, content in prepared_graphs.items():
                written_graphs.append(iri)  # include a PUT with an uncertain response
                self.rdf_store.put_named_graph(iri, content, "turtle")
                revision = self.session.scalar(
                    select(m.SemanticGraphRevisionModel).where(
                        m.SemanticGraphRevisionModel.graph_iri == iri
                    )
                )
                if revision is not None:
                    revision.content_hash = self.rdf_store.graph_content_hash(iri)
            for old_id in source_ontologies:
                OntologyWorkspaceService(self.session, settings).ensure(
                    self.session.get(m.OntologyModel, mapping[old_id])
                )
            for source in self.session.scalars(
                select(m.OntologyModel)
                .where(m.OntologyModel.project_id == source_project)
                .order_by(m.OntologyModel.id)
                .with_for_update()
            ):
                source.status = "archived"
                source.external_mappings = {
                    **source.external_mappings,
                    ARCHIVE_KEY: {
                        "target_project_id": mapping[source_project],
                        "snapshot_digest": snapshot["digest"],
                    },
                }
        except Exception as exc:
            self.session.rollback()
            remaining = []
            for iri in written_graphs:
                try:
                    self.rdf_store.drop_named_graph(iri)
                except Exception:
                    remaining.append(iri)
            if remaining:
                raise CheckpointDataError(
                    "fork_cleanup_incomplete", "New graphs require cleanup: " + ", ".join(remaining)
                ) from exc
            raise
        try:
            self.session.commit()
        except Exception as exc:
            # A lost COMMIT response is not proof that SQL rolled back. Keep
            # the new graphs and the caller's preallocated target identity for
            # readback; deleting them could corrupt an already committed fork.
            self.session.rollback()
            raise CheckpointDataError(
                "fork_commit_unknown",
                f"Confirm Project {target_project_id} before retrying; new graphs are retained",
            ) from exc
        return {
            "project_id": mapping[source_project],
            "ontology_ids": [mapping[item] for item in source_ontologies],
            "source_project_id": source_project,
            "snapshot_digest": snapshot["digest"],
            "identity_mapping": mapping,
            "derived_results": "recompute_required",
        }
