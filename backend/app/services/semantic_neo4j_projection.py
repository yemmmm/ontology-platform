"""Neo4j projection writer scoped by graph set + projection version partition.

Each projection rebuild clears only the target partition (identified by
``partition`` and tagged on every node/relationship), writes fresh nodes
and relationships from the RDF graph set, and returns counts. The caller
(``SemanticProjectionJobService``) is responsible for manifest promotion.
"""

from __future__ import annotations

from neo4j import Driver
from rdflib import Dataset, URIRef

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class Neo4jSemanticProjectionService(ProjectionWriter):
    kind = "neo4j"

    def __init__(
        self, rdf_store: RdfStoreRepository, driver: Driver | None
    ) -> None:
        self.rdf_store = rdf_store
        self.driver = driver

    def rebuild(
        self, job_id: str, scope: ScopeResolution, partition: str
    ) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        nodes: set[str] = set()
        relationships: set[tuple[str, str, str]] = set()
        for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
            if isinstance(subject, URIRef):
                nodes.add(str(subject))
            if isinstance(obj, URIRef):
                nodes.add(str(obj))
                relationships.add((str(subject), str(predicate), str(obj)))
        if self.driver is None:
            return {
                "node_count": len(nodes),
                "relationship_count": len(relationships),
                "document_count": 0,
            }
        self._replace_projection(job_id, scope, partition, nodes, relationships)
        return {
            "node_count": len(nodes),
            "relationship_count": len(relationships),
            "document_count": 0,
        }

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        iris = list(scope.source_graph_iris)
        if scope.reasoning_result_graph_iri:
            iris.append(scope.reasoning_result_graph_iri)
        if scope.rule_result_graph_iri:
            iris.append(scope.rule_result_graph_iri)
        for iri in iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _replace_projection(
        self,
        job_id: str,
        scope: ScopeResolution,
        partition: str,
        nodes: set[str],
        relationships: set[tuple[str, str, str]],
    ) -> None:
        assert self.driver is not None
        with self.driver.session() as session:
            session.run(
                """
                MATCH (n:SemanticProjection {partition: $partition})
                DETACH DELETE n
                """,
                partition=partition,
            )
            for iri in nodes:
                session.run(
                    """
                    MERGE (n:SemanticProjection {iri: $iri, partition: $partition})
                    SET n.projection_job_id = $job_id,
                        n.graph_set_id = $graph_set_id,
                        n.source_signature = $source_signature
                    """,
                    iri=iri,
                    partition=partition,
                    job_id=job_id,
                    graph_set_id=scope.graph_set_id,
                    source_signature=scope.source_signature,
                )
            for source, predicate, target in relationships:
                session.run(
                    """
                    MATCH (s:SemanticProjection {iri: $source, partition: $partition})
                    MATCH (t:SemanticProjection {iri: $target, partition: $partition})
                    MERGE (s)-[r:RDF_RELATION {predicate: $predicate, partition: $partition}]->(t)
                    SET r.projection_job_id = $job_id,
                        r.graph_set_id = $graph_set_id
                    """,
                    source=source,
                    target=target,
                    predicate=predicate,
                    partition=partition,
                    job_id=job_id,
                    graph_set_id=scope.graph_set_id,
                )
