from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from neo4j import Driver
from rdflib import BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, XSD
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import EvidenceModel, FactClaimModel
from app.services import import_export

PROV = Namespace("http://www.w3.org/ns/prov#")


@dataclass(frozen=True)
class SemanticNamespace:
    base_iri: str
    graph_iri_prefix: str

    @property
    def vocab(self) -> Namespace:
        return Namespace(f"{self.base_iri.rstrip('/')}/vocab/")

    def resource(self, kind: str, identifier: str) -> URIRef:
        return URIRef(f"{self.base_iri.rstrip('/')}/{kind}/{quote(str(identifier), safe='')}")

    def graph(self, kind: str, identifier: str) -> URIRef:
        return URIRef(f"{self.graph_iri_prefix.rstrip('/')}/{kind}/{quote(str(identifier), safe='')}")

    def enum_value(self, property_id: str, value: str) -> URIRef:
        return URIRef(
            f"{self.base_iri.rstrip('/')}/enum/{quote(str(property_id), safe='')}/"
            f"{quote(str(value), safe='')}"
        )


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


def semantic_iri_manifest(settings: Settings, ontology_id: str | None = None) -> dict[str, str]:
    ns = namespace_from_settings(settings)
    suffix = ontology_id or "{ontology_id}"
    return {
        "project": f"{ns.base_iri.rstrip('/')}/project/{{project_id}}",
        "ontology": f"{ns.base_iri.rstrip('/')}/ontology/{{ontology_id}}",
        "version": f"{ns.base_iri.rstrip('/')}/version/{{version_id}}",
        "class": f"{ns.base_iri.rstrip('/')}/class/{{class_id}}",
        "property": f"{ns.base_iri.rstrip('/')}/property/{{property_id}}",
        "relation_type": f"{ns.base_iri.rstrip('/')}/relation-type/{{relation_type_id}}",
        "entity": f"{ns.base_iri.rstrip('/')}/entity/{{entity_id}}",
        "relation": f"{ns.base_iri.rstrip('/')}/relation/{{relation_id}}",
        "fact_claim": f"{ns.base_iri.rstrip('/')}/fact-claim/{{fact_claim_id}}",
        "evidence": f"{ns.base_iri.rstrip('/')}/evidence/{{evidence_id}}",
        "ontology_graph": str(ns.graph("ontology", suffix)),
        "data_graph": str(ns.graph("data", suffix)),
        "shape_graph": str(ns.graph("shapes", suffix)),
    }


def export_ontology_semantic(
    session: Session,
    driver: Driver,
    settings: Settings,
    ontology_id: str,
    format: str,
) -> str:
    export = import_export.export_ontology(session, driver, ontology_id)
    dataset = build_ontology_dataset(
        export,
        namespace_from_settings(settings),
        _fact_claims(session, ontology_id),
        _evidence(session, ontology_id),
    )
    return _serialize_dataset(dataset, format, context=jsonld_context(settings))


def export_ontology_shapes(
    session: Session,
    driver: Driver,
    settings: Settings,
    ontology_id: str,
    format: str,
) -> str:
    export = import_export.export_ontology(session, driver, ontology_id)
    graph = build_shacl_shapes(export, namespace_from_settings(settings))
    return _serialize_graph(graph, format, context=jsonld_context(settings))


def compact_projection_from_semantic_export(content: str, format: str) -> dict[str, Any]:
    graph = Graph()
    if format == "trig":
        dataset = Dataset()
        dataset.parse(data=content, format="trig")
        _copy_dataset(dataset, graph)
    else:
        graph.parse(data=content, format=_rdflib_format(format))
    op = _op_from_graph(graph)
    return {
        "classes": _project_classes(graph, op),
        "relation_types": _project_relation_types(graph, op),
        "entities": _project_entities(graph, op),
        "relations": _project_relations(graph, op),
        "fact_claims": _project_fact_claims(graph, op),
    }


def build_ontology_dataset(
    export: dict[str, Any],
    ns: SemanticNamespace,
    fact_claims: list[FactClaimModel] | None = None,
    evidence_rows: list[EvidenceModel] | None = None,
) -> Dataset:
    dataset = Dataset()
    _bind(dataset, ns)
    ontology = export["ontology"]
    ontology_graph = dataset.graph(ns.graph("ontology", ontology["id"]))
    data_graph = dataset.graph(ns.graph("data", ontology["id"]))
    evidence_graph = dataset.graph(ns.graph("evidence", ontology["project_id"]))
    _bind(ontology_graph, ns)
    _bind(data_graph, ns)
    _bind(evidence_graph, ns)
    _add_schema_graph(ontology_graph, export, ns)
    _add_data_graph(data_graph, export, ns)
    _add_fact_claims(data_graph, fact_claims or [], ns)
    _add_evidence(evidence_graph, evidence_rows or [], ns)
    return dataset


def build_shacl_shapes(export: dict[str, Any], ns: SemanticNamespace) -> Graph:
    graph = Graph(identifier=ns.graph("shapes", export["ontology"]["id"]))
    _bind(graph, ns)
    op = ns.vocab
    property_by_name = _properties_by_class_and_name(export)
    for class_ in export["classes"]:
        shape = ns.resource("shape", f"{class_['id']}-node")
        class_iri = ns.resource("class", class_["id"])
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, class_iri))
        graph.add((shape, RDFS.label, Literal(f"{class_['name']} shape")))
        for prop in class_.get("properties", []):
            property_shape = BNode()
            graph.add((shape, SH.property, property_shape))
            graph.add((property_shape, SH.path, ns.resource("property", prop["id"])))
            if prop.get("required"):
                graph.add((property_shape, SH.minCount, Literal(1)))
            if not prop.get("multi_valued"):
                graph.add((property_shape, SH.maxCount, Literal(1)))
            datatype = _xsd_datatype(prop.get("type"))
            if datatype is not None:
                graph.add((property_shape, SH.datatype, datatype))
            if prop.get("enum_values"):
                graph.add((property_shape, SH["in"], _rdf_list(graph, [
                    Literal(value) for value in prop["enum_values"]
                ])))
        for relation_type in export["relation_types"]:
            if relation_type.get("source_class_id") != class_["id"]:
                continue
            relation_shape = BNode()
            graph.add((shape, SH.property, relation_shape))
            graph.add((relation_shape, SH.path, ns.resource("relation-type", relation_type["id"])))
            graph.add((relation_shape, SH["class"], ns.resource("class", relation_type["target_class_id"])))
            graph.add((relation_shape, op.scopePolicy, Literal(relation_type.get("scope_policy", "both"))))
    for class_id, properties in property_by_name.items():
        for name, prop in properties.items():
            graph.add((ns.resource("property", prop["id"]), op.sourceClassId, Literal(class_id)))
            graph.add((ns.resource("property", prop["id"]), op.propertyName, Literal(name)))
    return graph


def _add_schema_graph(graph: Graph, export: dict[str, Any], ns: SemanticNamespace) -> None:
    op = ns.vocab
    ontology = export["ontology"]
    ontology_iri = ns.resource("ontology", ontology["id"])
    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((ontology_iri, op.id, Literal(ontology["id"])))
    graph.add((ontology_iri, op.project, ns.resource("project", ontology["project_id"])))
    graph.add((ontology_iri, RDFS.label, Literal(ontology["name"])))
    _optional_literal(graph, ontology_iri, RDFS.comment, ontology.get("description"))
    _external_mappings(graph, ontology_iri, ontology.get("external_mappings") or {})

    for class_ in export["classes"]:
        class_iri = ns.resource("class", class_["id"])
        graph.add((class_iri, RDF.type, OWL.Class))
        graph.add((class_iri, op.id, Literal(class_["id"])))
        graph.add((class_iri, op.ontology, ontology_iri))
        graph.add((class_iri, RDFS.label, Literal(class_["name"])))
        _optional_literal(graph, class_iri, RDFS.comment, class_.get("description"))
        for alias in class_.get("aliases", []):
            graph.add((class_iri, SKOS.altLabel, Literal(alias)))
        for parent_id in class_.get("parent_class_ids", []):
            graph.add((class_iri, RDFS.subClassOf, ns.resource("class", parent_id)))
        _external_mappings(graph, class_iri, class_.get("external_mappings") or {})
        for prop in class_.get("properties", []):
            _add_property(graph, prop, class_iri, ns)

    for relation_type in export["relation_types"]:
        relation_iri = ns.resource("relation-type", relation_type["id"])
        graph.add((relation_iri, RDF.type, OWL.ObjectProperty))
        graph.add((relation_iri, op.id, Literal(relation_type["id"])))
        graph.add((relation_iri, op.ontology, ontology_iri))
        graph.add((relation_iri, RDFS.label, Literal(relation_type["name"])))
        _optional_literal(graph, relation_iri, RDFS.comment, relation_type.get("description"))
        for alias in relation_type.get("aliases", []):
            graph.add((relation_iri, SKOS.altLabel, Literal(alias)))
        parent_id = relation_type.get("parent_relation_type_id")
        if parent_id:
            graph.add((relation_iri, RDFS.subPropertyOf, ns.resource("relation-type", parent_id)))
        graph.add((relation_iri, RDFS.domain, ns.resource("class", relation_type["source_class_id"])))
        graph.add((relation_iri, RDFS.range, ns.resource("class", relation_type["target_class_id"])))
        graph.add((relation_iri, op.scopePolicy, Literal(relation_type.get("scope_policy", "both"))))
        graph.add((relation_iri, op.status, Literal(relation_type.get("status", "active"))))
        graph.add((relation_iri, op.sourceClassId, Literal(relation_type["source_class_id"])))
        graph.add((relation_iri, op.targetClassId, Literal(relation_type["target_class_id"])))
        if relation_type.get("symmetric"):
            graph.add((relation_iri, RDF.type, OWL.SymmetricProperty))
        if relation_type.get("transitive"):
            graph.add((relation_iri, RDF.type, OWL.TransitiveProperty))
        _external_mappings(graph, relation_iri, relation_type.get("external_mappings") or {})


def _add_property(graph: Graph, prop: dict[str, Any], class_iri: URIRef, ns: SemanticNamespace) -> None:
    op = ns.vocab
    property_iri = ns.resource("property", prop["id"])
    property_type = OWL.ObjectProperty if prop.get("type") == "reference" else OWL.DatatypeProperty
    graph.add((property_iri, RDF.type, property_type))
    graph.add((property_iri, op.id, Literal(prop["id"])))
    graph.add((property_iri, op.propertyName, Literal(prop["name"])))
    graph.add((property_iri, RDFS.label, Literal(prop["name"])))
    graph.add((property_iri, RDFS.domain, class_iri))
    datatype = _xsd_datatype(prop.get("type"))
    if datatype is not None:
        graph.add((property_iri, RDFS.range, datatype))
    graph.add((property_iri, op.required, Literal(bool(prop.get("required")))))
    graph.add((property_iri, op.multiValued, Literal(bool(prop.get("multi_valued")))))
    _optional_literal(graph, property_iri, RDFS.comment, prop.get("description"))
    for enum_value in prop.get("enum_values", []):
        enum_iri = ns.enum_value(prop["id"], enum_value)
        graph.add((enum_iri, RDF.type, SKOS.Concept))
        graph.add((enum_iri, SKOS.prefLabel, Literal(enum_value)))
        graph.add((property_iri, op.allowedValue, enum_iri))
    _external_mappings(graph, property_iri, prop.get("external_mappings") or {})


def _add_data_graph(graph: Graph, export: dict[str, Any], ns: SemanticNamespace) -> None:
    op = ns.vocab
    entity_by_id = {entity["id"]: entity for entity in export["entities"]}
    relation_type_by_id = {item["id"]: item for item in export["relation_types"]}
    properties_by_class = _properties_by_class_and_name(export)
    for entity in export["entities"]:
        entity_iri = ns.resource("entity", entity["id"])
        class_iri = ns.resource("class", entity["class_id"])
        graph.add((entity_iri, RDF.type, op.Entity))
        graph.add((entity_iri, RDF.type, class_iri))
        graph.add((entity_iri, op.id, Literal(entity["id"])))
        graph.add((entity_iri, op.project, ns.resource("project", entity["project_id"])))
        graph.add((entity_iri, op.ontology, ns.resource("ontology", entity["ontology_id"])))
        graph.add((entity_iri, op["class"], class_iri))
        graph.add((entity_iri, op.classId, Literal(entity["class_id"])))
        graph.add((entity_iri, RDFS.label, Literal(entity["name"])))
        for alias in entity.get("aliases", []):
            graph.add((entity_iri, SKOS.altLabel, Literal(alias)))
        for name, value in (entity.get("properties") or {}).items():
            prop = properties_by_class.get(entity["class_id"], {}).get(name)
            predicate = ns.resource("property", prop["id"]) if prop else ns.resource("property-name", name)
            for item in _as_values(value):
                graph.add((entity_iri, predicate, _literal_for_value(item)))
    for relation in export["relations"]:
        relation_iri = ns.resource("relation", relation["id"])
        relation_type = relation_type_by_id.get(relation["relation_type_id"], {})
        predicate = ns.resource("relation-type", relation["relation_type_id"])
        source = ns.resource("entity", relation["source_entity_id"])
        target = ns.resource("entity", relation["target_entity_id"])
        graph.add((source, predicate, target))
        graph.add((relation_iri, RDF.type, op.Relation))
        graph.add((relation_iri, op.id, Literal(relation["id"])))
        graph.add((relation_iri, op.source, source))
        graph.add((relation_iri, op.target, target))
        graph.add((relation_iri, op.relationType, predicate))
        graph.add((relation_iri, op.relationTypeId, Literal(relation["relation_type_id"])))
        graph.add((relation_iri, op.status, Literal(relation.get("status", "active"))))
        graph.add((relation_iri, RDFS.label, Literal(relation_type.get("name") or relation["relation_type"])))
        if relation["source_entity_id"] in entity_by_id and relation["target_entity_id"] in entity_by_id:
            graph.add((relation_iri, op.assertionKind, Literal("entity_relation")))


def _add_fact_claims(graph: Graph, claims: list[FactClaimModel], ns: SemanticNamespace) -> None:
    op = ns.vocab
    for claim in claims:
        claim_iri = ns.resource("fact-claim", claim.id)
        graph.add((claim_iri, RDF.type, op.FactClaim))
        graph.add((claim_iri, op.id, Literal(claim.id)))
        graph.add((claim_iri, op.claimKey, Literal(claim.claim_key)))
        graph.add((claim_iri, op.claimType, Literal(claim.claim_type)))
        graph.add((claim_iri, op.layer, Literal(claim.layer)))
        graph.add((claim_iri, op.predicate, Literal(claim.predicate)))
        graph.add((claim_iri, op.value, Literal(json.dumps(claim.value, ensure_ascii=False, sort_keys=True, default=str))))
        graph.add((claim_iri, op.auditStatus, Literal(claim.audit_status)))
        graph.add((claim_iri, op.confidence, Literal(claim.confidence)))
        graph.add((claim_iri, op.generationReason, Literal(claim.generation_reason)))
        graph.add((claim_iri, op.evidenceStatus, Literal("evidence_bound" if claim.evidence_ids else "missing_evidence")))
        graph.add((claim_iri, op.missingEvidence, Literal(not bool(claim.evidence_ids))))
        graph.add((claim_iri, op.stale, Literal(bool(claim.stale))))
        if claim.subject.get("entity_id"):
            graph.add((claim_iri, op.subject, ns.resource("entity", claim.subject["entity_id"])))
        elif claim.subject.get("class_id"):
            graph.add((claim_iri, op.subject, ns.resource("class", claim.subject["class_id"])))
        for evidence_id in claim.evidence_ids:
            graph.add((claim_iri, op.evidence, ns.resource("evidence", evidence_id)))


def _add_evidence(graph: Graph, evidence_rows: list[EvidenceModel], ns: SemanticNamespace) -> None:
    op = ns.vocab
    for evidence in evidence_rows:
        evidence_iri = ns.resource("evidence", evidence.id)
        graph.add((evidence_iri, RDF.type, PROV.Entity))
        graph.add((evidence_iri, RDF.type, op.Evidence))
        graph.add((evidence_iri, op.id, Literal(evidence.id)))
        graph.add((evidence_iri, op.sourceType, Literal(evidence.source_type)))
        graph.add((evidence_iri, op.proposalId, Literal(evidence.proposal_id)))
        graph.add((evidence_iri, op.quote, Literal(evidence.quote)))
        graph.add((evidence_iri, op.contentHash, Literal(evidence.content_hash)))
        if evidence.document_id:
            graph.add((evidence_iri, op.documentId, Literal(evidence.document_id)))


def _fact_claims(session: Session, ontology_id: str) -> list[FactClaimModel]:
    return list(
        session.scalars(
            select(FactClaimModel).where(FactClaimModel.ontology_id == ontology_id).order_by(FactClaimModel.id)
        )
    )


def _evidence(session: Session, ontology_id: str) -> list[EvidenceModel]:
    proposal_ids = set(
        session.scalars(
            select(FactClaimModel.linked_fix_proposal_id)
            .where(FactClaimModel.ontology_id == ontology_id)
            .where(FactClaimModel.linked_fix_proposal_id.is_not(None))
        )
    )
    claim_evidence_ids = {
        evidence_id
        for ids in session.scalars(
            select(FactClaimModel.evidence_ids).where(FactClaimModel.ontology_id == ontology_id)
        )
        for evidence_id in (ids or [])
    }
    if not proposal_ids and not claim_evidence_ids:
        return []
    statement = select(EvidenceModel)
    if claim_evidence_ids:
        statement = statement.where(EvidenceModel.id.in_(claim_evidence_ids))
    elif proposal_ids:
        statement = statement.where(EvidenceModel.proposal_id.in_(proposal_ids))
    return list(session.scalars(statement.order_by(EvidenceModel.id)))


def _project_classes(graph: Graph, op: Namespace) -> list[dict[str, Any]]:
    classes = []
    for subject in sorted(graph.subjects(RDF.type, OWL.Class), key=str):
        if str(subject).endswith("/vocab/Entity"):
            continue
        classes.append(
            {
                "id": _first_str(graph, subject, op.id),
                "name": _first_str(graph, subject, RDFS.label),
                "aliases": _all_str(graph, subject, SKOS.altLabel),
                "parent_class_ids": [
                    _first_str(graph, parent, op.id) or _tail(parent)
                    for parent in graph.objects(subject, RDFS.subClassOf)
                ],
            }
        )
    return [item for item in classes if item["id"]]


def _project_relation_types(graph: Graph, op: Namespace) -> list[dict[str, Any]]:
    items = []
    for subject in sorted(graph.subjects(RDF.type, OWL.ObjectProperty), key=str):
        relation_type_id = _first_str(graph, subject, op.id)
        if not relation_type_id:
            continue
        items.append(
            {
                "id": relation_type_id,
                "name": _first_str(graph, subject, RDFS.label),
                "source_class_id": _first_str(graph, subject, op.sourceClassId),
                "target_class_id": _first_str(graph, subject, op.targetClassId),
                "scope_policy": _first_str(graph, subject, op.scopePolicy),
            }
        )
    return items


def _project_entities(graph: Graph, op: Namespace) -> list[dict[str, Any]]:
    items = []
    for subject in sorted(graph.subjects(RDF.type, op.Entity), key=str):
        entity_id = _first_str(graph, subject, op.id)
        if not entity_id:
            continue
        items.append(
            {
                "id": entity_id,
                "name": _first_str(graph, subject, RDFS.label),
                "class_id": _first_str(graph, subject, op.classId),
                "aliases": _all_str(graph, subject, SKOS.altLabel),
            }
        )
    return items


def _project_relations(graph: Graph, op: Namespace) -> list[dict[str, Any]]:
    items = []
    for subject in sorted(graph.subjects(RDF.type, op.Relation), key=str):
        relation_id = _first_str(graph, subject, op.id)
        if not relation_id:
            continue
        items.append(
            {
                "id": relation_id,
                "relation_type_id": _first_str(graph, subject, op.relationTypeId),
                "source_entity_id": _tail(_first_uri(graph, subject, op.source)),
                "target_entity_id": _tail(_first_uri(graph, subject, op.target)),
                "status": _first_str(graph, subject, op.status),
            }
        )
    return items


def _project_fact_claims(graph: Graph, op: Namespace) -> list[dict[str, Any]]:
    items = []
    for subject in sorted(graph.subjects(RDF.type, op.FactClaim), key=str):
        claim_id = _first_str(graph, subject, op.id)
        if not claim_id:
            continue
        items.append(
            {
                "id": claim_id,
                "claim_key": _first_str(graph, subject, op.claimKey),
                "predicate": _first_str(graph, subject, op.predicate),
                "evidence_status": _first_str(graph, subject, op.evidenceStatus),
                "audit_status": _first_str(graph, subject, op.auditStatus),
            }
        )
    return items


def _serialize_dataset(dataset: Dataset, format: str, context: dict[str, Any]) -> str:
    if format == "trig":
        return dataset.serialize(format="trig")
    graph = Graph()
    _copy_dataset(dataset, graph)
    return _serialize_graph(graph, format, context)


def _serialize_graph(graph: Graph, format: str, context: dict[str, Any]) -> str:
    if format == "turtle":
        return graph.serialize(format="turtle")
    if format == "json-ld":
        return graph.serialize(format="json-ld", context=context, indent=2)
    if format == "trig":
        dataset = Dataset()
        _copy_graph(graph, dataset.graph(graph.identifier if isinstance(graph.identifier, URIRef) else None))
        return dataset.serialize(format="trig")
    raise ValueError(f"Unsupported semantic export format: {format}")


def _rdflib_format(format: str) -> str:
    return {"json-ld": "json-ld", "turtle": "turtle", "trig": "trig"}[format]


def _bind(graph: Graph | Dataset, ns: SemanticNamespace) -> None:
    graph.bind("op", ns.vocab)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("skos", SKOS)
    graph.bind("sh", SH)
    graph.bind("prov", PROV)
    graph.bind("xsd", XSD)


def _copy_dataset(dataset: Dataset, graph: Graph) -> None:
    for subject, predicate, object_, _ in dataset.quads((None, None, None, None)):
        graph.add((subject, predicate, object_))


def _copy_graph(source: Graph, target: Graph) -> None:
    for triple in source:
        target.add(triple)


def _optional_literal(graph: Graph, subject: URIRef, predicate: URIRef, value: Any) -> None:
    if value not in (None, ""):
        graph.add((subject, predicate, Literal(value)))


def _external_mappings(graph: Graph, subject: URIRef, mappings: dict[str, Any]) -> None:
    for value in mappings.values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and item.startswith(("http://", "https://", "urn:")):
                graph.add((subject, OWL.sameAs, URIRef(item)))


def _xsd_datatype(property_type: str | None) -> URIRef | None:
    return {
        "string": XSD.string,
        "number": XSD.decimal,
        "boolean": XSD.boolean,
        "date": XSD.date,
        "enum": XSD.string,
    }.get(str(property_type))


def _literal_for_value(value: Any) -> Literal:
    if isinstance(value, bool):
        return Literal(value)
    if isinstance(value, int | float):
        return Literal(value)
    if isinstance(value, dict | list):
        return Literal(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    return Literal(value)


def _as_values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _properties_by_class_and_name(export: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        class_["id"]: {prop["name"]: prop for prop in class_.get("properties", [])}
        for class_ in export["classes"]
    }


def _rdf_list(graph: Graph, values: list[Literal]) -> URIRef | BNode:
    if not values:
        return RDF.nil
    head = BNode()
    current = head
    for index, value in enumerate(values):
        graph.add((current, RDF.first, value))
        if index == len(values) - 1:
            graph.add((current, RDF.rest, RDF.nil))
        else:
            next_node = BNode()
            graph.add((current, RDF.rest, next_node))
            current = next_node
    return head


def _op_from_graph(graph: Graph) -> Namespace:
    for prefix, namespace in graph.namespaces():
        if prefix == "op":
            return Namespace(str(namespace))
    for subject in graph.subjects(RDF.type, OWL.Ontology):
        value = str(subject).split("/ontology/", 1)[0]
        if value:
            return Namespace(f"{value}/vocab/")
    return Namespace("http://ontology-platform.local/semantic/vocab/")


def _first_str(graph: Graph, subject: URIRef, predicate: URIRef) -> str | None:
    value = next(graph.objects(subject, predicate), None)
    return str(value) if value is not None else None


def _all_str(graph: Graph, subject: URIRef, predicate: URIRef) -> list[str]:
    return [str(value) for value in graph.objects(subject, predicate)]


def _first_uri(graph: Graph, subject: URIRef, predicate: URIRef) -> URIRef | None:
    value = next(graph.objects(subject, predicate), None)
    return value if isinstance(value, URIRef) else None


def _tail(value: URIRef | None) -> str | None:
    if value is None:
        return None
    return str(value).rstrip("/").rsplit("/", 1)[-1]
