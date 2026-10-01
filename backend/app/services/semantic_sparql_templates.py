"""Versioned SPARQL templates for graph-derived read models.

Each template declares required graph roles, whether derived-result graphs
are needed, default limit, and the projection version. Read models are owned
by the backend; caller-provided SPARQL remains available through the direct
semantic query endpoint from earlier phases.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from rdflib import Literal, URIRef

from app.core.config import DEFAULT_SEMANTIC_BASE_IRI

# ``op:`` vocabulary namespace shared with ``SemanticNamespace.vocab``
# (app/services/semantic_export.py), which appends "/vocab/" to the same
# configured base IRI. Derived once at import from the single default
# constant — never spelled out again — so compiler writes and template
# reads stay in one namespace. Template bodies are static strings and
# cannot read Settings per request; they carry the ``{op_prefix}`` token
# resolved here at definition time.
OP_VOCAB_PREFIX = f"{DEFAULT_SEMANTIC_BASE_IRI.rstrip('/')}/vocab/"


def _op_body(body: str) -> str:
    return body.replace("{op_prefix}", OP_VOCAB_PREFIX)


@dataclass(frozen=True)
class ReadModelTemplate:
    name: str
    projection_version: str
    required_roles: tuple[str, ...]
    needs_reasoning: bool
    needs_rules: bool
    default_limit: int
    assertion_kind: str
    body: str
    # Name of the SELECT variable that holds the primary IRI for each row.
    # ``SemanticReadModelService._decorate_row`` reads this column first when
    # populating the item's ``iri`` / ``id`` fields. Composer templates
    # (graph-set-staleness, entity-shape, fact-audit-queue) leave this empty
    # because their items are assembled by dedicated composers, not by the
    # generic decorator.
    primary_iri_variable: str = ""
    # Non-whitelist SELECT variables that the row decorator passes through
    # into the response item's ``detail_fields`` subobject (keys omitted when
    # unbound). The default keeps every existing template byte-identical.
    detail_variables: tuple[str, ...] = ()


_TEMPLATES: dict[str, ReadModelTemplate] = {
    "ontology-schema-summary": ReadModelTemplate(
        name="ontology-schema-summary",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        primary_iri_variable="class",
        body="""# template: schema-summary
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            VALUES ?class_type { owl:Class rdfs:Class }
            ?class a ?class_type .
            OPTIONAL { ?class rdfs:label ?label . }
          }
          BIND(?g AS ?graph)
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
        primary_iri_variable="class",
        body="""# template: class-detail
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            VALUES ?class_type { owl:Class rdfs:Class }
            ?class a ?class_type ;
                   rdfs:label ?label .
          }
          BIND(?g AS ?graph)
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
        primary_iri_variable="entity",
        body="""# template: entity-detail
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?entity ?label ?graph WHERE {
          VALUES ?graph { {graph_iris} }
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
        primary_iri_variable="subject",
        body="""# template: statement-list
        SELECT DISTINCT ?subject ?predicate ?object ?graph WHERE {
          VALUES ?graph { {graph_iris} }
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
        body="""# template: graph-set-staleness
        # COMPOSER. The SemanticReadModelService delegates to
        # ``_compose_graph_set_staleness``. The body is intentionally empty.
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
        primary_iri_variable="class",
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
        primary_iri_variable="property",
        # R3.0-009: the declared domain is projected so the caller can apply an
        # explicit class filter without treating "no domain" as "all classes".
        detail_variables=("domain",),
        body="""# template: property-list
        # R3.0-009: anchored on explicitly declared property types
        # (owl:DatatypeProperty / owl:ObjectProperty) instead of a mandatory
        # rdfs:domain join, so domain-less properties stay listable. One row
        # per (property, declared domain) pair; domain-less properties project
        # no domain. Callers post-filter by class IRI against the declared
        # domain only.
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?property ?label ?range ?type ?domain ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?property a ?type .
            FILTER(?type IN (owl:DatatypeProperty, owl:ObjectProperty))
            OPTIONAL { ?property rdfs:label ?label . }
            OPTIONAL { ?property rdfs:range ?range . }
            OPTIONAL { ?property rdfs:domain ?domain . }
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
        primary_iri_variable="relation",
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
        primary_iri_variable="shape",
        # R3.0-009 §6.1: rows are one per (shape, target) pair across all three
        # supported targets; target_kind/target_value are projected through
        # detail_fields so a node/subjects-of target is never mislabelled as a
        # class target.
        detail_variables=("target_kind", "target_value"),
        body="""# template: class-shape-generated
        # Reads SHACL NodeShapes from the derived generated sub-graph. Each
        # row is one (shape, target) pair; PropertyShape rows are
        # joined separately by the read-model service.
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?shape ?target_class ?target_kind ?target_value ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?shape a sh:NodeShape .
            {
              ?shape sh:targetClass ?target_class .
              BIND("class" AS ?target_kind)
              BIND(?target_class AS ?target_value)
            } UNION {
              ?shape sh:targetNode ?target_node .
              BIND("node" AS ?target_kind)
              BIND(?target_node AS ?target_value)
            } UNION {
              ?shape sh:targetSubjectsOf ?target_predicate .
              BIND("subjects_of" AS ?target_kind)
              BIND(?target_predicate AS ?target_value)
            }
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
        primary_iri_variable="shape",
        detail_variables=("target_kind", "target_value"),
        body="""# template: class-shape-custom
        # Reads SHACL NodeShapes from the editable custom sub-graph, one row
        # per (shape, target) pair across the three supported targets.
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?shape ?target_class ?target_kind ?target_value ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?shape a sh:NodeShape .
            {
              ?shape sh:targetClass ?target_class .
              BIND("class" AS ?target_kind)
              BIND(?target_class AS ?target_value)
            } UNION {
              ?shape sh:targetNode ?target_node .
              BIND("node" AS ?target_kind)
              BIND(?target_node AS ?target_value)
            } UNION {
              ?shape sh:targetSubjectsOf ?target_predicate .
              BIND("subjects_of" AS ?target_kind)
              BIND(?target_predicate AS ?target_value)
            }
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
        needs_reasoning=True,
        needs_rules=True,
        default_limit=500,
        assertion_kind="asserted",
        primary_iri_variable="entity",
        body="""# template: entity-list
        # R3.0-009 §9.3: the identity anchor is the asserted NamedIndividual
        # marker plus the entity's own stable /vocab/id; a business Class is no
        # longer an existence condition, so zero-class entities stay readable.
        # Type edges and class identity metadata are independently optional and
        # may come from a different authorized graph than the entity identity.
        # Rows are one per (entity, visible formal class) pair; the read-model
        # service aggregates them per entity IRI before pagination. Visible
        # classes without their own /vocab/id keep the known type IRI and are
        # reported as incomplete identity instead of dropping the node.
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?entity ?semantic_id ?label ?class ?class_semantic_id ?class_label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?ig { {graph_iris} }
          GRAPH ?ig { ?entity a owl:NamedIndividual . }
          GRAPH ?g {
            ?entity ?entity_id_pred ?semantic_id .
            FILTER(STRENDS(STR(?entity_id_pred), "/vocab/id"))
          }
          OPTIONAL {
            VALUES ?cg { {graph_iris} }
            GRAPH ?cg {
              ?entity a ?class .
              FILTER(!STRSTARTS(STR(?class), STR(owl:)))
              FILTER(?class != owl:NamedIndividual)
            }
            # Class identity metadata stays inside this OPTIONAL so an
            # unbound ?class can never be filled by an unrelated /vocab/id
            # subject (a malformed OPTIONAL would fabricate memberships).
            OPTIONAL {
              VALUES ?class_graph { {graph_iris} }
              GRAPH ?class_graph {
                ?class ?class_id_pred ?class_semantic_id .
                FILTER(STRENDS(STR(?class_id_pred), "/vocab/id"))
              }
            }
            OPTIONAL {
              VALUES ?og { {graph_iris} }
              GRAPH ?og { ?class rdfs:label ?class_label . }
            }
          }
          OPTIONAL {
            VALUES ?lg { {graph_iris} }
            GRAPH ?lg { ?entity rdfs:label ?label . }
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
        primary_iri_variable="source",
        body="""# template: entity-relations
        # Lists triples whose subject and object are both known
        # NamedIndividuals, with the identity check anchored in any graph in
        # scope so derived graphs only need to carry the relation triple.
        # The read-model service decorates each row's provenance from the
        # source graph (asserted vs reasoning-result vs rule-result).
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?source ?relation ?target ?label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?source ?relation ?target .
            FILTER(isIRI(?target))
            FILTER(?relation != rdf:type)
            FILTER(?relation != rdfs:label)
            FILTER(?relation != skos:altLabel)
          }
          VALUES ?sg { {graph_iris} }
          VALUES ?tg { {graph_iris} }
          GRAPH ?sg { ?source a owl:NamedIndividual . }
          GRAPH ?tg { ?target a owl:NamedIndividual . }
          OPTIONAL {
            VALUES ?lg { {graph_iris} }
            GRAPH ?lg { ?relation rdfs:label ?label . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "entity-literal-facts": ReadModelTemplate(
        name="entity-literal-facts",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=200,
        assertion_kind="any",
        primary_iri_variable="subject",
        body="""# template: entity-literal-facts
        # Lists literal-valued facts for one entity. The entity IRI is bound
        # by the read-model service via {entity_iri}; include controls whether
        # asserted, reasoning-result, rule-result, or full working graphs are
        # in scope.
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?subject ?subject_label ?predicate ?predicate_label
                        ?object ?object_label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?subject { <{entity_iri}> }
          GRAPH ?g {
            ?subject ?predicate ?object .
            FILTER(isLiteral(?object))
            FILTER(?predicate != rdf:type)
            FILTER(?predicate != rdfs:label)
            FILTER(?predicate != skos:altLabel)
            FILTER(?predicate != owl:sameAs)
            OPTIONAL { ?subject rdfs:label ?subject_label . }
          }
          OPTIONAL {
            VALUES ?pg { {graph_iris} }
            GRAPH ?pg { ?predicate rdfs:label ?predicate_label . }
          }
          BIND(?object AS ?object_label)
          BIND(?g AS ?graph)
        }
        ORDER BY ?predicate_label ?predicate ?object
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
        primary_iri_variable="mapping",
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
        primary_iri_variable="mapping",
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
    "fact-audit-queue": ReadModelTemplate(
        name="fact-audit-queue",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=500,
        assertion_kind="asserted",
        body="""# template: fact-audit-queue
        # COMPOSER. The SemanticReadModelService detects this template name
        # and delegates to ``_compose_fact_audit_queue``. The composer uses
        # the ``?kind=`` query parameter (asserted / inferred / rule_derived)
        # to select source graphs and decorates each row into the unified
        # FactRow shape.
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?subject ?subject_label ?predicate ?predicate_label
                        ?object ?object_label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?subject ?predicate ?object .
            FILTER(?predicate != rdf:type)
            FILTER(?predicate != rdfs:label)
            OPTIONAL { ?subject rdfs:label ?subject_label . }
            OPTIONAL { ?predicate rdfs:label ?predicate_label . }
            OPTIONAL { ?object rdfs:label ?object_label . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "fact-audit-queue-with-types": ReadModelTemplate(
        name="fact-audit-queue-with-types",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=500,
        assertion_kind="rule_derived",
        body="""# template: fact-audit-queue-with-types
        # Rule results may classify existing entities exclusively through
        # rdf:type. Keep those classifications visible in the rule-derived
        # fact view while the asserted/inferred queue retains its historical
        # filtering contract.
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?subject ?subject_label ?predicate ?predicate_label
                        ?object ?object_label ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?subject ?predicate ?object .
            FILTER(?predicate != rdfs:label)
            OPTIONAL { ?subject rdfs:label ?subject_label . }
            OPTIONAL { ?predicate rdfs:label ?predicate_label . }
            OPTIONAL { ?object rdfs:label ?object_label . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """,
    ),
    "publication-readiness": ReadModelTemplate(
        name="publication-readiness",
        projection_version="1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=1,
        assertion_kind="asserted",
        body="""# template: publication-readiness
        # Single-row composer. Body is intentionally empty; the service
        # delegates to ``_compose_publication_readiness`` which reuses the
        # graph-set-staleness aggregator.
        """,
    ),
    "graph-set-history-list": ReadModelTemplate(
        name="graph-set-history-list",
        projection_version="1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=50,
        assertion_kind="asserted",
        body="""# template: graph-set-history-list
        # Single-row composer that returns the list of graph sets in scope.
        # Reads from SemanticGraphSetModel joined with members and derived
        # pointers; see spec §4.2.
        """,
    ),
    "graph-set-delta": ReadModelTemplate(
        name="graph-set-delta",
        projection_version="1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        body="""# template: graph-set-delta
        # Composer-driven. Reads the ``target`` query param to identify the
        # second graph set, then for each role present in both sets computes
        # the CONSTRUCT diff. See spec §4.3.
        """,
    ),
    "entity-search": ReadModelTemplate(
        name="entity-search",
        projection_version="1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=50,
        assertion_kind="any",
        primary_iri_variable="entity",
        body="""# template: entity-search
        # Stage 4 §4.1, R3.0-009 §9.3. The composer binds ?q (search substring)
        # and ?class_iri (optional class equality filter) into the FILTER
        # before handing the query to the store. The lexical anchor is the same
        # legal entity anchor as entity-list (asserted NamedIndividual marker),
        # so zero-class entities are searchable; the class membership edges are
        # optional. An explicit class filter keeps only entities that are
        # formal members of that class (the {class_guard} token becomes
        # BOUND(?class)), never zero-class entities.
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX owl:  <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?entity ?label ?comment ?class ?class_label WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?ig { {graph_iris} }
          GRAPH ?ig { ?entity a owl:NamedIndividual . }
          OPTIONAL {
            VALUES ?cg { {graph_iris} }
            GRAPH ?cg {
              ?entity a ?class .
              FILTER(!STRSTARTS(STR(?class), STR(owl:)))
              FILTER(?class != owl:NamedIndividual)
              FILTER(!BOUND(?class_iri) || ?class = ?class_iri)
            }
            # Nested so an unbound ?class can never be filled by an unrelated
            # labelled resource.
            OPTIONAL {
              VALUES ?og { {graph_iris} }
              GRAPH ?og { ?class rdfs:label ?class_label . }
            }
          }
          OPTIONAL { VALUES ?lg { {graph_iris} } GRAPH ?lg { ?entity rdfs:label ?label . } }
          OPTIONAL { VALUES ?mg { {graph_iris} } GRAPH ?mg { ?entity rdfs:comment ?comment . } }
          FILTER({class_guard})
          FILTER(
            CONTAINS(LCASE(COALESCE(STR(?label), "")), LCASE(?q)) ||
            CONTAINS(LCASE(COALESCE(STR(?comment), "")), LCASE(?q)) ||
            CONTAINS(LCASE(STR(?entity)), LCASE(?q))
          )
          BIND(?g AS ?graph)
        }
        ORDER BY LCASE(?label)
        LIMIT {limit}
        """,
    ),
    "owl-consistency-summary": ReadModelTemplate(
        name="owl-consistency-summary",
        projection_version="1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=True,
        needs_rules=False,
        default_limit=1,
        assertion_kind="owl_inferred",
        primary_iri_variable="run",
        body="""# template: owl-consistency-summary
        # Composer-driven. The SemanticReadModelService reads the latest
        # SemanticReasoningRunModel row whose run_metadata.tasks contains
        # ``consistency`` and projects spec §4.3 fields. The body is a
        # placeholder; the composer never executes it directly.
        """,
    ),
    # ------------------------------------------------------------------
    # R3.0-003 relational schema mapping read models (list + exact detail
    # pairs). All eight carry VALUES ?g { {graph_iris} } (R3.0-007 frozen
    # lesson), read the ontology graph, and declare detail_variables for
    # the row decorator's detail_fields passthrough.
    # ------------------------------------------------------------------
    "table-mapping-list": ReadModelTemplate(
        name="table-mapping-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        primary_iri_variable="table_mapping",
        detail_variables=(
            "table_name",
            "mapped_class",
            "column_mappings",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: table-mapping-list
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?table_mapping ?label ?table_name ?mapped_class ?column_mappings
                        ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?table_mapping a op:TableMapping .
            OPTIONAL { ?table_mapping rdfs:label ?label . }
            OPTIONAL { ?table_mapping op:tableName ?table_name . }
            OPTIONAL { ?table_mapping op:mappedClass ?mapped_class . }
            OPTIONAL { ?table_mapping op:columnMappings ?column_mappings . }
            OPTIONAL { ?table_mapping op:schemaSource ?schema_source . }
            OPTIONAL { ?table_mapping op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label ?table_mapping
        LIMIT {limit}
        """),
    ),
    "table-mapping-detail": ReadModelTemplate(
        name="table-mapping-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1,
        assertion_kind="asserted",
        primary_iri_variable="table_mapping",
        detail_variables=(
            "table_name",
            "mapped_class",
            "column_mappings",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: table-mapping-detail
        # Exact single-resource lookup driven by the entity IRI parameter
        # ({entity_iri} placeholder mechanism, entity-literal-facts precedent).
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?table_mapping ?label ?table_name ?mapped_class ?column_mappings
                        ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?table_mapping { <{entity_iri}> }
          GRAPH ?g {
            ?table_mapping a op:TableMapping .
            OPTIONAL { ?table_mapping rdfs:label ?label . }
            OPTIONAL { ?table_mapping op:tableName ?table_name . }
            OPTIONAL { ?table_mapping op:mappedClass ?mapped_class . }
            OPTIONAL { ?table_mapping op:columnMappings ?column_mappings . }
            OPTIONAL { ?table_mapping op:schemaSource ?schema_source . }
            OPTIONAL { ?table_mapping op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """),
    ),
    "join-mapping-list": ReadModelTemplate(
        name="join-mapping-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        primary_iri_variable="join_mapping",
        detail_variables=(
            "mapped_relation",
            "join_direction",
            "join_path",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: join-mapping-list
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?join_mapping ?label ?mapped_relation ?join_direction ?join_path
                        ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?join_mapping a op:JoinMapping .
            OPTIONAL { ?join_mapping rdfs:label ?label . }
            OPTIONAL { ?join_mapping op:mappedRelationType ?mapped_relation . }
            OPTIONAL { ?join_mapping op:joinDirection ?join_direction . }
            OPTIONAL { ?join_mapping op:joinPath ?join_path . }
            OPTIONAL { ?join_mapping op:schemaSource ?schema_source . }
            OPTIONAL { ?join_mapping op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label ?join_mapping
        LIMIT {limit}
        """),
    ),
    "join-mapping-detail": ReadModelTemplate(
        name="join-mapping-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1,
        assertion_kind="asserted",
        primary_iri_variable="join_mapping",
        detail_variables=(
            "mapped_relation",
            "join_direction",
            "join_path",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: join-mapping-detail
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?join_mapping ?label ?mapped_relation ?join_direction ?join_path
                        ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?join_mapping { <{entity_iri}> }
          GRAPH ?g {
            ?join_mapping a op:JoinMapping .
            OPTIONAL { ?join_mapping rdfs:label ?label . }
            OPTIONAL { ?join_mapping op:mappedRelationType ?mapped_relation . }
            OPTIONAL { ?join_mapping op:joinDirection ?join_direction . }
            OPTIONAL { ?join_mapping op:joinPath ?join_path . }
            OPTIONAL { ?join_mapping op:schemaSource ?schema_source . }
            OPTIONAL { ?join_mapping op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """),
    ),
    "enum-meaning-list": ReadModelTemplate(
        name="enum-meaning-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        primary_iri_variable="enum_meaning",
        detail_variables=(
            "mapped_property",
            "enum_value",
            "business_meaning",
            "semantic_value",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: enum-meaning-list
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?enum_meaning ?label ?mapped_property ?enum_value ?business_meaning
                        ?semantic_value ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?enum_meaning a op:EnumValueMeaning .
            OPTIONAL { ?enum_meaning rdfs:label ?label . }
            OPTIONAL { ?enum_meaning op:mappedProperty ?mapped_property . }
            OPTIONAL { ?enum_meaning op:enumValue ?enum_value . }
            OPTIONAL { ?enum_meaning op:businessMeaning ?business_meaning . }
            OPTIONAL { ?enum_meaning op:semanticValue ?semantic_value . }
            OPTIONAL { ?enum_meaning op:schemaSource ?schema_source . }
            OPTIONAL { ?enum_meaning op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label ?enum_meaning
        LIMIT {limit}
        """),
    ),
    "enum-meaning-detail": ReadModelTemplate(
        name="enum-meaning-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1,
        assertion_kind="asserted",
        primary_iri_variable="enum_meaning",
        detail_variables=(
            "mapped_property",
            "enum_value",
            "business_meaning",
            "semantic_value",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: enum-meaning-detail
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?enum_meaning ?label ?mapped_property ?enum_value ?business_meaning
                        ?semantic_value ?schema_source ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?enum_meaning { <{entity_iri}> }
          GRAPH ?g {
            ?enum_meaning a op:EnumValueMeaning .
            OPTIONAL { ?enum_meaning rdfs:label ?label . }
            OPTIONAL { ?enum_meaning op:mappedProperty ?mapped_property . }
            OPTIONAL { ?enum_meaning op:enumValue ?enum_value . }
            OPTIONAL { ?enum_meaning op:businessMeaning ?business_meaning . }
            OPTIONAL { ?enum_meaning op:semanticValue ?semantic_value . }
            OPTIONAL { ?enum_meaning op:schemaSource ?schema_source . }
            OPTIONAL { ?enum_meaning op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """),
    ),
    "metric-list": ReadModelTemplate(
        name="metric-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        primary_iri_variable="metric",
        detail_variables=(
            "grain",
            "time_field",
            "measure",
            "value_expression",
            "filters",
            "aggregation",
            "null_value_rule",
            "denominator_rule",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: metric-list
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?metric ?label ?grain ?time_field ?measure ?value_expression ?filters
                        ?aggregation ?null_value_rule ?denominator_rule ?schema_source
                        ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g {
            ?metric a op:MetricDefinition .
            OPTIONAL { ?metric rdfs:label ?label . }
            OPTIONAL { ?metric op:metricGrain ?grain . }
            OPTIONAL { ?metric op:metricTimeField ?time_field . }
            OPTIONAL { ?metric op:metricMeasure ?measure . }
            OPTIONAL { ?metric op:valueExpression ?value_expression . }
            OPTIONAL { ?metric op:metricFilters ?filters . }
            OPTIONAL { ?metric op:metricAggregation ?aggregation . }
            OPTIONAL { ?metric op:nullValueRule ?null_value_rule . }
            OPTIONAL { ?metric op:denominatorRule ?denominator_rule . }
            OPTIONAL { ?metric op:schemaSource ?schema_source . }
            OPTIONAL { ?metric op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        ORDER BY ?label ?metric
        LIMIT {limit}
        """),
    ),
    "metric-detail": ReadModelTemplate(
        name="metric-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1,
        assertion_kind="asserted",
        primary_iri_variable="metric",
        detail_variables=(
            "grain",
            "time_field",
            "measure",
            "value_expression",
            "filters",
            "aggregation",
            "null_value_rule",
            "denominator_rule",
            "schema_source",
            "semantic_version",
        ),
        body=_op_body("""# template: metric-detail
        PREFIX op: <{op_prefix}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?metric ?label ?grain ?time_field ?measure ?value_expression ?filters
                        ?aggregation ?null_value_rule ?denominator_rule ?schema_source
                        ?semantic_version ?graph WHERE {
          VALUES ?g { {graph_iris} }
          VALUES ?metric { <{entity_iri}> }
          GRAPH ?g {
            ?metric a op:MetricDefinition .
            OPTIONAL { ?metric rdfs:label ?label . }
            OPTIONAL { ?metric op:metricGrain ?grain . }
            OPTIONAL { ?metric op:metricTimeField ?time_field . }
            OPTIONAL { ?metric op:metricMeasure ?measure . }
            OPTIONAL { ?metric op:valueExpression ?value_expression . }
            OPTIONAL { ?metric op:metricFilters ?filters . }
            OPTIONAL { ?metric op:metricAggregation ?aggregation . }
            OPTIONAL { ?metric op:nullValueRule ?null_value_rule . }
            OPTIONAL { ?metric op:denominatorRule ?denominator_rule . }
            OPTIONAL { ?metric op:schemaSource ?schema_source . }
            OPTIONAL { ?metric op:semanticVersion ?semantic_version . }
          }
          BIND(?g AS ?graph)
        }
        LIMIT {limit}
        """),
    ),
}


# R4.0-002 common business declaration, over the same governed graph scope.
# Keep it as a literal: contextual references remain ordinary graph relations,
# where existing resource authorization can filter their endpoints.
for _name in (
    "class-detail", "entity-detail", "ontology-schema-summary", "property-list",
    "relation-type-list", "entity-list",
):
    _template = _TEMPLATES[_name]
    _annotations = {"semantic_definition": "semanticDefinition"}
    if _name in {"entity-detail", "entity-list"}:
        _annotations.update({
            "action_definition": "actionDefinition",
            "parameter_definition": "parameterDefinition",
            "rule_definition": "ruleDefinition",
        })
    _body = _template.body.replace(
        " WHERE {", " " + " ".join(f"?{field}" for field in _annotations) + " WHERE {", 1
    )
    _end = _body.rfind("\n        }")
    _body = (
        _body[:_end]
        + "".join(
            "\n          OPTIONAL { VALUES ?definition_graph { {graph_iris} } "
            + f"GRAPH ?definition_graph {{ ?{_template.primary_iri_variable} "
            + f"<{OP_VOCAB_PREFIX}{predicate}> ?{field} . }} }}"
            for field, predicate in _annotations.items()
        )
        + _body[_end:]
    )
    _TEMPLATES[_name] = replace(
        _template, body=_body, projection_version="semantic-read-v2",
        detail_variables=(*_template.detail_variables, *_annotations),
    )


def get_template(name: str) -> ReadModelTemplate:
    if name not in _TEMPLATES:
        raise KeyError(name)
    return _TEMPLATES[name]


def list_templates() -> list[ReadModelTemplate]:
    return list(_TEMPLATES.values())


SEMANTIC_CONTEXT_TEMPLATE_VERSION = "semantic-context-v1"


def semantic_context_candidates_query(
    graph_to_ontology: dict[str, str],
    terms: list[str],
    limit: int,
    operation_type: str | None = None,
    operation_predicates: set[str] | None = None,
) -> str:
    """Return the fixed lexical corpus query for a resolved current scope."""
    graph_scope_values = _graph_scope_values(graph_to_ontology)
    predicate_label_pairs = _same_ontology_graph_pairs(graph_to_ontology)
    subject_match = _contains_any("LCASE(STR(?subject))", terms)
    predicate_match = _contains_any("LCASE(STR(?predicate))", terms)
    object_match = _contains_any("LCASE(STR(?object))", terms)
    label_match = _contains_any("LCASE(STR(?lexicalLabel))", terms)
    alias_match = _contains_any("LCASE(STR(?lexicalAlias))", terms)
    description_match = _contains_any("LCASE(STR(?lexicalDescription))", terms)
    predicate_label_match = _contains_any("LCASE(STR(?lexicalPredicateLabel))", terms)
    operation_filters = _operation_projection_filters(operation_type, operation_predicates)
    return f"""# template: semantic-context-candidates
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?graph ?candidateType ?subject ?predicate ?object ?matchedField ?matchedValue
       (SAMPLE(?subjectLabelValue) AS ?subjectLabel)
       (GROUP_CONCAT(DISTINCT STR(?aliasValue); separator="|") AS ?aliases)
       (SAMPLE(?descriptionValue) AS ?description)
       (GROUP_CONCAT(DISTINCT STR(?subjectTypeValue); separator="|") AS ?subjectTypes)
WHERE {{
  {{
    SELECT DISTINCT ?graph ?ontologyScope ?candidateType ?subject ?predicate ?object
                    ?matchedField ?matchedValue WHERE {{
      VALUES (?graph ?ontologyScope) {{ {graph_scope_values} }}
      {{ GRAPH ?graph {{ ?subject ?resourcePredicate ?resourceObject . }}
           FILTER({subject_match})
           BIND("resource" AS ?candidateType)
           BIND("identifier" AS ?matchedField)
           BIND(STR(?subject) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject rdfs:label ?lexicalLabel . }}
                 FILTER({label_match})
                 BIND("resource" AS ?candidateType)
                 BIND("label" AS ?matchedField)
                 BIND(STR(?lexicalLabel) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject skos:altLabel ?lexicalAlias . }}
                 FILTER({alias_match})
                 BIND("resource" AS ?candidateType)
                 BIND("alias" AS ?matchedField)
                 BIND(STR(?lexicalAlias) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject rdfs:comment ?lexicalDescription . }}
                 FILTER({description_match})
                 BIND("resource" AS ?candidateType)
                 BIND("description" AS ?matchedField)
                 BIND(STR(?lexicalDescription) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject dcterms:description ?lexicalDescription . }}
                 FILTER({description_match})
                 BIND("resource" AS ?candidateType)
                 BIND("description" AS ?matchedField)
                 BIND(STR(?lexicalDescription) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject ?predicate ?object . }}
                 FILTER({predicate_match})
                 BIND("statement" AS ?candidateType)
                 BIND("identifier" AS ?matchedField)
                 BIND(STR(?predicate) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject ?predicate ?object . }}
                 FILTER(ISLITERAL(?object) && ({object_match}))
                 BIND("statement" AS ?candidateType)
                 BIND("value" AS ?matchedField)
                 BIND(STR(?object) AS ?matchedValue) }}
      UNION {{ GRAPH ?graph {{ ?subject ?predicate ?object . }}
                 VALUES (?graph ?predicateLabelGraph) {{
                   {predicate_label_pairs}
                 }}
                 GRAPH ?predicateLabelGraph {{
                   ?predicate rdfs:label ?lexicalPredicateLabel .
                 }}
                 FILTER({predicate_label_match})
                 BIND("statement" AS ?candidateType)
                 BIND("predicate" AS ?matchedField)
                 BIND(STR(?lexicalPredicateLabel) AS ?matchedValue) }}
      {operation_filters}
    }}
  }}
  OPTIONAL {{ GRAPH ?graph {{ ?subject rdfs:label ?subjectLabelValue . }} }}
  OPTIONAL {{ GRAPH ?graph {{ ?subject skos:altLabel ?aliasValue . }} }}
  OPTIONAL {{ GRAPH ?graph {{
    {{ ?subject rdfs:comment ?descriptionValue . }}
    UNION {{ ?subject dcterms:description ?descriptionValue . }}
  }} }}
  OPTIONAL {{ GRAPH ?graph {{ ?subject rdf:type ?subjectTypeValue . }} }}
}}
GROUP BY ?graph ?candidateType ?subject ?predicate ?object ?matchedField ?matchedValue
ORDER BY ?graph ?candidateType ?subject ?predicate ?object ?matchedField ?matchedValue
LIMIT {int(limit)}
"""


def semantic_context_neighborhood_query(
    graph_iris: list[str],
    anchor_iris: list[str],
    limit: int,
    operation_type: str | None = None,
    operation_predicates: set[str] | None = None,
) -> str:
    values = _iri_values(graph_iris)
    anchors = _iri_values(anchor_iris)
    operation_filters = _operation_projection_filters(operation_type, operation_predicates)
    return f"""# template: semantic-context-neighborhood
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?graph ?subject ?predicate ?object ?subjectLabel ?objectLabel
       ?predicateLabel ?subjectType WHERE {{
  VALUES ?graph {{ {values} }}
  GRAPH ?graph {{
    VALUES ?anchor {{ {anchors} }}
    ?subject ?predicate ?object .
    FILTER(?subject = ?anchor || ?object = ?anchor)
    {operation_filters}
    OPTIONAL {{ ?subject rdfs:label ?subjectLabel . }}
    OPTIONAL {{ ?object rdfs:label ?objectLabel . }}
    OPTIONAL {{ ?predicate rdfs:label ?predicateLabel . }}
    OPTIONAL {{ ?subject rdf:type ?subjectType . }}
  }}
}}
ORDER BY ?graph ?subject ?predicate ?object
LIMIT {int(limit)}
"""


def _iri_values(iris: list[str]) -> str:
    return " ".join(URIRef(iri).n3() for iri in iris)


def _graph_scope_values(graph_to_ontology: dict[str, str]) -> str:
    return " ".join(
        f"({URIRef(graph_iri).n3()} {Literal(ontology_id).n3()})"
        for graph_iri, ontology_id in graph_to_ontology.items()
    )


def _same_ontology_graph_pairs(graph_to_ontology: dict[str, str]) -> str:
    return " ".join(
        f"({URIRef(fact_graph).n3()} {URIRef(label_graph).n3()})"
        for fact_graph, fact_ontology in graph_to_ontology.items()
        for label_graph, label_ontology in graph_to_ontology.items()
        if fact_ontology == label_ontology
    )


def _contains_any(expression: str, terms: list[str]) -> str:
    return (
        " || ".join(f"CONTAINS({expression}, LCASE({Literal(term).n3()}))" for term in terms)
        or "false"
    )


def _operation_projection_filters(
    operation_type: str | None, operation_predicates: set[str] | None
) -> str:
    if not operation_type:
        return ""
    predicates = ", ".join(URIRef(value).n3() for value in sorted(operation_predicates or set()))
    predicate_filter = (
        f"FILTER(!BOUND(?predicate) || ?predicate NOT IN ({predicates}))" if predicates else ""
    )
    return (
        f"FILTER NOT EXISTS {{ GRAPH ?graph {{ ?subject a {URIRef(operation_type).n3()} . }} }}\n"
        f"      {predicate_filter}"
    )
