from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from app.services.owl_reasoner import CommandOwlReasonerRunner, ReasonerInputDocument


def test_dev_owl_reasoner_command_infers_rdfs_subclass_types() -> None:
    command = Path(__file__).parents[1] / "scripts" / "dev_owl_reasoner.py"
    runner = CommandOwlReasonerRunner(str(command))

    result = runner.run(
        [
            ReasonerInputDocument(
                graph_iri="http://ontology-platform.local/semantic/graph/test",
                content="""
                    @prefix ex: <http://example.test/> .
                    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

                    ex:a a ex:Child .
                    ex:a ex:contains ex:b .
                    ex:Child rdfs:subClassOf ex:Parent .
                    ex:Parent rdfs:subClassOf ex:Root .
                    ex:contains rdfs:subPropertyOf ex:dependsOn .
                    ex:dependsOn rdfs:subPropertyOf ex:relatedTo .
                """,
            )
        ],
        tasks=["consistency", "classification"],
        timeout_seconds=5,
    )

    assert result.consistent is True
    assert result.classification["mode"] == "development_stub"
    assert result.classification["source_graph_count"] == 1
    assert {
        "kind": "rdfs_subclass_type",
        "subject": "http://example.test/a",
        "predicate": str(RDF.type),
        "object": "http://example.test/Parent",
        "source_class": "http://example.test/Child",
        "rule": "rdfs:subClassOf",
    } in result.entailments
    assert {
        "kind": "rdfs_subclass_type",
        "subject": "http://example.test/a",
        "predicate": str(RDF.type),
        "object": "http://example.test/Root",
        "source_class": "http://example.test/Child",
        "rule": "rdfs:subClassOf",
    } in result.entailments
    assert {
        "kind": "rdfs_subproperty_assertion",
        "subject": "http://example.test/a",
        "predicate": "http://example.test/dependsOn",
        "object": "http://example.test/b",
        "source_property": "http://example.test/contains",
        "rule": "rdfs:subPropertyOf",
    } in result.entailments
    assert {
        "kind": "rdfs_subproperty_assertion",
        "subject": "http://example.test/a",
        "predicate": "http://example.test/relatedTo",
        "object": "http://example.test/b",
        "source_property": "http://example.test/contains",
        "rule": "rdfs:subPropertyOf",
    } in result.entailments
    assert result.inferred_rdf is not None
    inferred_graph = Graph()
    inferred_graph.parse(data=result.inferred_rdf, format="turtle")
    assert (
        URIRef("http://example.test/a"),
        RDF.type,
        URIRef("http://example.test/Parent"),
    ) in inferred_graph
    assert (
        URIRef("http://example.test/a"),
        RDF.type,
        URIRef("http://example.test/Root"),
    ) in inferred_graph
    assert (
        URIRef("http://example.test/a"),
        URIRef("http://example.test/dependsOn"),
        URIRef("http://example.test/b"),
    ) in inferred_graph
    assert (
        URIRef("http://example.test/a"),
        URIRef("http://example.test/relatedTo"),
        URIRef("http://example.test/b"),
    ) in inferred_graph
    assert result.metadata["engine_name"] == "development_stub"
