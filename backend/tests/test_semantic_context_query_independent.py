"""Independent R1.2-004 verification tests added by the requirement_tester.

These cases intentionally overlap with the developer's focused suite but
verify contract rules at a deeper level or via different entry points so a
silent regression in one assertion cannot hide behind another. They are
additive: they never edit or replace the developer's tests.

Coverage priorities (design / test-plan mapping):
- SC-02: same Project, different principal -> cursor reuse fails closed at the
  full pipeline level (the codec test only covers the codec, not the service
  round trip).
- SC-08: signer rotation across two service invocations returns
  ``invalid_context_cursor`` (full pipeline, ephemeral secret).
- PG-10: cursor payload never contains the raw expression text even after
  base64-decoding the body.
- FU-05: reordering the same expression multiset keeps identities, scores,
  support_count, and final ranking bit-identical.
- FU-06: normalized duplicate expressions do not inflate ``support_count``
  and the original list (with duplicates) is still echoed verbatim.
- BD-05: capability discovery advertises canonical ``queries``, compatibility
  ``query`` alias, defaults/max for limit/context_limit/depth, cursor kinds,
  lifetime, and stable-secret flag.
- PF-01: a multi-expression request performs exactly one scope resolution
  and exactly one embedding batch (instrumented spy, not timing).
- Contract: ``depth=0`` yields empty ``related_context`` and no context
  cursor; ``context_limit=0`` with positive depth keeps matches unaffected.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.api.schemas import SemanticContextQueryRequest
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult
from app.security.auth import AuthPrincipal
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_capabilities import context_query_capabilities
from app.services.semantic_context_cursor import (
    ContextCursorCodec,
)
from app.services.semantic_context_query import (
    SemanticContextQueryService,
)
from app.services.semantic_query_scope import SemanticQueryScopeResolver


pytestmark = pytest.mark.filterwarnings(
    "ignore:Dataset\\.(default_context|contexts) is deprecated:DeprecationWarning"
)


def _principal(subject_id: str = "indep-principal", project_id: str | None = None) -> AuthPrincipal:
    return AuthPrincipal(
        subject_type="api_key",
        subject_id=subject_id,
        actor=f"key:{subject_id}",
        scopes=frozenset({"read"}),
        project_id=project_id,
        auth_method="bearer",
    )


def _candidate(
    *,
    iri: str,
    label: str,
    ontology_id: str = "ontology-1",
    score: int = 600,
    similarity: float | None = 0.6,
    reasons=("semantic_candidate",),
    candidate_level: str = "semantic_candidate",
) -> dict[str, Any]:
    return {
        "id": iri,
        "kind": "concept",
        "ontology_id": ontology_id,
        "iri": iri,
        "label": label,
        "aliases": [],
        "description": None,
        "data": {"rdf_types": []},
        "distance": 0,
        "assertion_kind": "asserted",
        "match": {
            "score": score,
            "lexical_score": 0,
            "semantic_similarity": similarity,
            "effective_score": round(similarity, 3) if similarity is not None else 1.0,
            "candidate_level": candidate_level,
            "method": "semantic",
            "matched_terms": [],
            "matched_fields": [],
            "reasons": list(reasons),
        },
    }


def _exact_candidate(*, iri: str, label: str, ontology_id: str = "ontology-1") -> dict[str, Any]:
    candidate = _candidate(
        iri=iri,
        label=label,
        ontology_id=ontology_id,
        score=1000,
        similarity=None,
        reasons=("exact_label",),
        candidate_level="exact",
    )
    candidate["match"]["lexical_score"] = 1000
    candidate["match"]["semantic_similarity"] = None
    candidate["match"]["effective_score"] = 1.0
    candidate["match"]["method"] = "label"
    return candidate


class _FakeStore:
    def __init__(self, candidates: list[dict[str, Any]] | None = None) -> None:
        self.candidates = candidates or []

    def query_sparql(self, query, timeout_seconds, limit):
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": self.candidates}},
            truncated=False,
        )


class _FakeLineage:
    def get_lineage(self, **kwargs):
        return {
            "lineage_status": "complete",
            "evidence_status": "supported",
            "dependency_evidence_status": "supported",
            "items": [],
            "warnings": [],
        }


class _FakeShapes:
    def read_merged_guidance(self, *_args, **_kwargs):
        return {"fields": []}


class _RecallSpy:
    """Fake ``recall_multi`` that records call count and per-call query count.

    Patched at the class level, so the bound ``self`` is passed as the first
    positional argument; the spy ignores it and only records query inputs.
    """

    def __init__(self, candidates_by_query: list[list[dict[str, Any]]]) -> None:
        self._candidates_by_query = candidates_by_query
        self.calls = 0
        self.queries_seen: list[list[str]] = []

    def __call__(self, *_args, **_kwargs):  # noqa: D401
        self.calls += 1
        queries = _kwargs.get("queries") or (_args[1] if len(_args) > 1 else [])
        self.queries_seen.append(list(queries))
        return {
            "candidates_by_query": self._candidates_by_query,
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        }


def _install_recall_multi(monkeypatch, candidates_by_query) -> _RecallSpy:
    spy = _RecallSpy(candidates_by_query)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        spy,
    )
    return spy


def _ready_ontology(session, settings) -> None:
    if session.get(ProjectModel, "project-1") is None:
        session.add(
            ProjectModel(id="project-1", name="project-1", normalized_label="project-1")
        )
    ontology = OntologyModel(
        id="ontology-1",
        project_id="project-1",
        name="ontology-1",
    )
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()


def _service(session, settings, store, monkeypatch=None, recall_multi=None):
    if recall_multi is not None and monkeypatch is not None:
        _install_recall_multi(monkeypatch, recall_multi)
    return SemanticContextQueryService(
        session,
        store,
        SemanticQueryScopeResolver(session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )


# ---------------------------------------------------------------------------
# SC-02: same Project, different principal -> cursor reuse fails closed
# ---------------------------------------------------------------------------


def test_sc02_same_project_different_principal_cursor_fails_closed(
    in_memory_session, monkeypatch
):
    """Principal A issues a match cursor; principal B (same Project) cannot resume.

    Design §6: the same Project being visible to two principals does not make
    their cursors interchangeable. The codec test only proves the codec layer;
    this proves the full ``query_multi`` round trip maps the failure to
    ``SemanticContextCursorMismatch`` (HTTP 400 ``context_cursor_mismatch``).
    """
    settings = Settings(
        semantic_graph_iri_prefix="https://graphs.test/",
        semantic_context_query_cursor_signing_secret="indep-stable-secret",
    )
    _ready_ontology(in_memory_session, settings)

    candidates = [
        _candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(5)
    ]
    store = _FakeStore([])
    service_a = _service(in_memory_session, settings, store, monkeypatch, [candidates])

    page_a = service_a.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        limit=2,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    next_cursor = page_a["matches_page"]["next_match_cursor"]
    assert next_cursor, "Match cursor must be issued when matches exceed the limit"

    # Principal B can see the same Project but must NOT be able to resume A's cursor.
    service_b = SemanticContextQueryService(
        in_memory_session,
        store,
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )
    from app.services.semantic_context_query import (
        SemanticContextCursorInvalid,
        SemanticContextCursorMismatch,
    )

    with pytest.raises((SemanticContextCursorInvalid, SemanticContextCursorMismatch)) as exc_info:
        service_b.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=["topic"],
            resource_types=["concept"],
            depth=0,
            limit=2,
            principal=_principal(subject_id="principal-b", project_id="project-1"),
            match_cursor=next_cursor,
        )
    # Stable error code that the REST adapter maps to HTTP 400.
    assert exc_info.value.code in {"invalid_context_cursor", "context_cursor_mismatch"}


# ---------------------------------------------------------------------------
# SC-08: signer rotation / restart with ephemeral key
# ---------------------------------------------------------------------------


def test_sc08_ephemeral_signer_rotation_returns_invalid(in_memory_session, monkeypatch):
    """Two codecs with empty secrets derive independent ephemeral keys.

    Design §4.6: a cursor signing-key rotation or process restart when only an
    ephemeral development key is available invalidates outstanding cursors and
    returns ``invalid_context_cursor``. This is exercised at the full pipeline
    level so the service correctly maps the codec failure to the public error.
    """
    settings_first = Settings(
        semantic_graph_iri_prefix="https://graphs.test/",
        semantic_context_query_cursor_signing_secret="",
    )
    _ready_ontology(in_memory_session, settings_first)

    candidates = [
        _candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(5)
    ]
    store = _FakeStore([])
    service_first = _service(in_memory_session, settings_first, store, monkeypatch, [candidates])
    page_first = service_first.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        limit=2,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    cursor = page_first["matches_page"]["next_match_cursor"]
    assert cursor, "Cursor must be issued before rotation can invalidate it"

    # Rotate: a new Settings still has an empty secret, but the codec derives a
    # fresh process-local ephemeral token because it is a brand-new instance.
    codec_first = ContextCursorCodec.from_settings(settings_first)
    settings_second = Settings(
        semantic_graph_iri_prefix="https://graphs.test/",
        semantic_context_query_cursor_signing_secret="",
    )
    codec_second = ContextCursorCodec.from_settings(settings_second)
    assert codec_first._signing_key() != codec_second._signing_key(), (
        "Two fresh codecs with empty secrets must derive independent keys"
    )

    service_second = SemanticContextQueryService(
        in_memory_session,
        store,
        SemanticQueryScopeResolver(in_memory_session, settings_second),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )
    from app.services.semantic_context_query import SemanticContextCursorInvalid

    with pytest.raises(SemanticContextCursorInvalid):
        service_second.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=["topic"],
            resource_types=["concept"],
            depth=0,
            limit=2,
            principal=_principal(subject_id="principal-a", project_id="project-1"),
            match_cursor=cursor,
        )


# ---------------------------------------------------------------------------
# PG-10: cursor payload excludes raw query text
# ---------------------------------------------------------------------------


def test_pg10_cursor_payload_excludes_raw_expression_text(
    in_memory_session, monkeypatch
):
    """Decode the cursor body and assert no original expression substring.

    Design §4.6 / §6: cursor contents exclude raw query text. The codec-level
    test asserts the encoded string lacks the secret value; this decodes the
    body explicitly and walks every JSON value so substring leakage anywhere in
    the payload is caught.
    """
    settings = Settings(
        semantic_graph_iri_prefix="https://graphs.test/",
        semantic_context_query_cursor_signing_secret="indep-stable-secret",
    )
    _ready_ontology(in_memory_session, settings)

    secret_marker = "TopSecretQueryValue-XYZ"
    candidates = [
        _candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(5)
    ]
    store = _FakeStore([])
    service = _service(in_memory_session, settings, store, monkeypatch, [candidates])
    page = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=[secret_marker],
        resource_types=["concept"],
        depth=0,
        limit=2,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    cursor = page["matches_page"]["next_match_cursor"]
    assert cursor

    # Raw token must not contain the marker.
    assert secret_marker not in cursor

    # Decode the body and walk every JSON value to ensure no leakage.
    body_b64 = cursor.split(".", 1)[0]
    padded = body_b64 + "=" * (-len(body_b64) % 4)
    body_bytes = base64.urlsafe_b64decode(padded)
    payload = json.loads(body_bytes.decode("utf-8"))
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert secret_marker not in blob, "Cursor body must not echo raw query text"
    assert secret_marker.casefold() not in blob.casefold()


# ---------------------------------------------------------------------------
# FU-05: expression-order invariance
# ---------------------------------------------------------------------------


def test_fu05_expression_order_does_not_affect_results(
    in_memory_session, monkeypatch
):
    """Reorder the same expression multiset; verify identity/score/support/rank match.

    Design §4.4: reordering the same expression multiset cannot change matches,
    scores, support count, or final order. The developer's test reuses the same
    spy fixture; this builds an explicit symmetric fixture and asserts every
    field independently.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    a = _candidate(iri="https://example.test/A", label="alpha", score=720, similarity=0.72)
    b = _candidate(iri="https://example.test/B", label="beta", score=720, similarity=0.72)

    def run(queries, candidates_by_query):
        spy = _RecallSpy(candidates_by_query)
        monkeypatch.setattr(
            "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
            spy,
        )
        service = SemanticContextQueryService(
            in_memory_session,
            _FakeStore([]),
            SemanticQueryScopeResolver(in_memory_session, settings),
            lineage_service=_FakeLineage(),
            shape_endpoint=_FakeShapes(),
        )
        result = service.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=queries,
            resource_types=["concept"],
            depth=0,
            principal=_principal(subject_id="principal-a", project_id="project-1"),
        )
        return result, spy

    first, spy_first = run(["x", "y"], [[a, b], [a]])
    second, spy_second = run(["y", "x"], [[a], [a, b]])

    # Original order is echoed verbatim; normalized order is the deduped
    # first-seen order, which for a reordered multiset differs.
    assert first["query"]["queries"] == ["x", "y"]
    assert second["query"]["queries"] == ["y", "x"]

    # Identity, score, support, and final rank must be identical. Original
    # input indexes are by definition input-order-dependent (design §4.4 says
    # only original-order echo changes), so they are excluded from the
    # invariance fingerprint.
    def fingerprint(result):
        return [
            (
                item["iri"],
                item["match"]["score"],
                item["fusion"]["best_evidence_tier"],
                item["fusion"]["support_count"],
                len(item["matched_queries"]),
            )
            for item in result["primary_matches"]
        ]

    assert fingerprint(first) == fingerprint(second), (
        "Reordering the expression multiset must not change identity, score, "
        "tier, support_count, or final rank"
    )
    # Exactly one embedding batch in each direction.
    assert spy_first.calls == 1
    assert spy_second.calls == 1


# ---------------------------------------------------------------------------
# FU-06: normalized duplicates do not boost support_count
# ---------------------------------------------------------------------------


def test_fu06_normalized_duplicates_do_not_boost_support_or_rank(
    in_memory_session, monkeypatch
):
    """A normalized duplicate must not increase support_count above its distinct form.

    Design §4.2: normalized duplicate expressions execute once and cannot
    increase expression-support count. The original list (with duplicates) is
    still echoed verbatim.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    shared = _candidate(iri="https://example.test/Shared", label="shared", score=500, similarity=0.5)
    spy = _RecallSpy([[shared]])

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        spy,
    )
    service = SemanticContextQueryService(
        in_memory_session,
        _FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )

    distinct = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["alpha"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    with_dupes = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["alpha", "alpha", "alpha"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )

    distinct_match = distinct["primary_matches"][0]
    dupe_match = with_dupes["primary_matches"][0]
    assert distinct_match["fusion"]["support_count"] == 1
    assert dupe_match["fusion"]["support_count"] == 1, (
        "Normalized duplicates must not inflate support_count"
    )
    assert distinct_match["match"]["score"] == dupe_match["match"]["score"]
    assert with_dupes["query"]["queries"] == ["alpha", "alpha", "alpha"]
    assert with_dupes["query"]["normalized_queries"] == ["alpha"]


# ---------------------------------------------------------------------------
# BD-05: capability discovery metadata
# ---------------------------------------------------------------------------


def test_bd05_capability_discovery_advertises_full_contract():
    """R1.2-007 discovery must expose canonical queries, query alias, limits, cursors.

    Design §4.6 / §7: capability discovery publishes cursor support, limits,
    and the configured lifetime policy. This asserts the metadata keys that
    API/MCP documentation reference.
    """
    settings = Settings(
        semantic_context_query_cursor_signing_secret="indep-stable-secret",
    )
    capabilities = context_query_capabilities(settings)

    # Canonical ``queries`` contract.
    assert capabilities["queries"]["min"] == settings.semantic_context_query_min_queries
    assert capabilities["queries"]["max"] == settings.semantic_context_query_max_queries
    assert (
        capabilities["queries"]["item_char_limit"]
        == settings.semantic_context_query_item_char_limit
    )
    assert (
        capabilities["queries"]["aggregate_char_limit"]
        == settings.semantic_context_query_aggregate_char_limit
    )

    # Compatibility alias.
    assert capabilities["query"]["alias_for"] == "queries[0]"

    # Independent limits.
    assert capabilities["limit"]["default"] == settings.semantic_context_query_match_limit_default
    assert capabilities["limit"]["max"] == settings.semantic_context_query_match_limit_max
    assert (
        capabilities["context_limit"]["default"]
        == settings.semantic_context_query_context_limit_default
    )
    assert (
        capabilities["context_limit"]["max"] == settings.semantic_context_query_context_limit_max
    )

    # Depth.
    assert capabilities["depth"]["default"] == settings.semantic_context_query_depth_default
    assert capabilities["depth"]["max"] == settings.semantic_context_query_depth_max

    # Cursor kinds and lifetime.
    cursor_meta = capabilities["cursors"]
    assert set(cursor_meta["kinds"]) == {"match", "context"}
    assert cursor_meta["lifetime_seconds"] == settings.semantic_context_query_cursor_lifetime_seconds
    assert cursor_meta["stable_secret_configured"] is True


def test_bd05_capability_discovery_reports_ephemeral_when_secret_missing():
    """Without a configured secret the metadata must advertise the limitation.

    Design §7: development fallback may be process-local and must advertise
    that limitation so callers know cursors will not survive restart.
    """
    settings = Settings(semantic_context_query_cursor_signing_secret="")
    capabilities = context_query_capabilities(settings)
    assert capabilities["cursors"]["stable_secret_configured"] is False


# ---------------------------------------------------------------------------
# PF-01: one scope resolution + one embedding batch
# ---------------------------------------------------------------------------


def test_pf01_multi_expression_uses_one_scope_resolution_and_one_batch(
    in_memory_session, monkeypatch
):
    """Eight distinct hybrid expressions must perform one embedding batch.

    Design §5: the implementation must not loop the existing complete Context
    Query pipeline. The developer proves this with a ``_CallSpy``; this test
    uses an independent spy shape and also asserts the queries handed to
    ``recall_multi`` are exactly the distinct execution set in first-seen order.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidates = [
        _candidate(iri="https://example.test/A", label="a", score=500, similarity=0.5)
    ]
    spy = _RecallSpy([candidates, candidates, candidates])

    # Patch the scope resolver to count resolutions. ``SemanticQueryScopeResolver``
    # is instantiated fresh inside the service; patch ``resolve`` on the class.
    resolve_calls = {"count": 0}
    real_resolve = SemanticQueryScopeResolver.resolve

    def counting_resolve(self, *args, **kwargs):
        resolve_calls["count"] += 1
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(SemanticQueryScopeResolver, "resolve", counting_resolve)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        spy,
    )

    service = SemanticContextQueryService(
        in_memory_session,
        _FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )
    service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["a", "b", "c"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    assert resolve_calls["count"] == 1, "Scope resolution must run exactly once"
    assert spy.calls == 1, "Embedding batch must run exactly once"
    assert spy.queries_seen == [["a", "b", "c"]], (
        "recall_multi must receive the distinct execution set in first-seen order"
    )


# ---------------------------------------------------------------------------
# CX-07 + depth=0 contract
# ---------------------------------------------------------------------------


def test_cx07_context_limit_zero_with_positive_depth_keeps_matches(
    in_memory_session, monkeypatch
):
    """``context_limit=0`` with ``depth=1`` must not alter match recall.

    Design §4.5: ``context_limit=0`` is a valid explicit request for matches
    without related context even when depth is positive. It does not alter
    match recall.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidates = [
        _candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(3)
    ]
    spy = _RecallSpy([candidates])
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        spy,
    )
    service = SemanticContextQueryService(
        in_memory_session,
        _FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )
    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=1,
        context_limit=0,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    assert len(result["primary_matches"]) == 3
    assert result["related_context"] == []
    assert result["context_page"]["returned"] == 0
    assert result["context_page"]["truncated"] is False
    assert result["context_page"]["next_context_cursor"] is None


def test_depth_zero_yields_empty_context_and_no_context_cursor(
    in_memory_session, monkeypatch
):
    """``depth=0`` must return matches only with no context cursor.

    Design §4.5: depth 0 returns matches only; ``depth=0`` always produces an
    empty related-context page and no context cursor.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidates = [
        _candidate(
            iri="https://example.test/Item",
            label="item",
            score=500,
            similarity=0.5,
        )
    ]
    spy = _RecallSpy([candidates])
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        spy,
    )
    service = SemanticContextQueryService(
        in_memory_session,
        _FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_FakeLineage(),
        shape_endpoint=_FakeShapes(),
    )
    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        context_limit=100,
        principal=_principal(subject_id="principal-a", project_id="project-1"),
    )
    assert len(result["primary_matches"]) == 1
    assert result["related_context"] == []
    assert result["context_page"]["next_context_cursor"] is None


# ---------------------------------------------------------------------------
# Schema contract: ``queries`` / ``query`` mutual exclusion (BC-03 / BC-04)
# ---------------------------------------------------------------------------


def test_schema_rejects_both_queries_and_query():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SemanticContextQueryRequest(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=["a"],
            query="b",
        )


def test_schema_rejects_neither_queries_nor_query():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SemanticContextQueryRequest(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
        )


def test_schema_rejects_both_cursors():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SemanticContextQueryRequest(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=["a"],
            match_cursor="some-opaque-cursor",
            context_cursor="another-opaque-cursor",
        )
