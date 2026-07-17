from app.repositories.models import ApiKeyModel
from app.security.auth import resolve_api_key


def _bearer(value):
    return {"Authorization": f"Bearer {value}"}


def test_plaintext_is_returned_once_and_hash_only_is_stored(r008_client):
    client = r008_client["client"]
    response = client.post(
        "/api/api-keys",
        json={
            "name": "new-reader",
            "project_id": r008_client["ids"]["p1"],
            "scopes": ["read"],
        },
        headers=_bearer(r008_client["org_key"]),
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["plaintext_key"].startswith("sk_read_")
    listed = client.get("/api/api-keys", headers=_bearer(r008_client["org_key"])).json()
    listed_record = next(item for item in listed if item["id"] == payload["id"])
    assert "plaintext_key" not in listed_record
    assert "key_hash" not in listed_record
    with r008_client["factory"]() as session:
        record = session.get(ApiKeyModel, payload["id"])
        assert record.key_hash != payload["plaintext_key"]
        assert resolve_api_key(session, payload["plaintext_key"]) is not None


def test_revoke_is_idempotent_and_immediately_invalidates_key(r008_client):
    client = r008_client["client"]
    key_id = r008_client["ids"]["p1_read_key_id"]
    headers = _bearer(r008_client["p1_admin_key"])
    first = client.post(f"/api/api-keys/{key_id}:revoke", headers=headers)
    second = client.post(f"/api/api-keys/{key_id}:revoke", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["revoked_at"] == second.json()["revoked_at"]
    denied = client.get("/api/projects", headers=_bearer(r008_client["p1_read_key"]))
    assert denied.status_code == 401


def test_read_and_model_keys_cannot_enumerate_api_key_metadata(r008_client):
    client = r008_client["client"]
    cases = (
        (r008_client["p1_read_key"], r008_client["ids"]["p1_read_key_id"]),
        (r008_client["p1_model_key"], r008_client["ids"]["p1_model_key_id"]),
    )

    for plaintext, own_key_id in cases:
        headers = _bearer(plaintext)
        assert client.get("/api/api-keys", headers=headers).status_code == 403
        assert client.get(f"/api/api-keys/{own_key_id}", headers=headers).status_code == 403


def test_project_admin_sees_only_same_project_api_keys(r008_client):
    client = r008_client["client"]
    headers = _bearer(r008_client["p1_admin_key"])

    response = client.get("/api/api-keys", headers=headers)
    assert response.status_code == 200
    visible_ids = {item["id"] for item in response.json()}
    assert visible_ids == {
        r008_client["ids"]["p1_read_key_id"],
        r008_client["ids"]["p1_model_key_id"],
        r008_client["ids"]["p1_admin_key_id"],
    }
    assert (
        client.get(
            f"/api/api-keys/{r008_client['ids']['p1_read_key_id']}",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/api-keys/{r008_client['ids']['org_key_id']}",
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/api-keys/{r008_client['ids']['p2_read_key_id']}",
            headers=headers,
        ).status_code
        == 404
    )
