"""Dedicated R1.2-004 cursor codec tests (SC and PG cursor-binding cases)."""

from __future__ import annotations

import time

import pytest

from app.security.auth import AuthPrincipal
from app.services.semantic_context_cursor import (
    CURSOR_KIND_CONTEXT,
    CURSOR_KIND_MATCH,
    ContextCursorCodec,
    ContextCursorInvalid,
    ContextCursorMismatch,
    ContextSnapshotChanged,
    CursorBinding,
    CursorPayload,
    binding_digest,
    make_binding,
)


def _codec(secret: str = "stable-secret", lifetime: int = 600) -> ContextCursorCodec:
    return ContextCursorCodec(
        secret=secret,
        lifetime_seconds=lifetime,
        stable_secret=bool(secret),
    )


def _principal(subject_id: str = "principal-a", project_id: str | None = "project-1") -> AuthPrincipal:
    return AuthPrincipal(
        subject_type="api_key",
        subject_id=subject_id,
        actor=f"key:{subject_id}",
        scopes=frozenset({"read"}),
        project_id=project_id,
        auth_method="bearer",
    )


def _binding(
    *,
    principal: AuthPrincipal | None = None,
    original_queries=("topic",),
    normalized_queries=("topic",),
    workspace_versions=(("ontology-1", "v1"),),
    source_signatures=(("ontology-1", "sig-1"),),
    limit: int = 20,
    context_limit: int = 100,
    depth: int = 1,
) -> CursorBinding:
    return make_binding(
        principal=principal or _principal(),
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        original_queries=list(original_queries),
        normalized_queries=list(normalized_queries),
        resource_types=["concept"],
        assertion_types=["asserted"],
        search_mode="hybrid",
        depth=depth,
        limit=limit,
        context_limit=context_limit,
        workspace_versions=list(workspace_versions),
        source_signatures=list(source_signatures),
    )


def _fill_payload(
    codec: ContextCursorCodec,
    binding: CursorBinding,
    kind: str = CURSOR_KIND_MATCH,
) -> CursorPayload:
    return CursorPayload(
        kind=kind,
        binding_digest=binding_digest(binding),
        workspace_versions=binding.workspace_versions,
        source_signatures=binding.source_signatures,
        resume_key=("ontology-1", "match-2"),
        root_match_ids=("match-1",) if kind == CURSOR_KIND_CONTEXT else (),
        issued_at=int(time.time()),
    )


def test_cursor_round_trip_preserves_resume_key_and_kind():
    codec = _codec()
    binding = _binding()
    token = codec.encode(_fill_payload(codec, binding))
    decoded = codec.decode(token, binding=binding, expected_kind=CURSOR_KIND_MATCH)
    assert decoded.kind == CURSOR_KIND_MATCH
    assert decoded.resume_key == ("ontology-1", "match-2")


def test_cursor_tamper_returns_invalid():
    codec = _codec()
    binding = _binding()
    token = codec.encode(_fill_payload(codec, binding))
    body, signature = token.split(".", 1)
    flipped = body[:-1] + ("A" if body[-1] != "A" else "B")
    with pytest.raises(ContextCursorInvalid):
        codec.decode(f"{flipped}.{signature}", binding=binding, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_wrong_kind_returns_invalid():
    codec = _codec()
    binding = _binding()
    match_token = codec.encode(_fill_payload(codec, binding, kind=CURSOR_KIND_MATCH))
    with pytest.raises(ContextCursorInvalid):
        codec.decode(match_token, binding=binding, expected_kind=CURSOR_KIND_CONTEXT)


def test_cursor_expired_returns_invalid():
    codec = _codec(lifetime=1)
    binding = _binding()
    payload = CursorPayload(
        kind=CURSOR_KIND_MATCH,
        binding_digest=binding_digest(binding),
        workspace_versions=binding.workspace_versions,
        source_signatures=binding.source_signatures,
        resume_key=("ontology-1", "match-2"),
        root_match_ids=(),
        issued_at=int(time.time()) - 10,
    )
    token = codec.encode(payload)
    with pytest.raises(ContextCursorInvalid):
        codec.decode(token, binding=binding, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_principal_mismatch_returns_mismatch():
    codec = _codec()
    principal_a = _principal(subject_id="principal-a")
    principal_b = _principal(subject_id="principal-b")
    binding_a = _binding(principal=principal_a)
    binding_b = _binding(principal=principal_b)
    token = codec.encode(_fill_payload(codec, binding_a))
    with pytest.raises(ContextCursorMismatch):
        codec.decode(token, binding=binding_b, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_query_change_returns_mismatch():
    codec = _codec()
    binding_original = _binding(original_queries=("topic",), normalized_queries=("topic",))
    binding_changed = _binding(
        original_queries=("topic", "other"),
        normalized_queries=("topic", "other"),
    )
    token = codec.encode(_fill_payload(codec, binding_original))
    with pytest.raises(ContextCursorMismatch):
        codec.decode(token, binding=binding_changed, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_workspace_version_drift_returns_snapshot_changed():
    codec = _codec()
    binding_v1 = _binding(workspace_versions=(("ontology-1", "v1"),))
    binding_v2 = _binding(workspace_versions=(("ontology-1", "v2"),))
    token = codec.encode(_fill_payload(codec, binding_v1))
    with pytest.raises(ContextSnapshotChanged):
        codec.decode(token, binding=binding_v2, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_ephemeral_secret_rotation_invalidates():
    codec_first = ContextCursorCodec(secret="", lifetime_seconds=600, stable_secret=False)
    codec_second = ContextCursorCodec(secret="", lifetime_seconds=600, stable_secret=False)
    binding = _binding()
    token = codec_first.encode(_fill_payload(codec_first, binding))
    with pytest.raises(ContextCursorInvalid):
        codec_second.decode(token, binding=binding, expected_kind=CURSOR_KIND_MATCH)


def test_cursor_payload_excludes_raw_query_text():
    codec = _codec()
    binding = _binding(
        original_queries=("secret-query-value",),
        normalized_queries=("secret-query-value",),
    )
    token = codec.encode(_fill_payload(codec, binding))
    assert "secret-query-value" not in token
