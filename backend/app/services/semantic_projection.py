from dataclasses import dataclass

from neo4j import Driver
from rdflib import Dataset, URIRef

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository


@dataclass
class SemanticProjectionResult:
    node_count: int
    relationship_count: int
    metadata: dict[str, object]


class SemanticProjectionService:
    def __init__(self, rdf_store: RdfStoreRepository, driver: Driver | None = None) -> None:
        self.rdf_store = rdf_store
        self.driver = driver

    def rebuild(
        self,
        source_graph_iris: list[str],
        reasoning_result_graph_iri: str | None = None,
        job_id: str | None = None,
    ) -> SemanticProjectionResult:
        dataset = Dataset()
        graph_iris = list(source_graph_iris)
        if reasoning_result_graph_iri:
            graph_iris.append(reasoning_result_graph_iri)
        for graph_iri in graph_iris:
            content = self.rdf_store.get_graph(graph_iri, RdfFormat.TRIG.value)
            dataset.parse(data=content, format=RdfFormat.TRIG.value)

        nodes: set[str] = set()
        relationships: set[tuple[str, str, str]] = set()
        for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
            if isinstance(subject, URIRef):
                nodes.add(str(subject))
            if isinstance(obj, URIRef):
                nodes.add(str(obj))
                relationships.add((str(subject), str(predicate), str(obj)))

        if self.driver is not None and job_id is not None:
            self._replace_projection(job_id, nodes, relationships)

        return SemanticProjectionResult(
            node_count=len(nodes),
            relationship_count=len(relationships),
            metadata={"graph_iris": graph_iris, "job_id": job_id},
        )

    def _replace_projection(
        self,
        job_id: str,
        nodes: set[str],
        relationships: set[tuple[str, str, str]],
    ) -> None:
        assert self.driver is not None
        with self.driver.session() as session:
            session.run("MATCH (n:SemanticProjection) DETACH DELETE n")
            for iri in nodes:
                session.run(
                    "MERGE (n:SemanticProjection {iri: $iri}) SET n.projection_job_id = $job_id",
                    iri=iri,
                    job_id=job_id,
                )
            for source, predicate, target in relationships:
                session.run(
                    """
                    MATCH (s:SemanticProjection {iri: $source})
                    MATCH (t:SemanticProjection {iri: $target})
                    MERGE (s)-[r:RDF_RELATION {predicate: $predicate}]->(t)
                    SET r.projection_job_id = $job_id
                    """,
                    source=source,
                    target=target,
                    predicate=predicate,
                    job_id=job_id,
                )
