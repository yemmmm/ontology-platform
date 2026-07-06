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
from app.services.semantic_shape_guidance_reader import extract_shape_guidance_for_class
from app.services.semantic_shape_generator import generate_shapes
from app.services.semantic_shape_merge import merge_shape_guidance


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

        ontology_graph = self._load_graph(ontology_graph_iri)
        generated_shapes = generate_shapes(ontology_graph)
        generated_guidance = extract_shape_guidance_for_class(generated_shapes, class_iri)

        custom_graph_iri = self.ns.graph("shapes", ontology_id).__str__() + "/custom"
        custom_guidance: dict[str, Any] = {"fields": []}
        try:
            custom_graph = self._load_graph(custom_graph_iri)
        except Exception:
            custom_graph = Graph()
        if len(custom_graph) > 0:
            custom_guidance = extract_shape_guidance_for_class(custom_graph, class_iri)

        merged = merge_shape_guidance(generated_guidance, custom_guidance)
        merged["graph_set_id"] = graph_set_id
        merged["generated_graph_iri"] = str(ontology_graph_iri)
        merged["custom_graph_iri"] = custom_graph_iri
        merged["shape_split"] = {
            "generated_subgraph": self.ns.graph("shapes", ontology_id).__str__() + "/generated",
            "custom_subgraph": custom_graph_iri,
        }
        return merged

    @staticmethod
    def _find_ontology_graph(members: list[dict[str, Any]]) -> str | None:
        for member in members:
            if member.get("role") == "asserted_ontology":
                return member["graph_iri"]
        return None

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
