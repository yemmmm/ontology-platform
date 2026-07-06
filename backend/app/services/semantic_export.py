from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from rdflib import Namespace
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, XSD

from app.core.config import Settings

PROV = Namespace("http://www.w3.org/ns/prov#")


@dataclass(frozen=True)
class SemanticNamespace:
    base_iri: str
    graph_iri_prefix: str

    @property
    def vocab(self) -> Namespace:
        return Namespace(f"{self.base_iri.rstrip('/')}/vocab/")

    def resource(self, kind: str, identifier: str):
        from rdflib import URIRef

        return URIRef(f"{self.base_iri.rstrip('/')}/{kind}/{quote(str(identifier), safe='')}")

    def graph(self, kind: str, identifier: str):
        from rdflib import URIRef

        return URIRef(f"{self.graph_iri_prefix.rstrip('/')}/{kind}/{quote(str(identifier), safe='')}")


def namespace_from_settings(settings: Settings) -> SemanticNamespace:
    return SemanticNamespace(settings.semantic_base_iri, settings.semantic_graph_iri_prefix)


def jsonld_context(settings: Settings) -> dict[str, Any]:
    ns = namespace_from_settings(settings)
    vocab = str(ns.vocab)
    return {
        "@version": 1.1,
        "@vocab": vocab,
        "op": vocab,
        "rdf": str(RDF),
        "rdfs": str(RDFS),
        "owl": str(OWL),
        "skos": str(SKOS),
        "sh": str(SH),
        "prov": str(PROV),
        "xsd": str(XSD),
        "id": "@id",
        "type": "@type",
        "label": "rdfs:label",
        "description": "rdfs:comment",
        "alias": "skos:altLabel",
        "sameAs": {"@id": "owl:sameAs", "@type": "@id"},
        "project": {"@id": f"{vocab}project", "@type": "@id"},
        "ontology": {"@id": f"{vocab}ontology", "@type": "@id"},
        "version": {"@id": f"{vocab}version", "@type": "@id"},
        "graph": {"@id": f"{vocab}graph", "@type": "@id"},
        "class": {"@id": f"{vocab}class", "@type": "@id"},
        "property": {"@id": f"{vocab}property", "@type": "@id"},
        "relationType": {"@id": f"{vocab}relationType", "@type": "@id"},
        "source": {"@id": f"{vocab}source", "@type": "@id"},
        "target": {"@id": f"{vocab}target", "@type": "@id"},
        "evidence": {"@id": f"{vocab}evidence", "@type": "@id"},
        "evidenceStatus": f"{vocab}evidenceStatus",
        "auditStatus": f"{vocab}auditStatus",
        "confidence": {"@id": f"{vocab}confidence", "@type": "xsd:decimal"},
        "createdAt": {"@id": "prov:generatedAtTime", "@type": "xsd:dateTime"},
        "updatedAt": {"@id": f"{vocab}updatedAt", "@type": "xsd:dateTime"},
        "editable": {"@id": f"{vocab}editable", "@type": "xsd:boolean"},
        "validationRun": {"@id": f"{vocab}validationRun", "@type": "@id"},
        "reasoningRun": {"@id": f"{vocab}reasoningRun", "@type": "@id"},
        "ruleRun": {"@id": f"{vocab}ruleRun", "@type": "@id"},
        "connector": {"@id": f"{vocab}connector", "@type": "@id"},
    }
