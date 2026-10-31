from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "lab.sqlite")) as value:
        yield value


def model(client, model_id="flash", enabled=True):
    response = client.post(
        "/admin/models", json={"id": model_id, "name": model_id, "enabled": enabled}
    )
    assert response.status_code == 201
    return response.json()


def key(client, quota=2, allowed=None):
    response = client.post(
        "/admin/keys",
        json={"name": "test-app", "allowed_models": allowed or ["flash"], "quota": quota},
    )
    assert response.status_code == 201
    return response.json()


def call(client, credential, request_id="r1", model_id="flash", prompt="hello"):
    return client.post(
        "/calls",
        headers={"Authorization": f"Bearer {credential['token']}"},
        json={"request_id": request_id, "model_id": model_id, "prompt": prompt},
    )


def test_success_charges_once_and_records_the_real_result(client):
    model(client)
    credential = key(client)
    response = call(client, credential)
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["reply"] == "flash: hello"
    assert receipt["charged_units"] == 1
    assert receipt["remaining_quota"] == 1
    assert receipt["replayed"] is False
    rows = client.get("/admin/calls").json()
    assert len(rows) == 1
    assert rows[0]["key_id"] == credential["id"]
    assert rows[0]["reply"] == receipt["reply"]
    assert client.get(f"/admin/keys/{credential['id']}").json()["remaining_quota"] == 1


def test_same_request_replays_after_quota_is_exhausted_and_model_disabled(client):
    model(client)
    credential = key(client, quota=1)
    first = call(client, credential).json()
    client.patch("/admin/models/flash", json={"enabled": False})
    repeated = call(client, credential)
    assert repeated.status_code == 200
    assert repeated.json() == {**first, "charged_units": 0, "replayed": True}
    assert len(client.get("/admin/calls").json()) == 1


@pytest.mark.parametrize("change", [{"prompt": "different"}, {"model_id": "other"}])
def test_request_id_cannot_be_reused_for_different_content(client, change):
    model(client)
    credential = key(client)
    assert call(client, credential).status_code == 200
    rejected = call(client, credential, **change)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "request_id_conflict"
    assert len(client.get("/admin/calls").json()) == 1
    assert client.get(f"/admin/keys/{credential['id']}").json()["remaining_quota"] == 1


def test_prompt_whitespace_is_preserved_and_counts_as_different_content(client):
    model(client)
    credential = key(client)
    assert call(client, credential).json()["reply"] == "flash: hello"
    assert call(client, credential, prompt=" hello").status_code == 409
    assert call(client, credential, request_id="r2", prompt=" hello").json()["reply"] == (
        "flash:  hello"
    )


@pytest.mark.parametrize(
    "case, status, reason",
    [
        ("unknown_model", 404, "model_not_found"),
        ("not_granted", 403, "model_not_allowed"),
        ("model_disabled", 409, "model_disabled"),
        ("key_disabled", 403, "key_disabled"),
        ("no_quota", 429, "quota_exhausted"),
    ],
)
def test_rejections_never_charge_or_create_success_records(client, case, status, reason):
    model(client)
    model(client, "other")
    credential = key(client, quota=0 if case == "no_quota" else 2)
    target = "flash"
    if case == "unknown_model":
        target = "missing"
    elif case == "not_granted":
        target = "other"
    elif case == "model_disabled":
        client.patch("/admin/models/flash", json={"enabled": False})
    elif case == "key_disabled":
        client.patch(f"/admin/keys/{credential['id']}", json={"enabled": False})
    rejected = call(client, credential, model_id=target)
    assert rejected.status_code == status
    assert rejected.json()["detail"] == reason
    assert client.get("/admin/calls").json() == []
    assert client.get(f"/admin/keys/{credential['id']}").json()["remaining_quota"] == (
        0 if case == "no_quota" else 2
    )


@pytest.mark.parametrize("authorization", [None, "Bearer invalid", "Basic invalid"])
def test_missing_or_unknown_credential_is_rejected(client, authorization):
    model(client)
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.post(
        "/calls",
        headers=headers,
        json={"request_id": "r1", "model_id": "flash", "prompt": "hello"},
    )
    assert response.status_code == 401
    assert client.get("/admin/calls").json() == []


def test_disabling_a_key_also_blocks_replay_and_reenabling_preserves_quota(client):
    model(client)
    credential = key(client)
    assert call(client, credential).status_code == 200
    url = f"/admin/keys/{credential['id']}"
    assert client.patch(url, json={"enabled": False}).status_code == 200
    assert call(client, credential).status_code == 403
    assert client.patch(url, json={"enabled": True}).json()["remaining_quota"] == 1
    assert call(client, credential).json()["charged_units"] == 0


def test_model_reenable_preserves_existing_grants(client):
    model(client, enabled=False)
    credential = key(client)
    assert call(client, credential).status_code == 409
    client.patch("/admin/models/flash", json={"enabled": True})
    assert call(client, credential).status_code == 200


def test_models_share_one_keys_quota_but_keys_have_independent_balances(client):
    model(client)
    model(client, "reasoner")
    first = key(client, quota=2, allowed=["flash", "reasoner"])
    second = key(client, quota=1)
    assert call(client, first).json()["remaining_quota"] == 1
    assert call(client, first, request_id="r2", model_id="reasoner").json()["remaining_quota"] == 0
    assert call(client, first, request_id="r3").status_code == 429
    assert call(client, second).json()["remaining_quota"] == 0
    assert len(client.get("/admin/calls").json()) == 3


@pytest.mark.parametrize("quota", [-1, 1.5, True, "2"])
def test_quota_must_be_a_nonnegative_integer(client, quota):
    model(client)
    response = client.post(
        "/admin/keys", json={"name": "bad", "quota": quota, "allowed_models": ["flash"]}
    )
    assert response.status_code == 422


def test_duplicate_models_and_unknown_or_empty_grants_are_rejected(client):
    model(client)
    assert (
        client.post("/admin/models", json={"id": "flash", "name": "duplicate"}).status_code == 409
    )
    for grants, status in [(["missing"], 400), ([], 422)]:
        response = client.post(
            "/admin/keys", json={"name": "bad", "quota": 1, "allowed_models": grants}
        )
        assert response.status_code == status
    assert client.get("/admin/keys").json() == []


def test_management_reads_hide_credential_and_openapi_is_available(client):
    model(client)
    credential = key(client)
    assert "token" not in client.get("/admin/keys").text
    assert credential["token"] not in client.get(f"/admin/keys/{credential['id']}").text
    assert client.get("/admin/models").json()[0]["id"] == "flash"
    assert "/calls" in client.get("/openapi.json").json()["paths"]
    assert client.get("/health").json() == {"status": "ok"}


def test_database_survives_app_recreation(tmp_path):
    path = tmp_path / "persistent.sqlite"
    with TestClient(create_app(path)) as first:
        model(first)
        credential = key(first)
        original = call(first, credential).json()
    with TestClient(create_app(path)) as restarted:
        assert call(restarted, credential).json() == {
            **original,
            "charged_units": 0,
            "replayed": True,
        }
        assert restarted.get(f"/admin/keys/{credential['id']}").json()["remaining_quota"] == 1
        assert len(restarted.get("/admin/calls").json()) == 1


@pytest.mark.parametrize("same_request", [False, True])
def test_parallel_requests_cannot_overdraw_or_double_charge(client, same_request):
    model(client)
    credential = key(client, quota=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda i: call(client, credential, request_id="r1" if same_request else f"r{i}"),
                range(4),
            )
        )
    assert sorted(response.status_code for response in responses) == (
        [200] * 4 if same_request else [200, 429, 429, 429]
    )
    assert sum(response.json().get("charged_units", 0) for response in responses) == 1
    assert len(client.get("/admin/calls").json()) == 1
    assert client.get(f"/admin/keys/{credential['id']}").json()["remaining_quota"] == 0


def test_cli_serves_a_real_http_round_trip_and_stops_cleanly(tmp_path):
    log_path = tmp_path / "server.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "app.py"),
                "--port",
                "0",
                "--db",
                str(tmp_path / "cli.sqlite"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 10
            address = None
            while time.monotonic() < deadline:
                address = re.search(r"http://127\.0\.0\.1:(\d+)", log_path.read_text())
                if address or process.poll() is not None:
                    break
                time.sleep(0.05)
            assert address is not None, log_path.read_text()
            with httpx.Client(base_url=address.group(0), timeout=5) as client:
                assert client.get("/health").json() == {"status": "ok"}
                assert client.get("/docs").status_code == 200
                assert "/calls" in client.get("/openapi.json").json()["paths"]
                model(client)
                credential = key(client, quota=1)
                assert call(client, credential).json()["charged_units"] == 1
                assert call(client, credential).json()["charged_units"] == 0
                assert call(client, credential, request_id="r2").status_code == 429
                assert len(client.get("/admin/calls").json()) == 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
