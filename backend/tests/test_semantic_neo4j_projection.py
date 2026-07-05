from app.services.semantic_neo4j_projection import Neo4jSemanticProjectionService
from app.services.semantic_read_scope import ScopeResolution


class _FakeResult:
    def __iter__(self):
        return iter([])


class FakeSession:
    def __init__(self):
        self.queries: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **kwargs):
        self.queries.append((query, kwargs))
        return _FakeResult()


class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()

    def session(self):
        return self.session_obj


class FakeStore:
    def __init__(self, content):
        self.content = content

    def get_graph(self, iri, fmt):
        return self.content


def _scope(iris):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
    )


def test_rebuild_clears_only_target_partition():
    store = FakeStore("@prefix ex: <http://example.test/> . ex:alice ex:knows ex:bob .")
    driver = FakeDriver()
    service = Neo4jSemanticProjectionService(rdf_store=store, driver=driver)
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/neo4j/neo4j-v1",
    )
    assert counts["node_count"] == 2
    assert counts["relationship_count"] == 1
    clear_query, clear_kwargs = next(
        (q, kw) for q, kw in driver.session_obj.queries if "DETACH DELETE" in q
    )
    assert clear_kwargs["partition"] == "gs-1/neo4j/neo4j-v1"


def test_nodes_tagged_with_partition_metadata():
    store = FakeStore("@prefix ex: <http://example.test/> . ex:alice ex:knows ex:bob .")
    driver = FakeDriver()
    service = Neo4jSemanticProjectionService(rdf_store=store, driver=driver)
    service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/neo4j/neo4j-v1",
    )
    merge_query = next(
        q for q, _ in driver.session_obj.queries if "MERGE" in q and "SemanticProjection" in q
    )
    assert "projection_job_id" in merge_query
    assert "graph_set_id" in merge_query


def test_no_driver_returns_counts_only():
    store = FakeStore("@prefix ex: <http://example.test/> . ex:alice ex:knows ex:bob .")
    service = Neo4jSemanticProjectionService(rdf_store=store, driver=None)
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/neo4j/neo4j-v1",
    )
    assert counts["node_count"] == 2
