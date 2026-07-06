"""Versioned SPARQL templates for graph-derived read models.

Each template declares required graph roles, whether derived-result graphs
are needed, default limit, and the projection version. Read models are owned
by the backend; caller-provided SPARQL remains available through the direct
semantic query endpoint from earlier phases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadModelTemplate:
    name: str
    projection_version: str
    required_roles: tuple[str, ...]
    needs_reasoning: bool
    needs_rules: bool
    default_limit: int
    assertion_kind: str
    evidence_status: str
    body: str


_TEMPLATES: dict[str, ReadModelTemplate] = {
    "ontology-schema-summary": ReadModelTemplate(
        name="ontology-schema-summary",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: schema-summary
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          GRAPH ?graph { ?class a rdfs:Class . OPTIONAL { ?class rdfs:label ?label . } }
        }
        ORDER BY ?label
        LIMIT {limit}
        """,
    ),
    "class-detail": ReadModelTemplate(
        name="class-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: class-detail
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          GRAPH ?graph { ?class a rdfs:Class . ?class rdfs:label ?label . }
        }
        LIMIT {limit}
        """,
    ),
    "entity-detail": ReadModelTemplate(
        name="entity-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="unknown",
        body="""# template: entity-detail
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?entity ?label ?graph WHERE {
          GRAPH ?graph { ?entity rdfs:label ?label . }
        }
        LIMIT {limit}
        """,
    ),
    "statement-list": ReadModelTemplate(
        name="statement-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1000,
        assertion_kind="asserted",
        evidence_status="unknown",
        body="""# template: statement-list
        SELECT DISTINCT ?subject ?predicate ?object ?graph WHERE {
          GRAPH ?graph { ?subject ?predicate ?object . }
        }
        LIMIT {limit}
        """,
    ),
    "graph-set-staleness": ReadModelTemplate(
        name="graph-set-staleness",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=1,
        assertion_kind="asserted",
        evidence_status="mixed",
        body="""# template: graph-set-staleness
        # Composer-driven. The SemanticReadModelService branch assembles
        # member/editable/staleness from Postgres; this SPARQL only fetches
        # the missing-evidence count across the active graph-set members.
        PREFIX op: <http://ontology-platform.local/semantic/op/>
        SELECT (COUNT(*) AS ?count) WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g { ?s op:evidenceStatus "missing_evidence" . }
        }
        """,
    ),
    "class-topology": ReadModelTemplate(
        name="class-topology",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: class-topology
        # Returns one row per class with its label and parent IRI(s).
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?class ?label ?parent ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?class a owl:Class .
            OPTIONAL { ?class rdfs:label ?label . }
            OPTIONAL { ?class rdfs:subClassOf ?parent . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label
        LIMIT {limit}
        """,
    ),
    "property-list": ReadModelTemplate(
        name="property-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: property-list
        # Returns one row per property whose rdfs:domain is the given class.
        # Caller post-filters by class IRI; the SPARQL stays generic so the
        # template remains graph-set portable.
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?property ?label ?range ?type ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?property rdfs:domain ?class .
            OPTIONAL { ?property rdfs:label ?label . }
            OPTIONAL { ?property rdfs:range ?range . }
            OPTIONAL { ?property a ?type . FILTER(?type IN (owl:DatatypeProperty, owl:ObjectProperty)) }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "relation-type-list": ReadModelTemplate(
        name="relation-type-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: relation-type-list
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?relation ?label ?source ?target ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?relation a owl:ObjectProperty .
            OPTIONAL { ?relation rdfs:label ?label . }
            OPTIONAL { ?relation rdfs:domain ?source . }
            OPTIONAL { ?relation rdfs:range ?target . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label
        LIMIT {limit}
        """,
    ),
    "class-shape-generated": ReadModelTemplate(
        name="class-shape-generated",
        projection_version="semantic-read-v1",
        required_roles=("shape_graph_generated",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: class-shape-generated
        # Reads SHACL NodeShapes from the derived generated sub-graph. Each
        # row is one (shape, targetClass) pair; PropertyShape rows are
        # joined separately by the read-model service.
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?shape ?target_class ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?shape a sh:NodeShape ;
                   sh:targetClass ?target_class .
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "class-shape-custom": ReadModelTemplate(
        name="class-shape-custom",
        projection_version="semantic-read-v1",
        required_roles=("shape_graph_custom",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: class-shape-custom
        # Reads SHACL NodeShapes from the editable custom sub-graph.
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?shape ?target_class ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?shape a sh:NodeShape ;
                   sh:targetClass ?target_class .
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "entity-list": ReadModelTemplate(
        name="entity-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="mixed",
        body="""# template: entity-list
        # Returns one row per NamedIndividual in the asserted data graph.
        # Projects id, label, class_iri, and the op:evidenceStatus marker if
        # present. class_label is joined optionally from the asserted ontology
        # graph when the read-model service hands both graph IRIs in.
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX op: <http://ontology-platform.local/semantic/op/>
        SELECT ?entity ?label ?class ?class_label ?evidence_status ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?entity a owl:NamedIndividual .
            ?entity a ?class .
            FILTER(!STRSTARTS(STR(?class), STR(owl:)))
            FILTER(?class != owl:NamedIndividual)
            OPTIONAL { ?entity rdfs:label ?label . }
            OPTIONAL { ?entity op:evidenceStatus ?evidence_status . }
          }
          OPTIONAL {
            VALUES ?og { {graph_iris} }
            GRAPH ?og { ?class rdfs:label ?class_label . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label
        LIMIT {limit}
        """,
    ),
    "entity-relations": ReadModelTemplate(
        name="entity-relations",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=1000,
        assertion_kind="asserted",
        evidence_status="mixed",
        body="""# template: entity-relations
        # Lists triples whose subject and object are both NamedIndividuals
        # and whose predicate is not rdf:type / rdfs:label / skos:altLabel.
        # The read-model service decorates each row's provenance from the
        # source graph (asserted vs reasoning-result vs rule-result).
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT ?source ?relation ?target ?label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?source ?relation ?target .
            ?source a owl:NamedIndividual .
            ?target a owl:NamedIndividual .
            FILTER(?relation != rdf:type)
            FILTER(?relation != rdfs:label)
            FILTER(?relation != skos:altLabel)
            OPTIONAL { ?relation rdfs:label ?label . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "entity-shape": ReadModelTemplate(
        name="entity-shape",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology", "shape_graph_generated", "shape_graph_custom"),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: entity-shape
        # COMPOSER. The SemanticReadModelService recognizes this template name
        # and delegates to SemanticShapeEndpointService.read_merged_guidance
        # with the entity's class IRI (resolved by the caller via the entity
        # param). The body is not executed directly.
        """,
    ),
    "mapping-list": ReadModelTemplate(
        name="mapping-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: mapping-list
        # Returns op:SemanticMapping instances asserted in the ontology graph.
        PREFIX op: <http://ontology-platform.local/semantic/op/>
        SELECT ?mapping ?external_field ?target ?join_key ?confidence ?owner ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?mapping a op:SemanticMapping .
            OPTIONAL { ?mapping op:externalField ?external_field . }
            OPTIONAL { ?mapping op:targetClass ?target . }
            OPTIONAL { ?mapping op:joinKey ?join_key . }
            OPTIONAL { ?mapping op:confidence ?confidence . }
            OPTIONAL { ?mapping op:owner ?owner . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "import-graph-mappings": ReadModelTemplate(
        name="import-graph-mappings",
        projection_version="semantic-read-v1",
        required_roles=("import_graph",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: import-graph-mappings
        # Returns op:SemanticMapping instances written into a specific import
        # run sub-graph (graph/import/{source_id}/{run_id}).
        PREFIX op: <http://ontology-platform.local/semantic/op/>
        SELECT ?mapping ?external_field ?target ?join_key ?confidence ?owner ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?mapping a op:SemanticMapping .
            OPTIONAL { ?mapping op:externalField ?external_field . }
            OPTIONAL { ?mapping op:targetClass ?target . }
            OPTIONAL { ?mapping op:joinKey ?join_key . }
            OPTIONAL { ?mapping op:confidence ?confidence . }
            OPTIONAL { ?mapping op:owner ?owner . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
}


def get_template(name: str) -> ReadModelTemplate:
    if name not in _TEMPLATES:
        raise KeyError(name)
    return _TEMPLATES[name]


def list_templates() -> list[ReadModelTemplate]:
    return list(_TEMPLATES.values())
