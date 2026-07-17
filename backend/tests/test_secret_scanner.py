import pytest
from sqlalchemy import select

from app.repositories.models import ProjectModel
from app.security.secrets import SecretDetected, scan_domain_payload


@pytest.mark.parametrize(
    "value",
    [
        "api_key and password are credential requirements",
        {"authorization": "<TOKEN>"},
        {"api_key": "${API_KEY}"},
        "Bearer <TOKEN>",
        "REDACTED",
    ],
)
def test_documentation_and_placeholders_are_allowed(value):
    scan_domain_payload(value)


@pytest.mark.parametrize(
    "value",
    [
        "sk_admin_" + "A" * 32,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456789",
        "AKIA" + "A" * 16,
        "Bearer abcdefghijklmnopqrstuvwxyz012345",
        {"password": "real-password-value"},
    ],
)
def test_high_confidence_secrets_are_rejected(value):
    with pytest.raises(SecretDetected):
        scan_domain_payload(value)


def test_http_write_rejects_secret_before_persistence(r008_client):
    secret = "sk_admin_" + "A" * 32
    response = r008_client["client"].post(
        "/api/projects",
        headers={"Authorization": f"Bearer {r008_client['org_key']}"},
        json={"name": "Must not persist", "description": secret},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "secret_in_payload"
    with r008_client["factory"]() as session:
        assert (
            session.scalar(select(ProjectModel).where(ProjectModel.name == "Must not persist"))
            is None
        )
