from app.services.semantic_visibility import (
    SemanticVisibilityPolicy,
    VisibilityDecision,
)


def test_unrestricted_graph_passes_through():
    policy = SemanticVisibilityPolicy(graph_labels={"http://op/s/graph/data/x": "internal"})
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/x",
        visibility_context={"labels": ["internal"]},
    )
    assert decision.allow is True
    assert decision.redact_evidence is False


def test_restricted_graph_without_label_is_omitted():
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/secret": "restricted"}
    )
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/secret",
        visibility_context={"labels": ["internal"]},
    )
    assert decision.allow is False


def test_restricted_graph_with_label_redacts_evidence():
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/secret": "restricted"}
    )
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/secret",
        visibility_context={"labels": ["internal", "restricted"]},
    )
    assert decision.allow is True
    assert decision.redact_evidence is True


def test_filter_graphs_drops_unauthorized():
    policy = SemanticVisibilityPolicy(
        graph_labels={
            "http://op/s/graph/data/a": "internal",
            "http://op/s/graph/data/b": "restricted",
        }
    )
    allowed, warnings = policy.filter_graphs(
        [
            "http://op/s/graph/data/a",
            "http://op/s/graph/data/b",
        ],
        visibility_context={"labels": ["internal"]},
    )
    assert allowed == ["http://op/s/graph/data/a"]
    assert any("restricted" in w["message"] for w in warnings)


def test_filter_graphs_keeps_unrestricted_graphs():
    policy = SemanticVisibilityPolicy(graph_labels={"http://op/s/graph/data/a": "internal"})
    allowed, warnings = policy.filter_graphs(
        ["http://op/s/graph/data/a", "http://op/s/graph/data/unrestricted"],
        visibility_context={"labels": ["internal"]},
    )
    assert set(allowed) == {
        "http://op/s/graph/data/a",
        "http://op/s/graph/data/unrestricted",
    }
    assert warnings == []


def test_redact_evidence_text_replaces_with_placeholder():
    policy = SemanticVisibilityPolicy(graph_labels={})
    assert policy.redact_evidence_text("Secret content") == "[redacted]"


def test_redact_evidence_text_handles_none():
    policy = SemanticVisibilityPolicy(graph_labels={})
    assert policy.redact_evidence_text(None) is None


def test_decision_is_dataclass():
    policy = SemanticVisibilityPolicy(graph_labels={})
    decision = policy.evaluate("http://op/s/graph/data/x", visibility_context=None)
    assert isinstance(decision, VisibilityDecision)
