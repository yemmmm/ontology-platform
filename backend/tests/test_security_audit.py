from sqlalchemy import select

from app.repositories.models import SecurityAuditEventModel


def test_auth_failure_and_actor_spoof_are_persisted_without_payload(r008_client):
    client = r008_client["client"]
    fake = "sk_admin_" + "A" * 32
    client.get("/api/projects", headers={"Authorization": f"Bearer {fake}"})
    response = client.patch(
        f"/api/projects/{r008_client['ids']['p1']}/brief",
        json={"fields": {}, "actor": "forged-user"},
        headers={"Authorization": f"Bearer {r008_client['p1_admin_key']}"},
    )
    assert response.status_code in {200, 422}
    with r008_client["factory"]() as session:
        events = list(session.scalars(select(SecurityAuditEventModel)))
    assert {event.event_type for event in events} >= {
        "authentication_failure",
        "actor_spoof_attempt",
    }
    serialized = repr([event.details for event in events])
    assert fake not in serialized
    assert "forged-user" not in serialized
