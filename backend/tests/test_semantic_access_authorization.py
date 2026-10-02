"""Semantic access authorization tests (R3.0-004 §5 resolver/view)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.models import OntologyModel, ProjectModel
from app.security.auth import AuthPrincipal, resolve_api_key
from subject_access_support import create_api_key
from app.services.evidence_reference import (
    EvidenceReferenceNotFound,
    EvidenceReferenceService,
)
from app.services.semantic_access import (
    SemanticAccessDependencyError,
    SemanticAccessResolver,
    SemanticAccessView,
)


def _principal(project_id=None, scopes=("read",), grants=()):
    return AuthPrincipal(
        subject_type="api_key",
        subject_id="key-1",
        actor="key:key-1",
        scopes=frozenset(scopes),
        project_id=project_id,
        auth_method="bearer",
        semantic_grants=frozenset(grants),
    )


def _seed_project(session, name="P"):
    project = ProjectModel(id=name, name=name, normalized_label=name)
    ontology = OntologyModel(id=f"o-{name}", project_id=name, name=f"O-{name}")
    session.add_all([project, ontology])
    session.commit()
    return project, ontology


def _add_set(session, project_id, name, grants, members):
    from app.repositories.models import (
        SemanticProtectionSetMemberModel,
        SemanticProtectionSetModel,
    )

    record = SemanticProtectionSetModel(
        id=name, project_id=project_id, name=name, allowed_grants=list(grants)
    )
    session.add(record)
    session.flush()
    for iri, ontology_id in members:
        session.add(
            SemanticProtectionSetMemberModel(
                protection_set_id=record.id, resource_iri=iri, ontology_id=ontology_id
            )
        )
    session.commit()
    return record


COST_IRI = "https://example.test/entity/cost-1"
PUBLIC_IRI = "https://example.test/entity/public-1"


def test_project_without_protection_sets_uses_fast_path(in_memory_session):
    project, _ontology = _seed_project(in_memory_session, "P")
    view = SemanticAccessResolver(in_memory_session).resolve(_principal("P"), project.id)
    assert view.requires_filtering is False
    assert view.is_member_visible(COST_IRI)


def test_or_formula_across_sets_and_grants(in_memory_session):
    project, _ontology = _seed_project(in_memory_session, "P")
    # same resource in two sets; either covering set grants access
    _add_set(in_memory_session, "P", "s1", ["hr-visibility"], [(COST_IRI, None)])
    _add_set(in_memory_session, "P", "s2", ["cost-visibility", "audit"], [(COST_IRI, None)])
    _add_set(in_memory_session, "P", "s3", ["cost-visibility"], [(PUBLIC_IRI, None)])

    no_grants = SemanticAccessResolver(in_memory_session).resolve(_principal("P"), project.id)
    assert no_grants.requires_filtering is True
    assert no_grants.is_member_visible(COST_IRI) is False
    assert no_grants.is_member_visible(PUBLIC_IRI) is False

    # one grant covering one of the OR-sets unlocks the shared member
    cost_only = SemanticAccessResolver(in_memory_session).resolve(
        _principal("P", grants=("cost-visibility",)), project.id
    )
    assert cost_only.is_member_visible(COST_IRI) is True
    assert cost_only.is_member_visible(PUBLIC_IRI) is True

    # either grant inside one set is enough
    audit_only = SemanticAccessResolver(in_memory_session).resolve(
        _principal("P", grants=("audit",)), project.id
    )
    assert audit_only.is_member_visible(COST_IRI) is True


def test_admin_bypass_is_project_bound(in_memory_session):
    project, _ontology = _seed_project(in_memory_session, "P")
    _seed_project(in_memory_session, "Q")
    _add_set(in_memory_session, "P", "s1", ["cost-visibility"], [(COST_IRI, None)])

    org_admin = _principal(None, scopes=("read", "admin"))
    assert SemanticAccessResolver(in_memory_session).resolve(org_admin, "P").requires_filtering is False

    same_project_admin = _principal("P", scopes=("read", "admin"))
    resolved = SemanticAccessResolver(in_memory_session).resolve(same_project_admin, "P")
    assert resolved.requires_filtering is False

    other_project_admin = _principal("Q", scopes=("read", "admin"))
    cross = SemanticAccessResolver(in_memory_session).resolve(other_project_admin, "P")
    assert cross.requires_filtering is True
    assert cross.is_member_visible(COST_IRI) is False


def test_dangling_members_stay_protected_and_scope_is_conservative(in_memory_session):
    project, ontology = _seed_project(in_memory_session, "P")
    other_ontology = OntologyModel(id="o-other", project_id="P", name="O-other")
    in_memory_session.add(other_ontology)
    in_memory_session.flush()
    dangling = "https://example.test/entity/not-created-yet"
    stale = "https://example.test/entity/stale-ontology"
    elsewhere = "https://example.test/entity/elsewhere"
    _add_set(
        in_memory_session,
        "P",
        "s1",
        ["cost-visibility"],
        [
            (dangling, None),
            (stale, "missing-ontology-id"),
            (COST_IRI, ontology.id),
            (elsewhere, other_ontology.id),
        ],
    )
    view = SemanticAccessResolver(in_memory_session).resolve(_principal("P"), project.id)
    assert view.is_member_visible(dangling) is False
    assert view.is_member_visible(stale) is False

    # members in the queried ontology, and members with null or unknown
    # ontology_id, are conservatively in scope for a whole-request rejection
    in_scope = view.scope_unauthorized_members([ontology.id])
    assert COST_IRI in in_scope
    assert dangling in in_scope
    assert stale in in_scope
    assert elsewhere not in in_scope

    # once created, the dangling member keeps its protection semantics
    assert view.is_member_visible(dangling) is False


def test_resolver_fails_closed_on_database_error(in_memory_session):
    class FailingSession:
        def scalars(self, *_args, **_kwargs):
            raise SQLAlchemyError("control plane down")

    with pytest.raises(SemanticAccessDependencyError):
        SemanticAccessResolver(FailingSession()).resolve(_principal("P"), "P")


def test_view_statement_row_and_quad_filtering():
    view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset({COST_IRI}),
    )
    assert view.is_statement_visible(PUBLIC_IRI, "https://example.test/p/name", ["lit"]) is True
    assert view.is_statement_visible(PUBLIC_IRI, COST_IRI, ["lit"]) is False
    assert view.is_statement_visible(PUBLIC_IRI, "https://example.test/p/x", [COST_IRI]) is False
    # N-Triples term syntax is also recognized
    assert view.is_statement_visible(f"<{COST_IRI}>", "p", []) is False

    rows = [
        {"subject_iri": PUBLIC_IRI, "predicate_iri": "p", "object_value": "v"},
        {"subject_iri": COST_IRI, "predicate_iri": "p", "object_value": "v"},
        {"subject_iri": PUBLIC_IRI, "predicate_iri": "p", "object_value": COST_IRI},
    ]
    assert view.filter_statement_rows(rows) == [rows[0]]

    items = [{"id": PUBLIC_IRI}, {"id": COST_IRI}]
    assert view.filter_items(items) == [items[0]]

    from rdflib import Dataset, URIRef, Literal

    dataset = Dataset()
    graph = dataset.graph(URIRef("https://example.test/graph/a"))
    graph.add((URIRef(PUBLIC_IRI), URIRef("https://example.test/p/n"), Literal("x")))
    nested = json.dumps({"conversion_rule_iri": COST_IRI})
    graph.add((URIRef(PUBLIC_IRI), URIRef("https://example.test/p/mapping"), Literal(nested)))
    graph.add((URIRef(COST_IRI), URIRef("https://example.test/p/n"), Literal("y")))
    filtered = view.filter_quads(dataset)
    remaining = {str(triple[0]) for _g in filtered.graphs() for triple in _g}
    assert remaining == {PUBLIC_IRI}
    assert not any(
        str(triple[2]) == nested
        for graph in filtered.graphs()
        for triple in graph
    )


def test_evidence_reference_visibility_by_association_target(in_memory_session):
    project, ontology = _seed_project(in_memory_session, "P")
    _add_set(in_memory_session, "P", "s1", ["cost-visibility"], [(COST_IRI, None)])

    service = EvidenceReferenceService(in_memory_session)
    cost_ref, _ = service.get_or_create(project.id, "cost-doc", "cost excerpt")
    public_ref, _ = service.get_or_create(project.id, "public-doc", "public excerpt")
    orphan_ref, _ = service.get_or_create(project.id, "orphan-doc", "no associations")
    service.associate(
        project_id=project.id,
        ontology_id=ontology.id,
        graph_set_id=None,
        target_type="entity",
        target_id=COST_IRI,
        references=[cost_ref],
        actor="tester",
    )
    service.associate(
        project_id=project.id,
        ontology_id=ontology.id,
        graph_set_id=None,
        target_type="entity",
        target_id=PUBLIC_IRI,
        references=[public_ref],
        actor="tester",
    )
    in_memory_session.commit()

    operator_view = SemanticAccessResolver(in_memory_session).resolve(
        _principal("P"), project.id
    )
    operator_service = EvidenceReferenceService(in_memory_session, access_view=operator_view)
    rows, total = operator_service.list_references(project.id, limit=10, offset=0)
    assert {row.id for row in rows} == {public_ref.id, orphan_ref.id}
    assert total == 2
    with pytest.raises(EvidenceReferenceNotFound):
        operator_service.get_visible(cost_ref.id)
    assert operator_service.visible_association_count(public_ref.id) == 1
    assert operator_service.visible_association_count(cost_ref.id) == 0

    manager_view = SemanticAccessResolver(in_memory_session).resolve(
        _principal("P", grants=("cost-visibility",)), project.id
    )
    manager_service = EvidenceReferenceService(in_memory_session, access_view=manager_view)
    rows, total = manager_service.list_references(project.id, limit=10, offset=0)
    assert total == 3
    assert manager_service.get_visible(cost_ref.id).id == cost_ref.id


def test_created_api_key_resolves_role_grants(in_memory_session):
    _seed_project(in_memory_session, "P")
    _record, plaintext = create_api_key(
        in_memory_session,
        name="manager",
        project_id="P",
        scopes=["read"],
        semantic_grants=["cost-visibility", "cost-visibility"],
    )
    principal = resolve_api_key(in_memory_session, plaintext)
    assert principal is not None
    assert principal.semantic_grants == frozenset({"cost-visibility"})
