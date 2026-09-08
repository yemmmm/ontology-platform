"""Service that powers GET /graph-sets/{gs}/shapes/classes/{class_iri}.

Stage 2 §3.4: returns merged SHACL form guidance for one class. Reads
the asserted ontology graph for the graph set, runs the OWL→SHACL
generator in memory, reads the custom shape sub-graph if present, and
returns the merged guidance with per-field provenance.

For MVP the generated shapes are recomputed on each request. The
generator trigger (Stage 2 task 421) will pre-materialize them.
"""

from __future__ import annotations

from typing import Any

from rdflib import Graph
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_shape_guidance_reader import (
    entity_class_iris,
    entity_subject_predicates,
    extract_shape_guidance_for_class,
    extract_shape_guidance_for_targets,
)
from app.services.semantic_shape_generator import generate_shapes
from app.services.semantic_shape_merge import merge_shape_guidance_multi


class ShapeEndpointError(RuntimeError):
    status_code = 400


class GraphSetNotFound(ShapeEndpointError):
    status_code = 404


class OntologyGraphMissing(ShapeEndpointError):
    status_code = 409


class SemanticShapeEndpointService:
    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        settings: Settings,
        graph_set_service: SemanticGraphSetService | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.settings = settings
        self.ns = namespace_from_settings(settings)
        self.graph_set_service = graph_set_service or SemanticGraphSetService(session, settings)

    def read_merged_guidance(
        self,
        graph_set_id: str,
        class_iri: str,
    ) -> dict[str, Any]:
        description = self.graph_set_service.describe(graph_set_id)
        if description is None:
            raise GraphSetNotFound(f"Graph set not found: {graph_set_id}")
        ontology_graph_iri = self._find_ontology_graph(description["members"])
        if ontology_graph_iri is None:
            raise OntologyGraphMissing(
                f"Graph set {graph_set_id} has no asserted_ontology member"
            )
        ontology_id = self._ontology_id_from_graph_iri(ontology_graph_iri)

        missing_graph_iris: list[str] = []
        ontology_graph = self._load_graph_or_empty(
            ontology_graph_iri, missing=missing_graph_iris
        )
        generated_shapes = generate_shapes(
            ontology_graph, base_iri=self._generated_shapes_iri(ontology_id)
        )
        generated_guidance = extract_shape_guidance_for_class(generated_shapes, class_iri)

        custom_graph_iri = self.ns.graph("shapes", ontology_id).__str__() + "/custom"
        custom_guidance: dict[str, Any] = {"fields": []}
        custom_graph = self._load_optional_graph(custom_graph_iri)
        if custom_graph is not None and len(custom_graph) > 0:
            custom_guidance = extract_shape_guidance_for_class(custom_graph, class_iri)

        merged = self._merge_class_guidance(
            generated_label=f"generated:{ontology_graph_iri}",
            generated_guidance=generated_guidance,
            custom_label=f"custom:{custom_graph_iri}",
            custom_guidance=custom_guidance,
        )
        merged["graph_set_id"] = graph_set_id
        merged["generated_graph_iri"] = str(ontology_graph_iri)
        merged["custom_graph_iri"] = custom_graph_iri
        merged["shape_split"] = {
            "generated_subgraph": self.ns.graph("shapes", ontology_id).__str__() + "/generated",
            "custom_subgraph": custom_graph_iri,
        }
        merged["missing_graph_iris"] = sorted(missing_graph_iris)
        return merged

    @staticmethod
    def _merge_class_guidance(
        *,
        generated_label: str,
        generated_guidance: dict[str, Any],
        custom_label: str,
        custom_guidance: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge class guidance and keep the legacy per-field provenance (F08).

        Conflict detection runs on the pre-merge, per-shape constraints from
        both sources (``merge_shape_guidance_multi``), so two still-effective
        shapes that bind one path differently raise ``shape_conflict`` instead
        of the reader silently keeping the first or last constraint. The output
        envelope stays the one the class endpoint has always returned:
        ``provenance`` is ``generated`` / ``custom`` / ``merged``.
        """
        merged = merge_shape_guidance_multi(
            [
                (generated_label, generated_guidance),
                (custom_label, custom_guidance),
            ]
        )
        for field in merged["fields"]:
            sources = field.get("sources") or []
            if not sources:
                field["provenance"] = "generated"
            elif all(source.startswith("generated:") for source in sources):
                field["provenance"] = "generated"
            elif all(source.startswith("custom:") for source in sources):
                field["provenance"] = "custom"
            else:
                field["provenance"] = "merged"
        result: dict[str, Any] = {"fields": merged["fields"]}
        target_class = custom_guidance.get("target_class") or generated_guidance.get(
            "target_class"
        )
        if target_class is not None:
            result["target_class"] = target_class
        target_class_label = custom_guidance.get("target_class_label") or (
            generated_guidance.get("target_class_label")
        )
        if target_class_label is not None:
            result["target_class_label"] = target_class_label
        shape_iri = custom_guidance.get("shape_iri") or generated_guidance.get("shape_iri")
        if shape_iri is not None:
            result["shape_iri"] = shape_iri
        return result

    @staticmethod
    def _find_ontology_graph(members: list[dict[str, Any]]) -> str | None:
        for member in members:
            if member.get("role") == "asserted_ontology":
                return member["graph_iri"]
        return None

    def read_entity_guidance(self, graph_set_id: str, entity_iri: str) -> dict[str, Any]:
        """Merged SHACL guidance for one entity (R3.0-009 §6.1).

        Collects the entity's full formal class set, the predicates it actually
        uses as a subject and its node target, then matches generated and
        custom shapes across **every** authorized ``asserted_ontology`` member
        of the graph set (plus each ontology's custom sub-graph). Sources are
        merged without dropping still-effective constraints; conflicting
        constraints raise ``ShapeGuidanceConflict``.
        """
        description = self.graph_set_service.describe(graph_set_id)
        if description is None:
            raise GraphSetNotFound(f"Graph set not found: {graph_set_id}")
        members = description["members"]
        ontology_graph_iris = [
            member["graph_iri"]
            for member in members
            if member.get("role") == "asserted_ontology"
        ]
        data_graph_iris = [
            member["graph_iri"]
            for member in members
            if member.get("role") == "asserted_data"
        ]
        if not ontology_graph_iris:
            raise OntologyGraphMissing(
                f"Graph set {graph_set_id} has no asserted_ontology member"
            )

        class_iris: set[str] = set()
        subject_predicates: set[str] = set()
        missing_graph_iris: list[str] = []
        for graph_iri in data_graph_iris:
            data_graph = self._load_graph_or_empty(graph_iri, missing=missing_graph_iris)
            class_iris.update(entity_class_iris(data_graph, entity_iri))
            subject_predicates.update(entity_subject_predicates(data_graph, entity_iri))

        sources: list[tuple[str, dict[str, Any]]] = []
        for ontology_graph_iri in ontology_graph_iris:
            ontology_id = self._ontology_id_from_graph_iri(ontology_graph_iri)
            custom_graph_iri = (
                self.ns.graph("shapes", ontology_id).__str__() + "/custom"
            )
            ontology_graph = self._load_graph_or_empty(
                ontology_graph_iri, missing=missing_graph_iris
            )
            sources.append(
                (
                    f"generated:{ontology_graph_iri}",
                    extract_shape_guidance_for_targets(
                        generate_shapes(
                            ontology_graph,
                            base_iri=self._generated_shapes_iri(ontology_id),
                        ),
                        class_iris=class_iris,
                        target_node_iri=entity_iri,
                        subject_predicates=subject_predicates,
                    ),
                )
            )
            custom_graph = self._load_optional_graph(custom_graph_iri)
            if custom_graph is not None and len(custom_graph) > 0:
                sources.append(
                    (
                        f"custom:{custom_graph_iri}",
                        extract_shape_guidance_for_targets(
                            custom_graph,
                            class_iris=class_iris,
                            target_node_iri=entity_iri,
                            subject_predicates=subject_predicates,
                        ),
                    )
                )

        merged = merge_shape_guidance_multi(sources)
        merged["entity_iri"] = entity_iri
        merged["class_iris"] = sorted(class_iris)
        merged["subject_predicates"] = sorted(subject_predicates)
        merged["graph_set_id"] = graph_set_id
        merged["generated_graph_iri"] = ontology_graph_iris[0]
        merged["custom_graph_iris"] = [
            self.ns.graph("shapes", self._ontology_id_from_graph_iri(iri)).__str__()
            + "/custom"
            for iri in ontology_graph_iris
        ]
        merged["shape_split"] = {
            "generated_subgraph": ontology_graph_iris[0],
            "custom_subgraphs": merged["custom_graph_iris"],
        }
        merged["missing_graph_iris"] = sorted(missing_graph_iris)
        return merged

    def _generated_shapes_iri(self, ontology_id: str) -> str:
        """Base IRI of the derived generated shapes sub-graph (Stage 2 §3.4)."""
        return self.ns.graph("shapes", ontology_id).__str__() + "/generated"

    def _ontology_id_from_graph_iri(self, graph_iri: str) -> str:
        prefix = self.settings.semantic_graph_iri_prefix
        if not graph_iri.startswith(prefix):
            raise ShapeEndpointError(
                f"Ontology graph IRI outside managed prefix: {graph_iri}"
            )
        suffix = graph_iri[len(prefix):]
        parts = suffix.split("/")
        if len(parts) < 2 or parts[0] != "ontology":
            raise ShapeEndpointError(
                f"Unable to derive ontology_id from graph IRI: {graph_iri}"
            )
        return parts[1]

    def _load_graph(self, graph_iri: str) -> Graph:
        content = self.rdf_store.get_graph(graph_iri, RdfFormat.TURTLE.value)
        graph = Graph()
        if content:
            graph.parse(data=content, format="turtle")
        return graph

    def _load_graph_or_empty(self, graph_iri: str, *, missing: list[str]) -> Graph:
        """Read a consulted graph that may not be materialized yet (D14).

        Workspace graphs are created lazily, so "no such graph" is an empty
        projection, not a store failure; the IRI is reported in the envelope's
        ``missing_graph_iris`` instead of surfacing as HTTP 500. An unavailable
        store or an unparseable graph still propagates.
        """
        exists = getattr(self.rdf_store, "graph_exists", None)
        if exists is not None and not exists(graph_iri):
            if graph_iri not in missing:
                missing.append(graph_iri)
            return Graph()
        return self._load_graph(graph_iri)

    def _load_optional_graph(self, graph_iri: str) -> Graph | None:
        """Load a named graph that may not exist yet (R3.0-009 §6.1).

        A missing custom sub-graph is a normal empty state, so it returns
        ``None``. Anything else — an unavailable store or an unparseable
        graph — propagates instead of being read as "no shape guidance".
        """
        exists = getattr(self.rdf_store, "graph_exists", None)
        if exists is not None and not exists(graph_iri):
            return None
        return self._load_graph(graph_iri)
