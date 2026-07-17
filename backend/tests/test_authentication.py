import json
import stat

import pytest
from sqlalchemy import create_engine

from app.cli.bootstrap_auth import provision_operator
from app.core.config import Settings
from app.repositories.postgres import Base


def test_http_hard_cut_and_health_exception(r008_client):
    client = r008_client["client"]
    assert client.get("/api/health").status_code == 200
    denied = client.get("/api/projects")
    assert denied.status_code == 401
    assert denied.json()["detail"]["code"] == "invalid_authentication"
    assert denied.headers["www-authenticate"] == "Bearer"


def test_login_session_csrf_and_logout(r008_client):
    client = r008_client["client"]
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200, login.text
    assert "ontology_session" in login.headers["set-cookie"]
    assert "HttpOnly" in login.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 200
    denied = client.post("/api/projects", json={"name": "csrf denied"})
    assert denied.status_code == 403
    csrf = client.cookies["ontology_csrf"]
    created = client.post(
        "/api/projects",
        json={"name": "csrf accepted"},
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": csrf},
    )
    assert created.status_code == 201, created.text
    logout = client.post(
        "/api/auth/logout",
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_operator_bootstrap_writes_once_with_private_permissions(tmp_path):
    database_path = tmp_path / "bootstrap.sqlite"
    settings = Settings(database_url=f"sqlite:///{database_path}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    output = tmp_path / "private" / "operator.json"
    created = provision_operator(
        username="operator",
        password="a sufficiently long operator password",
        output_path=output,
        settings=settings,
    )
    assert created == output.resolve()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    credentials = json.loads(output.read_text(encoding="utf-8"))
    assert credentials["username"] == "operator"
    assert credentials["password"] == "a sufficiently long operator password"
    assert credentials["api_key"].startswith("sk_admin_")
    assert credentials["api_key_id"]
    with pytest.raises(FileExistsError):
        provision_operator(
            username="operator",
            password="a sufficiently long operator password",
            output_path=output,
            settings=settings,
        )
