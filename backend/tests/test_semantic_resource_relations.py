"""v4.2 relations use the governed node window and actual RDF triples."""

import json
from types import SimpleNamespace

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.util import from_n3

from app.core.config import Settings
from app.services.operation_semantics import canonical_operation_iri, operation_quads
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_read_model import ReadModelError, SemanticReadModelService
from app.services.semantic_sparql_templates import OP_VOCAB_PREFIX, get_template
from test_semantic_read_model import FakeScopeResolver, FakeStore, _resolution
from test_operation_semantics import _operation


ONTOLOGY = "https://example.test/graph/ontology/a"
DATA = "https://example.test/graph/ontology/b"
EX = "https://example.test/"


class DatasetStore:
    """Run production queries, preserving real RDF term bindings."""

    def __init__(self):
        self.dataset = Dataset()
        self.queries = []

    def query_read_model(self, query, **kwargs):
        self.queries.append(query)
        result = self.dataset.query(query)
        return SimpleNamespace(bindings=[
            {str(key): value for key, value in row.items()} for row in result.bindings
        ])


def service(store, hidden=()):
    return SemanticReadModelService(
        store, FakeScopeResolver(_resolution([ONTOLOGY, DATA])),
        access_view=SemanticAccessView(
            requires_filtering=bool(hidden), _unauthorized_iris=frozenset(hidden),
        ),
    )


def edge(source="a", target="b", predicate="related", graph=DATA, label=None):
    return {
        "source": EX + source, "target": EX + target, "relation": EX + predicate,
        "graph": graph, **({"label": label} if label is not None else {}),
    }


def fake_store(edges, extra_nodes=()):
    return FakeStore({
        "template: schema-summary": [
            {"class": EX + name, "label": name, "graph": ONTOLOGY}
            for name in ("a", "b", "c", *extra_nodes)
        ],
        "template: resource-relations": edges,
    })


def test_actual_rdf_class_type_unclassified_individuals_and_schema_endpoints():
    store = DatasetStore()
    ontology = store.dataset.graph(URIRef(ONTOLOGY))
    data = store.dataset.graph(URIRef(DATA))
    for name in ("Parent", "Child"):
        ontology.add((URIRef(EX + name), RDF.type, OWL.Class))
    ontology.add((URIRef(EX + "Child"), RDFS.subClassOf, URIRef(EX + "Parent")))
    relation = URIRef(EX + "related")
    ontology.add((relation, RDF.type, OWL.ObjectProperty))
    ontology.add((relation, RDFS.label, Literal("related to")))
    for name in ("typed", "unclassified1", "unclassified2"):
        iri = URIRef(EX + name)
        data.add((iri, RDF.type, OWL.NamedIndividual))
        data.add((iri, URIRef(OP_VOCAB_PREFIX + "id"), Literal(name)))
    data.add((URIRef(EX + "typed"), RDF.type, URIRef(EX + "Child")))
    data.add((URIRef(EX + "unclassified1"), relation, URIRef(EX + "unclassified2")))
    # JSON is a literal and does not create a relation to Parent.
    data.add((URIRef(EX + "unclassified1"), relation, Literal(json.dumps({
        "target": EX + "Parent",
    }))))
    # Non-NamedIndividual endpoints have actual schema-to-schema relations.
    ontology.add((relation, RDFS.domain, URIRef(EX + "Child")))
    settings = Settings()
    operation = _operation(target_resource_type_iri=EX + "Parent")
    for subject, predicate, obj, _graph in operation_quads(operation, settings, "o"):
        ontology.add((from_n3(subject), from_n3(predicate), from_n3(obj)))
    operation_iri = canonical_operation_iri(settings, operation["operation_id"])
    assert (URIRef(operation_iri), RDF.type, OWL.NamedIndividual) not in ontology
    result = service(store).read_model("gs-1", "resource-relations")
    triples = {(i["source"], i["relation"], i["target"]) for i in result["items"]}
    assert triples == {
        (EX + "Child", str(RDFS.subClassOf), EX + "Parent"),
        (EX + "typed", str(RDF.type), EX + "Child"),
        (EX + "unclassified1", str(relation), EX + "unclassified2"),
        (str(relation), str(RDFS.domain), EX + "Child"),
        (operation_iri, OP_VOCAB_PREFIX + "targetResourceType", EX + "Parent"),
    }
    assert result["paging"]["complete"]
    assert all(item["assertion_kind"] == "asserted" for item in result["items"])
    assert result["model_revision"] == service(store).read_model(
        "gs-1", "resource-list", field_set="detail", limit=500,
    )["model_revision"]
    template = get_template("resource-relations")
    assert not hasattr(template, "required_roles")
    assert not template.needs_reasoning and "NamedIndividual" not in template.body


def test_endpoint_window_is_in_query_before_limit_outside_edges_cannot_consume_budget():
    store = DatasetStore()
    graph = store.dataset.graph(URIRef(ONTOLOGY))
    for name in ("a", "b"):
        graph.add((URIRef(EX + name), RDF.type, OWL.Class))
    graph.add((URIRef(EX + "a"), URIRef(EX + "related"), URIRef(EX + "b")))
    # These resources are outside resource-list; all these edges sort first.
    for n in range(1001):
        graph.add((URIRef(EX + f"0outside{n}"), URIRef(EX + "related"), URIRef(EX + "b")))
    result = service(store).read_model("gs-1", "resource-relations", limit=1)
    assert len(result["items"]) == 1 and result["items"][0]["source"] == EX + "a"
    query = store.queries[-1]
    assert "FILTER(?source IN (" in query and "?target IN (" in query
    assert "outside" not in query
    assert result["paging"]["complete"]


def test_real_rdf_mapping_nested_reference_is_governed_before_endpoint_window():
    store = DatasetStore()
    graph = store.dataset.graph(URIRef(ONTOLOGY))
    parent = URIRef(EX + "Parent")
    graph.add((parent, RDF.type, OWL.Class))
    for name in ("publicMapping", "nestedHiddenMapping"):
        mapping = URIRef(EX + name)
        graph.add((mapping, RDF.type, URIRef(OP_VOCAB_PREFIX + "TableMapping")))
        graph.add((mapping, URIRef(OP_VOCAB_PREFIX + "mappedClass"), parent))
    graph.add((URIRef(EX + "nestedHiddenMapping"), URIRef(OP_VOCAB_PREFIX + "columnMappings"),
               Literal(json.dumps({"nested": [{"ref": EX + "secret"}]}))))
    result = service(store, [EX + "secret"]).read_model("gs-1", "resource-relations")
    assert len(result["items"]) == 1
    assert result["items"][0]["source"] == EX + "publicMapping"
    assert result["paging"]["complete"]
    assert "nestedHiddenMapping" not in store.queries[-1]
    assert "secret" not in json.dumps(result)


def test_authorization_nested_references_predicate_and_hidden_first_window():
    hidden = [EX + f"hidden{n}" for n in range(501)]
    hidden_predicate = EX + "privatePredicate"
    store = fake_store([
        edge(predicate="privatePredicate"), edge("hidden0"),
        edge(target="c"), edge(label=json.dumps({"ref": hidden[0]})), edge(),
    ])
    rows = store.rows_by_template["template: schema-summary"]
    rows[:0] = [{"class": iri, "label": "000 hidden", "graph": ONTOLOGY} for iri in hidden]
    rows[-1]["semantic_definition"] = json.dumps({"nested": {"ref": hidden[0]}})
    result = service(store, [*hidden, hidden_predicate]).read_model(
        "gs-1", "resource-relations", limit=1,
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["relation"] == EX + "related"
    assert result["paging"] == {
        "limit": 1, "returned": 1, "visible_count": 1,
        "has_more": False, "truncated": False, "complete": True,
    }
    assert "hidden" not in json.dumps(result) and "privatePredicate" not in json.dumps(result)
    assert EX + "c" not in store.last_query


def test_real_rdf_hidden_predicates_and_nested_labels_cannot_fill_fetch_window(monkeypatch):
    # A small real query ceiling exercises the same boundary without a slow
    # 10,000-row dataset; the next test separately covers the production cap.
    monkeypatch.setattr("app.services.semantic_read_model._FILTERED_FETCH_LIMIT", 3)
    store = DatasetStore()
    graph = store.dataset.graph(URIRef(ONTOLOGY))
    for name in ("a", "b", "c"):
        graph.add((URIRef(EX + name), RDF.type, OWL.Class))
    hidden_predicate = URIRef(EX + "0privatePredicate")
    for source, target in (("a", "b"), ("a", "c"), ("b", "a"), ("b", "c")):
        graph.add((URIRef(EX + source), hidden_predicate, URIRef(EX + target)))
    reader = service(store, [str(hidden_predicate), EX + "secret"])
    result = reader.read_model("gs-1", "resource-relations")
    assert result["items"] == [] and result["paging"]["complete"]
    graph.add((URIRef(EX + "a"), URIRef(EX + "related"), URIRef(EX + "b")))
    # Numerous nested protected labels cannot multiply edge rows or leak.
    for n in range(5):
        graph.add((URIRef(EX + "related"), RDFS.label, Literal(json.dumps({
            "secret": EX + "secret", "index": n,
        }))))
    result = reader.read_model("gs-1", "resource-relations")
    assert len(result["items"]) == 1 and result["items"][0]["label"] is None
    assert result["paging"]["complete"] and result["paging"]["visible_count"] == 1
    assert "secret" not in json.dumps(result)


def test_adapter_reports_truncated_even_below_query_ceiling():
    class TruncatedStore(FakeStore):
        def query_read_model(self, query, **kwargs):
            result = super().query_read_model(query, **kwargs)
            result.truncated = "template: resource-relations" in query
            return result

    store = fake_store([edge()])
    result = service(TruncatedStore(store.rows_by_template)).read_model(
        "gs-1", "resource-relations",
    )
    assert not result["paging"]["complete"] and result["paging"]["truncated"]


def test_real_rdf_ten_thousand_hidden_edges_do_not_starve_later_visible_edge():
    store = DatasetStore()
    graph = store.dataset.graph(URIRef(ONTOLOGY))
    nodes = [URIRef(EX + f"node{n:03d}") for n in range(100)]
    visible_source, visible_target = URIRef(EX + "zsource"), URIRef(EX + "ztarget")
    for iri in [*nodes, visible_source, visible_target]:
        graph.add((iri, RDF.type, OWL.Class))
    private = URIRef(EX + "privatePredicate")
    for source in nodes:
        for target in nodes:
            graph.add((source, private, target))
    reader = service(store, [str(private)])
    hidden_only = reader.read_model("gs-1", "resource-relations")
    assert hidden_only["items"] == [] and hidden_only["paging"]["complete"]
    graph.add((visible_source, URIRef(EX + "related"), visible_target))
    result = reader.read_model("gs-1", "resource-relations")
    assert len(result["items"]) == 1
    assert result["items"][0]["source"] == str(visible_source)
    assert result["paging"]["visible_count"] == 1 and result["paging"]["complete"]
    assert "privatePredicate" not in json.dumps(result)


def test_stable_identity_sort_deduplicate_before_edge_window():
    store = fake_store([edge(graph=DATA), edge(graph=ONTOLOGY), edge("b", "c"), edge()])
    reader = service(store)
    result = reader.read_model("gs-1", "resource-relations", limit=1)
    assert result["paging"]["visible_count"] == 2
    assert result["paging"]["has_more"] and not result["paging"]["complete"]
    first = result["items"][0]
    assert first["ontology_id"] == "gs-1"
    store.rows_by_template["template: resource-relations"].reverse()
    assert reader.read_model("gs-1", "resource-relations", limit=1)["items"] == [first]
    store.rows_by_template["template: resource-relations"] = [edge(graph=ONTOLOGY, label="changed")]
    assert reader.read_model("gs-1", "resource-relations")["items"][0]["id"] == first["id"]


def test_underlying_fetch_ceiling_and_endpoint_window_are_partial_without_hidden_counts():
    store = fake_store([edge()] * 10_000)
    result = service(store).read_model("gs-1", "resource-relations")
    assert result["paging"]["visible_count"] == 1
    assert result["paging"]["truncated"] and not result["paging"]["complete"]
    assert "read_model_rows_truncated" in {w["code"] for w in result["warnings"]}
    store = fake_store([], extra_nodes=[f"node{n}" for n in range(500)])
    result = service(store).read_model("gs-1", "resource-relations")
    assert result["items"] == [] and not result["paging"]["complete"]
    assert "resource_relations_endpoint_window_incomplete" in {
        w["code"] for w in result["warnings"]
    }


def test_only_hidden_endpoints_return_empty_complete_window():
    store = fake_store([edge()])
    result = service(store, [EX + n for n in ("a", "b", "c")]).read_model(
        "gs-1", "resource-relations",
    )
    assert result["items"] == [] and result["paging"]["complete"]
    assert result["paging"]["visible_count"] == 0
    assert "template: resource-relations" not in store.last_query


def test_non_asserted_include_rejected_and_edge_limit_bounded():
    reader = service(fake_store([edge()]))
    with pytest.raises(ReadModelError, match="include=asserted"):
        reader.read_model("gs-1", "resource-relations", include="full-working-view")
    assert reader.read_model("gs-1", "resource-relations", limit=2000)["paging"]["limit"] == 1000


def test_resource_window_signature_change_rejects_mixed_scope():
    class ChangingResolver(FakeScopeResolver):
        reads = 0

        def resolve(self, *args, **kwargs):
            resolution = super().resolve(*args, **kwargs)
            self.reads += 1
            resolution.model_revision = f"signature-{self.reads}"
            return resolution

    reader = SemanticReadModelService(
        fake_store([edge()]), ChangingResolver(_resolution([ONTOLOGY, DATA])),
    )
    with pytest.raises(ReadModelError, match="Model revision changed"):
        reader.read_model("gs-1", "resource-relations")


@pytest.mark.parametrize("legacy", [False, True])
def test_mapping_reference_fields_connect_loaded_definitions_without_guessing(legacy):
    store = DatasetStore()
    data = store.dataset.graph(URIRef(DATA))
    for name in ("mapping", "table", "value"):
        iri = URIRef(EX + name)
        data.add((iri, RDF.type, OWL.NamedIndividual))
        data.add((iri, URIRef(OP_VOCAB_PREFIX + "id"), Literal(name)))
    predicate = URIRef(OP_VOCAB_PREFIX.replace("/vocab/", "/property/") + "mapping_payload")
    payload = {
        "left_table_mapping": {"definition_ref": "table"},
        "semantic_value_ref": {"definition_ref": "value"},
        "business_meaning": EX + "table",
        "example": {"target": EX + "table"},
        "unknown_ref": {"definition_ref": "not-loaded"},
    }
    data.add((URIRef(EX + "mapping"), predicate, Literal(str(payload) if legacy else json.dumps(payload))))
    result = service(store).read_model("gs-1", "resource-relations")
    assert {(item["target"], item["field_path"]) for item in result["items"]} == {
        (EX + "table", "left_table_mapping.definition_ref"),
        (EX + "value", "semantic_value_ref.definition_ref"),
    }
    assert all(item["edge_kind"] == "structured_reference" for item in result["items"])
    assert all(item["relation"] == str(predicate) for item in result["items"])
    assert all(item["ontology_id"] == "gs-1" for item in result["items"])
    assert result["paging"]["complete"]
    # Authorization is applied before resolving references and counting edges.
    hidden_result = service(store, [EX + "value"]).read_model("gs-1", "resource-relations")
    assert len(hidden_result["items"]) == 1
    assert hidden_result["items"][0]["target"] == EX + "table"
    assert hidden_result["paging"]["visible_count"] == 1
    assert EX + "value" not in json.dumps(hidden_result)
    assert service(store, [str(predicate)]).read_model("gs-1", "resource-relations")["items"] == []
    data.set((URIRef(EX + "mapping"), predicate, Literal(json.dumps({
        "left_table_mapping": {"definition_ref": "table"},
        "nested": {"target_iri": EX + "value"},
    }))))
    assert service(store, [EX + "value"]).read_model("gs-1", "resource-relations")["items"] == []


def test_structured_iri_references_keep_positions_and_do_not_replace_rdf_edges():
    store = DatasetStore()
    data = store.dataset.graph(URIRef(DATA))
    for name in ("source", "target"):
        data.add((URIRef(EX + name), RDF.type, OWL.NamedIndividual))
        data.add((URIRef(EX + name), URIRef(OP_VOCAB_PREFIX + "id"), Literal(name)))
    source, target = URIRef(EX + "source"), URIRef(EX + "target")
    predicate = URIRef(OP_VOCAB_PREFIX + "parameterDefinition")
    payload = {"first_iri": str(target), "nested": [{"second_iri": str(target)}]}
    data.add((source, predicate, Literal(json.dumps(payload))))
    data.add((source, predicate, target))
    result = service(store).read_model("gs-1", "resource-relations")
    assert len(result["items"]) == 3
    assert len({item["id"] for item in result["items"]}) == 3
    assert {item.get("field_path") for item in result["items"]} == {
        None, "first_iri", "nested[0].second_iri",
    }
    assert {item["edge_kind"] for item in result["items"]} == {
        "rdf_relation", "structured_reference",
    }
    bounded = service(store).read_model("gs-1", "resource-relations", limit=1)
    assert bounded["paging"]["visible_count"] == 3
    assert bounded["paging"]["has_more"] and not bounded["paging"]["complete"]
    assert service(store, [str(target)]).read_model("gs-1", "resource-relations")["items"] == []


def test_ambiguous_definition_ids_and_malformed_literals_never_invent_edges():
    store = DatasetStore()
    data = store.dataset.graph(URIRef(DATA))
    for name in ("source", "target1", "target2"):
        data.add((URIRef(EX + name), RDF.type, OWL.NamedIndividual))
        data.add((URIRef(EX + name), URIRef(OP_VOCAB_PREFIX + "id"),
                  Literal("same" if name.startswith("target") else name)))
    source = URIRef(EX + "source")
    predicate = URIRef(OP_VOCAB_PREFIX.replace("/vocab/", "/property/") + "mapping_payload")
    data.add((source, predicate, Literal("{'mapped_definition': {'definition_ref': 'same'}}")))
    data.add((source, predicate, Literal("__import__('os').getcwd()")))
    data.add((source, URIRef(OP_VOCAB_PREFIX + "parameterDefinition"), Literal("{invalid")))
    result = service(store).read_model("gs-1", "resource-relations")
    assert result["items"] == []
