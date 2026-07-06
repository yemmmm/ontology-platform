from unittest.mock import MagicMock
from app.services.semantic_build_overview import (
    BuildOverviewResponse,
    BuildOverviewService,
    NextAction,
)


def _service(read_model_payload, brief, questions):
    read_model = MagicMock(return_value=read_model_payload)
    brief_fn = MagicMock(return_value=brief)
    question_fn = MagicMock(return_value=questions)
    return BuildOverviewService(
        read_model=read_model,
        brief_summary=brief_fn,
        question_summary=question_fn,
    )


def _gs_payload(members=None, missing=0):
    return {
        "items": [{
            "graph_set_id": "gs-1",
            "members": members or [],
            "missing_evidence_count": missing,
            "last_semantic_edit_at": None,
        }],
    }


def _member(**kw):
    defaults = dict(iri="g://x", role="asserted_ontology", editable=True,
                    validation_stale=False, reasoning_stale=False, rule_stale=False,
                    last_semantic_edit_at=None)
    defaults.update(kw)
    return defaults


def _brief(completeness=1.0, missing=None):
    from app.services.semantic_build_overview import BriefSummary
    return BriefSummary(completeness=completeness, missing_fields=missing or [])


def _questions(total=0, **by_status):
    from app.services.semantic_build_overview import CompetencyQuestionSummary
    defaults = {"draft": 0, "approved": 0, "testable": 0, "passed": 0, "failed": 0}
    defaults.update(by_status)
    return CompetencyQuestionSummary(total=total, by_status=defaults)


def test_build_overview_composes_all_sections():
    svc = _service(
        _gs_payload(members=[_member(role="asserted_ontology")]),
        _brief(0.5, ["scope"]),
        _questions(3, draft=1, passed=2),
    )
    resp = svc.build(session=MagicMock(), project_id="p-1", ontology_id="o-1", graph_set_id="gs-1")
    assert isinstance(resp, BuildOverviewResponse)
    assert resp.ontology_id == "o-1"
    assert resp.graph_set.members[0].role == "asserted_ontology"
    assert resp.project_brief.completeness == 0.5
    assert resp.competency_questions.total == 3
    assert len(resp.next_actions) > 0


def test_build_overview_next_actions_priority_order():
    svc = _service(
        _gs_payload(members=[_member(validation_stale=True, reasoning_stale=True)], missing=5),
        _brief(0.0, ["a", "b"]),
        _questions(1, draft=1),
    )
    resp = svc.build(session=MagicMock(), project_id="p", ontology_id="o", graph_set_id="gs")
    keys = [a.key for a in resp.next_actions]
    assert keys == ["complete_brief", "approve_questions", "recompute_validation"]


def test_build_overview_no_actions_when_clean():
    svc = _service(
        _gs_payload(members=[_member()], missing=0),
        _brief(1.0),
        _questions(0),
    )
    resp = svc.build(session=MagicMock(), project_id="p", ontology_id="o", graph_set_id="gs")
    assert resp.next_actions == []


def test_parse_empty_payload_is_safe():
    svc = _service({}, _brief(1.0), _questions(0))
    resp = svc.build(session=MagicMock(), project_id="p", ontology_id="o", graph_set_id="gs")
    assert resp.graph_set.members == []
    assert resp.graph_set.missing_evidence_count == 0
