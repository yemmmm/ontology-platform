"""Opt-in runtime contracts with isolated fixture resources and explicit cleanup."""

from __future__ import annotations

import os
import json
from uuid import uuid4

import httpx
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS
from sqlalchemy import create_engine, text, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.models import (
    ProjectModel,
    ProjectUserMembershipModel,
    OntologyModel,
    UserModel,
    ApiKeyModel,
    SemanticGraphSetModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
)
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_retrieval import PgVectorRetrievalRepository, RetrievalConfig

pytestmark = pytest.mark.skipif(
    os.environ.get("ONTOLOGY_LIVE_CONTEXT_TEST") != "1",
    reason="Opt in to isolated PostgreSQL/Oxigraph/runtime contract tests",
)


def test_pgvector_stable_distance_and_iri_continuation():
    settings = Settings()
    config = RetrievalConfig.from_settings(settings)
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            session.execute(
                text("""CREATE TEMP TABLE semantic_projection_manifests (
                active_job_id text, graph_set_id text, projection_kind text, status text,
                source_signature text, projection_version text
            ) ON COMMIT DROP""")
            )
            session.execute(
                text("""CREATE TEMP TABLE semantic_retrieval_documents (
                resource_iri text, resource_kind text, assertion_kind text, label text,
                labels jsonb, aliases jsonb, descriptions jsonb, mapping_evidence jsonb,
                rdf_types jsonb, embedding vector, build_job_id text, graph_set_id text,
                ontology_id text, workspace_version text, source_signature text,
                rule_set_signature text, projection_version text, embedding_config_hash text
            ) ON COMMIT DROP""")
            )
            session.execute(
                text("""INSERT INTO semantic_projection_manifests VALUES (
                'job','g','vector','current','ss',:version
            )"""),
                {"version": config.projection_version},
            )
            vector = [1.0] + [0.0] * (config.dimensions - 1)
            for i in range(7):
                session.execute(
                    text("""INSERT INTO semantic_retrieval_documents VALUES (
                    :iri,'instance','asserted','same label','[]','[]','[]','[]','[]',
                    CAST(:vector AS vector),'job','g','o','wv','ss','rs',:version,:config
                )"""),
                    {
                        "iri": f"https://r4008.test/{i}",
                        "vector": json.dumps(vector),
                        "version": config.projection_version,
                        "config": config.config_hash,
                    },
                )
            repository = PgVectorRetrievalRepository(session, config)
            args = dict(
                graph_set_id="g",
                ontology_id="o",
                workspace_version="wv",
                source_signature="ss",
                rule_signature="rs",
                resource_kinds={"instance"},
                query_vector=vector,
                limit=3,
            )
            first = repository.exact_cosine_candidates(**args)
            assert len(first) == 3
            second = repository.exact_cosine_candidates(
                **args, after=(first[-1]["distance"], first[-1]["resource_iri"])
            )
            third = repository.exact_cosine_candidates(
                **args, after=(second[-1]["distance"], second[-1]["resource_iri"])
            )
            assert [row["resource_iri"] for row in first + second + third] == [
                f"https://r4008.test/{i}" for i in range(7)
            ]
            assert all(row["distance"] == 0 for row in first + second + third)
            session.rollback()
    finally:
        engine.dispose()


def test_restarted_context_endpoint_with_real_scope_graph_and_cursor():
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id, ontology_id, user_id = (f"r4008-{kind}-{token[:24]}" for kind in ("p", "o", "u"))
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{ontology_id}"
    vocab = str(namespace_from_settings(settings).vocab)
    resource_prefix = f"https://r4008.test/{token}/"
    graph = Graph()
    for i in range(3):
        root = URIRef(resource_prefix + f"action-{i}")
        graph.add((root, RDFS.label, Literal("common action")))
        graph.add(
            (
                root,
                URIRef(vocab + "semanticDefinition"),
                Literal('{"semantic_role":"Action","unknowns":["owner"]}'),
            )
        )
        for n in range(4):
            graph.add((root, URIRef(resource_prefix + f"value-{n}"), Literal(f"{i}-{n}")))
    rule = URIRef(resource_prefix + "rule")
    graph.add((rule, RDFS.label, Literal("linked policy")))
    graph.add((URIRef(resource_prefix + "action-1"), URIRef(resource_prefix + "policy"), rule))
    graph.add(
        (
            rule,
            URIRef(vocab + "ruleDefinition"),
            Literal('{"script_source":"return true","script_language":"javascript"}'),
        )
    )
    owned_graph_iris = []
    try:
        with factory() as session:
            session.add(ProjectModel(id=project_id, name=project_id, normalized_label=project_id))
            session.flush()
            ontology = OntologyModel(id=ontology_id, project_id=project_id, name=ontology_id)
            session.add(ontology)
            session.flush()
            workspace = OntologyWorkspaceService(session, settings)
            workspace.ensure(ontology)
            owned_graph_iris = [
                member["graph_iri"] for member in workspace.context(ontology_id)["members"]
            ]
            session.add(UserModel(id=user_id, username=user_id, is_org_admin=True))
            session.flush()
            session.add(ProjectUserMembershipModel(project_id=project_id, user_id=user_id))
            session.commit()
            _, key = create_api_key(
                session, name=project_id, project_id=project_id, scopes=["read"], user_id=user_id
            )
        store.put_named_graph(graph_iri, graph.serialize(format="turtle"), "turtle")
        with httpx.Client(
            base_url="http://127.0.0.1:8001", headers={"Authorization": "Bearer " + key}, timeout=30
        ) as client:
            body = {
                "project_id": project_id,
                "scope_mode": "ontologies",
                "ontology_ids": [ontology_id],
                "queries": ["common action"],
                "semantic_roles": ["Action"],
                "search_mode": "lexical",
                "limit": 1,
                "context_limit": 2,
                "depth": 2,
                "context_detail": "compact",
            }

            def query(**extra):
                response = client.post("/api/semantic/context:query", json={**body, **extra})
                assert response.status_code == 200, response.text
                return response.json()

            first = query()
            assert first["query"]["result_scope"] == "authorized_query_scope"
            second = query(match_cursor=first["matches_page"]["next_match_cursor"])
            rows, page = list(second["related_context"]), second
            while cursor := page["context_page"]["next_context_cursor"]:
                page = query(context_cursor=cursor)
                assert page["primary_matches"] == second["primary_matches"]
                rows.extend(page["related_context"])
            assert {row["data"].get("object") for row in rows} >= {f"1-{n}" for n in range(4)}
            assert "return true" not in json.dumps(rows)
            assert any(row.get("projection") for row in rows)
            third = query(match_cursor=page["matches_page"]["next_match_cursor"])
            assert third["primary_matches"][0]["iri"].endswith("action-2")
            assert third["context_page"]["expansion"]["status"] == "complete"
    finally:
        store.drop_named_graph(graph_iri)
        with factory() as session:
            session.execute(delete(ApiKeyModel).where(ApiKeyModel.user_id == user_id))
            sets = list(
                session.scalars(
                    select(SemanticGraphSetModel).where(
                        SemanticGraphSetModel.scope_type == "ontology",
                        SemanticGraphSetModel.scope_id == ontology_id,
                    )
                )
            )
            for graph_set in sets:
                session.delete(graph_set)
            session.flush()
            session.execute(
                delete(SemanticGraphRegistryModel).where(
                    SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                    SemanticGraphRegistryModel.semantic_owner_id == ontology_id,
                )
            )
            session.execute(
                delete(SemanticGraphRevisionModel).where(
                    SemanticGraphRevisionModel.graph_iri.in_(owned_graph_iris),
                )
            )
            session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
            session.execute(delete(UserModel).where(UserModel.id == user_id))
            session.commit()
            assert session.get(ProjectModel, project_id) is None
            assert session.get(UserModel, user_id) is None
            assert (
                session.scalar(select(ApiKeyModel.id).where(ApiKeyModel.user_id == user_id)) is None
            )
            assert (
                session.scalar(
                    select(SemanticGraphSetModel.id).where(
                        SemanticGraphSetModel.scope_id == ontology_id
                    )
                )
                is None
            )
            assert (
                session.scalar(
                    select(SemanticGraphRegistryModel.id).where(
                        SemanticGraphRegistryModel.semantic_owner_id == ontology_id
                    )
                )
                is None
            )
        assert not store.graph_exists(graph_iri)
