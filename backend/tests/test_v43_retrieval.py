"""R4.3 retrieval: actual RDF queries, previews and cache boundaries."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, OWL, RDFS

from app.core.config import Settings
from app.services.embedding import EmbeddingClient
from app.services.semantic_retrieval import (
    SemanticResourceRetrievalService, SemanticRetrievalProjectionService, _QUERY_VECTORS,
)
from app.services.semantic_retrieval_text import definition_text_fields
from app.services.semantic_context_query import _best_match
from test_r4008_context_query import context as v43_context, identity  # noqa: F401

context = v43_context


def test_saved_definition_recalls_owner_and_preserves_unknown(context):
    _, _, declare, query, _ = context
    owner = declare('opaque', label='R17', semanticDefinition={
        'semantic_role': 'Rule', 'business_meaning': '关单必须核实现场服务记录',
        'applicability': '仅限正式维修', 'unknowns': ['紧急审批阈值尚未确认'],
        'not_applicable': ['演示环境'], 'conflicting_meanings': ['旧版按接单计算'],
    })
    for term, field in [('现场服务', 'business_meaning'), ('正式维修', 'applicability'),
                        ('紧急审批', 'unknowns'), ('演示环境', 'not_applicable'),
                        ('接单计算', 'conflicting_meanings')]:
        result = query([term], resource_types=['instance'], depth=0)
        row = next(row for row in result['primary_matches'] if row['iri'] == str(owner))
        assert 'semantic_definition.' + field in row['match']['matched_fields']
        assert row['data']['semantic_definition']['unknowns'] == ['紧急审批阈值尚未确认']
    assert query(['未保存批准人'], depth=0)['primary_matches'] == []


def test_projection_embeds_only_saved_contract_content(context):
    service, graph, declare, _, vocab = context
    owner = declare('unlabeled-meaning', semanticDefinition={
        'business_meaning': '维修收入仅按已确认结算额', 'unknowns': ['税率未知'],
        'secret': 'do-not-index',
    }, parameterDefinition={'missing_meaning': '缺值表示尚未审核', 'value_type': 'decimal'})
    graph.add((owner, RDF.type, OWL.Class))
    graph.add((owner, URIRef('https://business.test/secret'), Literal('row-secret')))
    builder = SemanticRetrievalProjectionService(service.session, service.rdf_store, Mock(), service.settings)
    scope = service.scope_resolver.resolve(project_id='project-1', scope_mode='ontologies',
                                          ontology_ids=['ontology-1'])
    service.rdf_store.graph_exists = lambda iri: True
    service.rdf_store.get_graph = lambda iri, format: service.rdf_store.dataset.serialize(format='trig')
    documents = builder._metadata_documents(
        ontology_id='ontology-1', model_revision=1, job_id='job', partition='partition',
        scope=SimpleNamespace(model_graph_iris=scope.graph_iris),
    )
    doc = next(row for row in documents if row['resource_iri'] == str(owner))
    assert '维修收入仅按已确认结算额' in doc['document_text']
    assert '税率未知' in doc['document_text'] and '缺值表示尚未审核' in doc['document_text']
    assert 'do-not-index' not in doc['document_text'] and 'row-secret' not in doc['document_text']
    assert any(row['predicate'] == vocab + 'semanticDefinition' for row in doc['descriptions'])


def test_preview_shared_neighbors_pagination_and_exact_details(context):
    _, graph, declare, query, _ = context
    a = declare('root-a', 'Action', label='close a')
    b = declare('root-b', 'Action', label='close b')
    shared = declare('shared', semanticDefinition={
        'semantic_role': 'Rule', 'business_meaning': '业务条件' * 2000,
        'unknowns': ['最终批准方式未知'],
    })
    predicate = URIRef('https://business.test/constrainedBy')
    graph.add((a, predicate, shared))
    graph.add((b, predicate, shared))
    full = query(['close'], depth=2, context_limit=100, context_detail='full')
    preview = query(['close'], depth=2, context_limit=100, context_detail='preview')
    assert {identity(row) for row in full['related_context']} == {
        identity(row) for row in preview['related_context']}
    row = next(row for row in preview['related_context'] if row['iri'] == str(shared)
               and row['target_kind'] == 'resource')
    assert row['preview'] and row['details_omitted'] and row['truncated']
    assert row['semantic_role'] == 'Rule' and len(row['excerpt']) == 160
    assert '最终批准方式未知' not in json.dumps(preview['related_context'], ensure_ascii=False)
    for root in preview['primary_matches']:
        assert any(preview['related_context'][n['preview_ref']]['id'] == str(shared)
                   for n in root['neighbors'])
        assert root['data']['semantic_definition']['business_meaning']
    detail = query([str(shared)], context_detail='preview')
    assert detail['primary_matches'][0]['data']['semantic_definition']['unknowns'] == ['最终批准方式未知']
    page = query(['close'], depth=2, context_limit=2, context_detail='preview')
    rows = list(page['related_context'])
    while cursor := page['context_page']['next_context_cursor']:
        page = query(['close'], depth=2, context_limit=2, context_detail='preview', context_cursor=cursor)
        assert page['context_page']['returned'] <= 2
        rows.extend(page['related_context'])
    assert {identity(row) for row in rows} == {identity(row) for row in full['related_context']}
    assert len(rows) == len({identity(row) for row in rows})
    assert len(json.dumps(preview, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False))


def test_type_paths_and_shared_adjacency_keep_root_distances(context):
    service, graph, declare, query, _ = context
    a = declare('a', label='start a')
    b = declare('b', label='start b')
    kind = declare('type')
    other = declare('other')
    graph.add((RDF.type, RDFS.label, Literal('type')))
    graph.add((a, RDF.type, kind))
    graph.add((b, RDF.type, kind))
    graph.add((other, RDF.type, kind))
    graph.add((URIRef('https://business.test/cycle'), RDFS.label, Literal('cycle')))
    graph.add((other, URIRef('https://business.test/cycle'), a))
    calls = []
    original = service.rdf_store.query_sparql
    def tracked(text, **kwargs):
        if 'template: semantic-context-neighborhood' in text:
            calls.append(text)
        return original(text, **kwargs)
    service.rdf_store.query_sparql = tracked
    cached = query(['start'], depth=3, context_limit=100, context_detail='preview',
                   expansion_strategy='fixed', context_order='graph_distance')
    cached_calls = len(calls)
    calls.clear()
    original_chunks = service._neighborhood_chunks
    def uncached(scope, frontier):
        service._adjacency_cache.clear()
        yield from original_chunks(scope, frontier)
    service._neighborhood_chunks = uncached
    baseline = query(['start'], depth=3, context_limit=100, context_detail='preview',
                     expansion_strategy='fixed', context_order='graph_distance')
    assert cached == baseline
    assert cached_calls < len(calls)
    other_row = next(row for row in cached['related_context'] if row['id'] == str(other))
    assert len(other_row['root_paths']) == 2


def test_partial_token_is_not_full_expression_exact():
    match = _best_match('close work order', ['close work order', 'close', 'work', 'order'],
                        [('label', 'close', 1000, 'exact_label')])
    assert match['score'] < 1000 and 'exact_label' not in match['reasons']
    assert 'label_term_equal' in match['reasons']
    assert _best_match('close', ['close'], [('label', 'close', 1000, 'exact_label')])['score'] == 1000
    assert definition_text_fields('semantic_definition', '{broken') == []


def test_query_vectors_reuse_and_config_credential_ttl_fences(monkeypatch):
    _QUERY_VECTORS.clear()
    calls = []
    def embed(self, values):
        calls.append(values)
        return [[1.0] * self.dimensions for _ in values]
    monkeypatch.setattr(EmbeddingClient, 'embed', embed)
    settings = Settings(embedding_dimensions=256, embedding_api_key='test-only')
    service = SemanticResourceRetrievalService(Mock(), settings)
    first = service._query_vectors(['同一查询', 'another'])
    first[0][0] = 9
    assert service._query_vectors(['同一查询'])[0][0] == 1
    assert len(calls) == 1
    changed = SemanticResourceRetrievalService(Mock(), settings.model_copy(update={'embedding_model':'other'}))
    changed._query_vectors(['同一查询'])
    changed = SemanticResourceRetrievalService(Mock(), settings.model_copy(update={'embedding_api_key':'different'}))
    changed._query_vectors(['同一查询'])
    assert len(calls) == 3
    monkeypatch.setattr('app.services.semantic_retrieval.time.monotonic', lambda: 1e12)
    service._query_vectors(['同一查询'])
    assert len(calls) == 4
    _QUERY_VECTORS.clear()


def test_preview_authorizes_full_definition_before_omission(context):
    from app.services.semantic_access import SemanticAccessView
    service, graph, declare, query, _ = context
    root = declare('safe', label='safe')
    secret = 'https://business.test/protected'
    neighbor = declare('neighbor', semanticDefinition={'business_meaning': 'public ' * 100, 'unknowns': [secret]})
    graph.add((root, URIRef('https://business.test/linkedTo'), neighbor))
    service.access_view = SemanticAccessView(requires_filtering=True,
                                             _unauthorized_iris=frozenset({secret}))
    result = query([str(root)], context_detail='preview')
    serialized = json.dumps(result)
    assert str(neighbor) not in serialized and secret not in serialized
    assert result['primary_matches'][0]['neighbors'] == []


def test_rank_fusion_is_scale_independent_and_preserves_candidates():
    from app.services.semantic_ranking import rank_context_candidates
    items = [
        {'id': 'semantic', 'kind': 'instance', 'ontology_id': 'o',
         'match': {'lexical_score': 0, 'semantic_similarity': .99}},
        {'id': 'joint', 'kind': 'instance', 'ontology_id': 'o',
         'match': {'lexical_score': 650, 'semantic_similarity': .80}},
        {'id': 'lexical', 'kind': 'instance', 'ontology_id': 'o',
         'match': {'lexical_score': 850, 'semantic_similarity': None}},
    ]
    rank_context_candidates(items)
    scores = {item['id']: item['match']['rank_score'] for item in items}
    assert scores['joint'] > scores['semantic']
    assert len(items) == 3
    for item in items:
        item['match']['lexical_score'] *= 100
    rank_context_candidates(items)
    assert scores == {item['id']: item['match']['rank_score'] for item in items}


def test_fixed_candidate_comparison_reports_regression_and_missing_recall():
    from app.cli.compare_semantic_ranking import compare
    import pytest
    def item(iri, lex, semantic):
        return {'id': iri, 'kind': 'instance', 'ontology_id': 'o',
                'match': {'lexical_score': lex, 'semantic_similarity': semantic}}
    # A joint hit need not answer the question: this counterexample must remain visible.
    packet = {'visibility': 'public', 'evidence_scope': 'controlled_contract_fixture', 'cases': [{
        'question_id': 'counterexample', 'query': '条件',
        'candidates': [item('answer', 0, .99), item('background', 650, .65)],
        'relevance': {'answer': 3, 'background': 1, 'not-recalled': 2},
    }]}
    result = compare(packet)
    assert result['regressions'] == 1
    assert result['cases'][0]['not_recalled'] == ['not-recalled']
    assert result['consumer_coverage'] == 'not_measured'
    with pytest.raises(ValueError, match='public'):
        compare({**packet, 'visibility': 'hidden'})


def test_invalid_provider_batch_is_degraded_and_not_cached(monkeypatch):
    _QUERY_VECTORS.clear()
    monkeypatch.setattr(EmbeddingClient, 'embed', lambda self, values: [])
    service = SemanticResourceRetrievalService(Mock(), Settings(embedding_api_key='test-only'))
    service.repository.index_status = lambda **kwargs: {'ontology_id': 'o', 'status': 'current'}
    scope = SimpleNamespace(ontologies=[SimpleNamespace(ontology_id='o', model_revision=1)])
    for operation in (lambda: service.recall(scope=scope, query='bad', resource_kinds={'instance'},
                                            search_mode='hybrid', limit=5),
                      lambda: service.recall_multi(scope=scope, queries=['bad'],
                            resource_kinds={'instance'}, search_mode='hybrid', limit=5)):
        result = operation()
        assert result['completeness'] == 'degraded'
        assert result['warnings'][0]['code'] == 'semantic_recall_degraded'
    assert not _QUERY_VECTORS


def test_definition_recall_respects_mapping_and_metric_kinds(context):
    from app.services.semantic_retrieval import _resource_kind
    _, graph, declare, query, vocab = context
    for name, rdf_type, kind in [('map', 'TableMapping', 'mapping'), ('metric', 'MetricDefinition', 'metric')]:
        owner = declare(name, semanticDefinition={'business_meaning': '未标名称的核算范围'})
        graph.add((owner, RDF.type, URIRef(vocab + rdf_type)))
        assert _resource_kind([vocab + rdf_type]) == kind
        result = query(['核算范围'], resource_types=[kind], depth=0)
        assert any(row['id'] == str(owner) and row['kind'] == kind for row in result['primary_matches'])
