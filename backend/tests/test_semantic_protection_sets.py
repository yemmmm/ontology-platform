"""Protection Set management surface tests (R3.0-004 §10.1)."""

from __future__ import annotations

from sqlalchemy import select

from app.repositories.models import SecurityAuditEventModel


def _bearer(value):
    return {"Authorization": f"Bearer {value}"}


def _create(client, headers, project_id, **overrides):
    payload = {
        "name": "cost-visibility",
        "description": "spare-part cost module",
        "allowed_grants": ["cost-visibility"],
    }
    payload.update(overrides)
    return client.post(
        f"/api/projects/{project_id}/protection-sets",
        json=payload,
        headers=headers,
    )


def test_full_management_lifecycle(r008_client):
    client = r008_client["client"]
    p1 = r008_client["ids"]["p1"]
    model_headers = _bearer(r008_client["p1_model_key"])

    created = _create(client, model_headers, p1)
    assert created.status_code == 201, created.text
    set_id = created.json()["id"]
    assert created.json()["allowed_grants"] == ["cost-visibility"]
    assert created.json()["member_count"] == 0

    listed = client.get(f"/api/projects/{p1}/protection-sets", headers=model_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [set_id]

    added = client.post(
        f"/api/protection-sets/{set_id}/members",
        json={"members": [{"resource_iri": "https://example.test/entity/cost-1"}]},
        headers=model_headers,
    )
    assert added.status_code == 200, added.text
    assert added.json()["members_added"] == 1
    # idempotent duplicate add
    again = client.post(
        f"/api/protection-sets/{set_id}/members",
        json={"members": [{"resource_iri": "https://example.test/entity/cost-1"}]},
        headers=model_headers,
    )
    assert again.json()["members_added"] == 0

    detail = client.get(f"/api/protection-sets/{set_id}", headers=model_headers)
    assert detail.status_code == 200
    assert detail.json()["member_total"] == 1
    assert detail.json()["members"][0]["resource_iri"] == "https://example.test/entity/cost-1"

    updated = client.patch(
        f"/api/protection-sets/{set_id}",
        json={"description": "updated", "allowed_grants": ["cost-visibility", "audit"]},
        headers=model_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["allowed_grants"] == ["cost-visibility", "audit"]

    # non-empty set cannot be deleted
    blocked = client.delete(f"/api/protection-sets/{set_id}", headers=model_headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "protection_set_not_empty"

    removed = client.request(
        "DELETE",
        f"/api/protection-sets/{set_id}/members",
        json={"resource_iris": ["https://example.test/entity/cost-1"]},
        headers=model_headers,
    )
    assert removed.status_code == 200
    assert removed.json()["members_removed"] == 1

    assert client.delete(f"/api/protection-sets/{set_id}", headers=model_headers).status_code == 204


def test_duplicate_name_in_same_project_conflicts(r008_client):
    client = r008_client["client"]
    p1 = r008_client["ids"]["p1"]
    headers = _bearer(r008_client["p1_model_key"])
    assert _create(client, headers, p1).status_code == 201
    duplicate = _create(client, headers, p1)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "protection_set_name_conflict"
    # the same name in another project is allowed (org key owns both planes)
    assert (
        _create(client, _bearer(r008_client["org_key"]), r008_client["ids"]["p2"]).status_code
        == 201
    )


def test_invalid_grants_and_members_are_rejected(r008_client):
    client = r008_client["client"]
    p1 = r008_client["ids"]["p1"]
    headers = _bearer(r008_client["p1_model_key"])
    empty_grant = _create(client, headers, p1, allowed_grants=[""])
    assert empty_grant.status_code == 422
    too_many = _create(
        client, headers, p1, allowed_grants=[f"g{i}" for i in range(65)]
    )
    assert too_many.status_code == 422
    bad_members = _create(
        client, headers, p1, members=[{"resource_iri": "   "}]
    )
    assert bad_members.status_code == 422


def test_scope_and_project_boundary_enforcement(r008_client):
    client = r008_client["client"]
    p1 = r008_client["ids"]["p1"]
    # read scope cannot manage or read the control plane
    read_headers = _bearer(r008_client["p1_read_key"])
    assert (
        client.get(f"/api/projects/{p1}/protection-sets", headers=read_headers).status_code
        == 403
    )
    assert _create(client, read_headers, p1).status_code == 403

    # p1 keys cannot touch p2's project plane
    model_headers = _bearer(r008_client["p1_model_key"])
    assert _create(client, model_headers, r008_client["ids"]["p2"]).status_code == 403

    # p1 keys cannot read a p2-owned set by id
    org_headers = _bearer(r008_client["org_key"])
    p2_set = _create(client, org_headers, r008_client["ids"]["p2"]).json()["id"]
    assert (
        client.get(f"/api/protection-sets/{p2_set}", headers=model_headers).status_code == 404
    )


def test_management_writes_audit_events(r008_client):
    client = r008_client["client"]
    p1 = r008_client["ids"]["p1"]
    headers = _bearer(r008_client["p1_model_key"])
    set_id = _create(client, headers, p1).json()["id"]
    client.post(
        f"/api/protection-sets/{set_id}/members",
        json={"members": [{"resource_iri": "https://example.test/entity/cost-1"}]},
        headers=headers,
    )
    client.request(
        "DELETE",
        f"/api/protection-sets/{set_id}/members",
        json={"resource_iris": ["https://example.test/entity/cost-1"]},
        headers=headers,
    )
    client.delete(f"/api/protection-sets/{set_id}", headers=headers)

    with r008_client["factory"]() as session:
        events = session.scalars(
            select(SecurityAuditEventModel).where(
                SecurityAuditEventModel.resource_id == set_id
            )
        ).all()
        event_types = {event.event_type for event in events}
    assert {
        "semantic_protection_set_created",
        "semantic_protection_set_members_added",
        "semantic_protection_set_members_removed",
        "semantic_protection_set_deleted",
    } <= event_types


def test_patch_api_keys_manages_semantic_grants(r008_client):
    client = r008_client["client"]
    key_id = r008_client["ids"]["p1_read_key_id"]
    org_headers = _bearer(r008_client["org_key"])

    patched = client.patch(
        f"/api/api-keys/{key_id}",
        json={"semantic_grants": ["cost-visibility"]},
        headers=org_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["semantic_grants"] == ["cost-visibility"]

    # grant management is admin-only
    model_headers = _bearer(r008_client["p1_model_key"])
    denied = client.patch(
        f"/api/api-keys/{key_id}",
        json={"semantic_grants": ["cost-visibility"]},
        headers=model_headers,
    )
    assert denied.status_code == 403

    invalid = client.patch(
        f"/api/api-keys/{key_id}",
        json={"semantic_grants": [""]},
        headers=org_headers,
    )
    assert invalid.status_code == 422
    too_many = client.patch(
        f"/api/api-keys/{key_id}",
        json={"semantic_grants": [f"g{i}" for i in range(65)]},
        headers=org_headers,
    )
    assert too_many.status_code == 422

    with r008_client["factory"]() as session:
        events = session.scalars(
            select(SecurityAuditEventModel).where(
                SecurityAuditEventModel.resource_id == key_id,
                SecurityAuditEventModel.event_type == "api_key_updated",
            )
        ).all()
    assert events
    assert any("grants_added" in (event.details or {}) for event in events)
