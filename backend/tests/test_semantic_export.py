"""Tests for the trimmed-down semantic_export module.

Stage 3 B2 hard-cut: the legacy ontology-dataset / SHACL / compact-projection
builders (which depended on FactClaimModel/EvidenceModel and the deleted
import_export service) were removed. Only ``SemanticNamespace``,
``namespace_from_settings`` and ``jsonld_context`` remain — they back the
semantic graph-set export, command compiler, and shape endpoint services.
"""

from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, XSD

from app.core.config import Settings
from app.services import semantic_export


SETTINGS = Settings(_env_file=None)
NS = semantic_export.namespace_from_settings(SETTINGS)


def test_namespace_from_settings_round_trips_settings() -> None:
    assert NS.base_iri == SETTINGS.semantic_base_iri
    assert NS.graph_iri_prefix == SETTINGS.semantic_graph_iri_prefix
    assert str(NS.vocab) == f"{SETTINGS.semantic_base_iri.rstrip('/')}/vocab/"


def test_namespace_resource_and_graph_quote_identifiers() -> None:
    # / is encoded as %2F so IRI stays a single path segment.
    assert str(NS.resource("class", "a/b")) == (
        f"{SETTINGS.semantic_base_iri.rstrip('/')}/class/a%2Fb"
    )
    assert str(NS.graph("data", "ont-1")) == (
        f"{SETTINGS.semantic_graph_iri_prefix.rstrip('/')}/data/ont-1"
    )


def test_jsonld_context_binds_core_namespaces_and_terms() -> None:
    context = semantic_export.jsonld_context(SETTINGS)
    vocab = str(NS.vocab)

    assert context["@vocab"] == vocab
    assert context["op"] == vocab
    assert context["rdf"] == str(RDF)
    assert context["rdfs"] == str(RDFS)
    assert context["owl"] == str(OWL)
    assert context["skos"] == str(SKOS)
    assert context["sh"] == str(SH)
    assert context["xsd"] == str(XSD)

    # Spot-check a few json-ld term mappings that downstream services rely on.
    assert context["id"] == "@id"
    assert context["type"] == "@type"
    assert context["label"] == "rdfs:label"
    assert context["description"] == "rdfs:comment"
    assert context["alias"] == "skos:altLabel"
    assert context["sameAs"] == {"@id": "owl:sameAs", "@type": "@id"}
    assert context["project"] == {"@id": f"{vocab}project", "@type": "@id"}
    assert context["ontology"] == {"@id": f"{vocab}ontology", "@type": "@id"}
    assert context["evidenceStatus"] == f"{vocab}evidenceStatus"
    assert context["confidence"] == {"@id": f"{vocab}confidence", "@type": "xsd:decimal"}
    assert context["createdAt"] == {"@id": "prov:generatedAtTime", "@type": "xsd:dateTime"}
