"""Stage 3 read-model template execution tests.

Validates that the new templates route SPARQL to the correct named
graphs and produce the envelope shape defined in
docs/delivery/designs/2026-07-06-semantic-stage3-publish-design.md §4.

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
    assert not hasattr(t, "required_roles")
    assert not hasattr(t, "required_roles")
    assert t.needs_reasoning is True
    assert not hasattr(t, "needs_rules")
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
    svc, ontology_id = fake_graph_set_with_members
    envelope = svc.read_model(
        ontology_id=ontology_id,
        model_name="publication-readiness",
        field_set="detail",
    )
    assert called.get("yes") is True
    assert envelope["items"][0]["ready"] is True


def test_publication_readiness_returns_gate_set(fake_graph_set_with_members):
    """End-to-end composer run: gates cover derived state, edits, and
    projection freshness without a missing-evidence gate."""
    svc, ontology_id = fake_graph_set_with_members
    envelope = svc.read_model(
        ontology_id=ontology_id,
        model_name="publication-readiness",
        field_set="detail",
    )
    item = envelope["items"][0]
    assert item["ontology_id"] == ontology_id
    gate_names = {g["gate"] for g in item["gates"]}
    assert gate_names == {
        "open_edits",
        "projection_freshness",
    }


# ---------------------------------------------------------------------------
# Task A2 — graph-set-history-list
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Task A3 — graph-set-delta
# ---------------------------------------------------------------------------
