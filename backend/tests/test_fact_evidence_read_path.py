"""Read-path contract after R4.0-012 tracing suspension."""

import pytest

from app.services.semantic_read_model import ReadModelError, SemanticReadModelService


def test_semantic_read_model_does_not_expose_evidence_field_set():
    assert not hasattr(SemanticReadModelService, "_fetch_evidence_bindings_from_pg")
    assert not hasattr(SemanticReadModelService, "_missing_evidence_count")


def test_evidence_field_set_is_rejected_before_read_model_dispatch():
    with pytest.raises(ReadModelError, match="field_set=evidence is no longer supported"):
        SemanticReadModelService(
            rdf_store=object(),
            scope_resolver=object(),
        ).read_model(
            graph_set_id="graph-set",
            model_name="fact-audit-queue",
            field_set="evidence",
        )
