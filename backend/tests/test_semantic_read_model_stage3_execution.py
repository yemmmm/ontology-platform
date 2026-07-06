"""Stage 3 read-model template execution tests.

Validates that the new templates route SPARQL to the correct named
graphs and produce the envelope shape defined in
docs/superpowers/specs/2026-07-06-semantic-stage3-publish-design.md §4.

Reuses the ``conftest_stage3`` fixtures (in-memory SQLite + FakeStore with
per-named-graph triple storage so the delta composer can diff real triples).
"""
from __future__ import annotations

# ``pytest_plugins`` is the canonical pytest hook for loading fixtures from a
# sibling module whose name is not ``conftest.py``. Listed as a module path
# relative to ``rootdir``.
pytest_plugins = ("conftest_stage3",)

from app.services.semantic_sparql_templates import _TEMPLATES


# ---------------------------------------------------------------------------
# Task A1 — publication-readiness
# ---------------------------------------------------------------------------


def test_publication_readiness_template_registered() -> None:
    t = _TEMPLATES["publication-readiness"]
    assert t.projection_version == "1"
    assert "asserted_ontology" in t.required_roles
    assert "asserted_data" in t.required_roles
    assert t.needs_reasoning is True
    assert t.needs_rules is True
    assert t.default_limit == 1


def test_publication_readiness_composer_routes_to_dispatch(
    monkeypatch, fake_graph_set_with_members
):
    """The read-model service must dispatch `publication-readiness` to the
    dedicated composer (not the generic SPARQL path)."""
    from app.services import semantic_read_model as mod

    called = {}

    def stub(self, scope, field_set):  # type: ignore[no-untyped-def]
        called["yes"] = True
        return {"ready": True}

    monkeypatch.setattr(
        mod.SemanticReadModelService,
        "_compose_publication_readiness",
        stub,
        raising=True,
    )
    svc, graph_set_id = fake_graph_set_with_members
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="publication-readiness",
        field_set="detail",
    )
    assert called.get("yes") is True
    assert envelope["items"][0]["ready"] is True


def test_publication_readiness_returns_gate_set(fake_graph_set_with_members):
    """End-to-end composer run: gates include validation/reasoning/rule/
    missing_evidence/open_edits/projection_freshness, and the missing-evidence
    gate is ``passed`` because the FakeStore returns zero missing rows."""
    svc, graph_set_id = fake_graph_set_with_members
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="publication-readiness",
        field_set="detail",
    )
    item = envelope["items"][0]
    assert item["graph_set_id"] == graph_set_id
    gate_names = {g["gate"] for g in item["gates"]}
    assert gate_names == {
        "validation_stale",
        "reasoning_stale",
        "rule_stale",
        "missing_evidence",
        "open_edits",
        "projection_freshness",
    }
    # Missing-evidence gate is passed because the FakeStore canned row reports
    # ``count=0``.
    missing = next(g for g in item["gates"] if g["gate"] == "missing_evidence")
    assert missing["status"] == "passed"
    assert "0 facts missing evidence" == missing["label"]


# ---------------------------------------------------------------------------
# Task A2 — graph-set-history-list
# ---------------------------------------------------------------------------


def test_graph_set_history_list_template_registered() -> None:
    t = _TEMPLATES["graph-set-history-list"]
    assert t.projection_version == "1"
    assert t.default_limit == 50


def test_graph_set_history_list_returns_sets_in_scope(
    fake_graph_set_with_members, second_graph_set_same_scope
):
    """Composer returns both graph sets in scope with status derived from
    member editability and derived pointer timestamps."""
    svc, _ = fake_graph_set_with_members
    other_id = second_graph_set_same_scope
    envelope = svc.read_model(
        graph_set_id=other_id,  # any set in scope works; composer queries by scope
        model_name="graph-set-history-list",
        field_set="summary",
    )
    assert envelope["model_name"] == "graph-set-history-list"
    rows = envelope["items"][0]
    assert rows["total"] >= 2
    ids = {r["graph_set_id"] for r in rows["graph_sets"]}
    assert other_id in ids
    for r in rows["graph_sets"]:
        assert r["status"] in ("editable", "locked", "superseded")
        assert "created_at" in r
        assert "locked_at" in r
        assert "member_count" in r


# ---------------------------------------------------------------------------
# Task A3 — graph-set-delta
# ---------------------------------------------------------------------------


def test_graph_set_delta_template_registered() -> None:
    t = _TEMPLATES["graph-set-delta"]
    assert t.projection_version == "1"
    assert t.default_limit == 200


def test_graph_set_delta_requires_target_query_param(fake_graph_set_with_members):
    """Without ``target`` the composer raises a 400 ReadModelError."""
    import pytest

    from app.services.semantic_read_model import ReadModelError

    svc, base_id = fake_graph_set_with_members
    with pytest.raises(ReadModelError, match="target"):
        svc.read_model(
            graph_set_id=base_id,
            model_name="graph-set-delta",
            field_set="detail",
        )


def test_graph_set_delta_returns_per_role_triple_diff(
    fake_graph_set_with_members, second_graph_set_with_one_fewer_entity
):
    """Given two graph sets differing by one triple in the asserted_data
    role, the delta composer reports one removed triple group."""
    svc, base_id = fake_graph_set_with_members
    target_id = second_graph_set_with_one_fewer_entity
    envelope = svc.read_model(
        graph_set_id=base_id,
        model_name="graph-set-delta",
        field_set="detail",
        target=target_id,
    )
    rows = envelope["items"][0]
    assert rows["base_graph_set_id"] == base_id
    assert rows["target_graph_set_id"] == target_id
    role_map = {r["role"]: r for r in rows["roles"]}
    assert "asserted_data" in role_map
    ad = role_map["asserted_data"]
    assert ad["counts"]["removed"] >= 1
    assert len(ad["removed"]) >= 1
    # Removed triples carry subject/predicate/object keys.
    assert {"subject", "predicate", "object"} <= set(ad["removed"][0])


def test_read_model_route_threads_target_query_param(
    in_memory_session, fake_store, fake_graph_set_with_members,
    second_graph_set_with_one_fewer_entity,
):
    """End-to-end route test: ``GET /read-models/graph-set-delta?target=...``
    threads the target through to the composer and returns 200."""
    from conftest_stage3 import client_for

    base_id = fake_graph_set_with_members[1]
    target_id = second_graph_set_with_one_fewer_entity
    client = client_for(fake_store, in_memory_session)
    response = client.get(
        f"/api/semantic/graph-sets/{base_id}/read-models/graph-set-delta",
        params={"include": "asserted", "target": target_id, "field_set": "detail"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rows = body["items"][0]
    assert rows["target_graph_set_id"] == target_id


def test_graph_set_delta_counts_independent_of_display_cap(
    in_memory_session, fake_store, fake_graph_set_with_members
):
    """Stage 3 §4.3: ``counts.added`` / ``counts.removed`` must reflect the
    true diff size, while the ``added[]`` / ``removed[]`` arrays are capped
    at ``limit``. The two are independent — a small ``limit`` must NOT
    underreport counts.

    We seed a base asserted_data graph with 50 triples and a target with 30
    additional triples (so target − base = 30 added, base − target = 0
    removed). We then call the delta composer with ``limit=10`` and verify:

    - ``counts.added == 30`` (real diff size)
    - ``len(added) <= 10`` (display cap respected)
    - ``truncated`` is True
    """
    from conftest_stage3 import (
        DATA_GRAPH,
        GRAPH_PREFIX,
        PREFIX,
        _seed_graph_set,
    )

    svc, base_id = fake_graph_set_with_members

    # 50 base triples; 30 additional target-only triples => 30 added.
    base_triples = [
        (f"{PREFIX}ns/entity/e{i}", f"{PREFIX}ns/property/label", f"Entity {i}")
        for i in range(50)
    ]
    target_extra = [
        (f"{PREFIX}ns/entity/x{i}", f"{PREFIX}ns/property/label", f"Extra {i}")
        for i in range(30)
    ]
    target_data_graph = f"{GRAPH_PREFIX}data/ont-stage3-cap"
    target_ontology_graph = f"{GRAPH_PREFIX}ontology/ont-stage3-cap"

    fake_store.set_triples(DATA_GRAPH, base_triples)
    fake_store.set_triples(target_data_graph, base_triples + target_extra)
    # Ontology graph identical on both sides so its role diff is empty.
    fake_store.set_triples(
        target_ontology_graph,
        fake_store._triples.get(
            f"{GRAPH_PREFIX}ontology/ont-stage3", set()
        ),
    )

    target_id = _seed_graph_set(
        in_memory_session,
        graph_set_id="gs-stage3-cap-target",
        name="stage3-cap-target",
        members=[
            (target_ontology_graph, "asserted_ontology"),
            (target_data_graph, "asserted_data"),
        ],
    )

    envelope = svc.read_model(
        graph_set_id=base_id,
        model_name="graph-set-delta",
        field_set="detail",
        target=target_id,
        limit=10,
    )
    rows = envelope["items"][0]
    role_map = {r["role"]: r for r in rows["roles"]}
    ad = role_map["asserted_data"]
    # True diff size reported even though ``limit=10`` was requested.
    assert ad["counts"]["added"] == 30
    assert ad["counts"]["removed"] == 0
    # Display arrays capped.
    assert len(ad["added"]) <= 10
    # Truncation flag set.
    assert rows["truncated"] is True



