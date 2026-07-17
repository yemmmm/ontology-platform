from uuid import uuid4

from app.api.schemas import OntologyCreate
from app.repositories.models import SemanticGraphSetModel
from app.security.http import HTTP_ROUTE_POLICIES, PUBLIC_PATHS, _collect_resource_ids
from app.services.ontology_crud import create_ontology


def _bearer(value):
    return {"Authorization": f"Bearer {value}"}


def test_project_list_and_explicit_foreign_project_are_isolated(r008_client):
    client = r008_client["client"]
    ids = r008_client["ids"]
    headers = _bearer(r008_client["p1_read_key"])
    listed = client.get("/api/projects", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [ids["p1"]]
    denied = client.get(f"/api/projects/{ids['p2']}", headers=headers)
    assert denied.status_code == 403


def test_opaque_foreign_ontology_is_not_enumerable(r008_client):
    with r008_client["factory"]() as session:
        ontology = create_ontology(
            session,
            r008_client["ids"]["p2"],
            OntologyCreate(name="P2 ontology"),
        )
        ontology_id = ontology.id
    response = r008_client["client"].get(
        f"/api/ontologies/{ontology_id}",
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert response.status_code == 404


def test_read_scope_cannot_write(r008_client):
    response = r008_client["client"].patch(
        f"/api/projects/{r008_client['ids']['p1']}/brief",
        json={"fields": {}},
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert response.status_code == 403


def test_every_protected_openapi_operation_has_an_explicit_policy(r008_client):
    schema = r008_client["client"].app.openapi()
    operations = {
        (method.upper(), path)
        for path, item in schema["paths"].items()
        for method in item
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert operations - PUBLIC_PATHS <= set(HTTP_ROUTE_POLICIES)
    assert HTTP_ROUTE_POLICIES[("GET", "/api/api-keys")] == "admin"
    assert HTTP_ROUTE_POLICIES[("GET", "/api/api-keys/{key_id}")] == "admin"


def test_project_model_cannot_load_unscoped_dataset(r008_client):
    class StoreMustNotBeCalled:
        def __getattr__(self, name):
            raise AssertionError(f"dataset authorization reached RDF store method {name}")

    r008_client["client"].app.state.rdf_store = StoreMustNotBeCalled()
    response = r008_client["client"].post(
        "/api/semantic/datasets:load",
        headers=_bearer(r008_client["p1_model_key"]),
        json={
            "format": "trig",
            "content": '<urn:unowned> { <urn:s> <urn:p> "must-not-reach-store" . }',
            "base_iri": "urn:r008:",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_scope"


def test_project_model_denies_ad_hoc_graph_sets_and_allows_owned_ontology_scope(r008_client):
    with r008_client["factory"]() as session:
        ontology = create_ontology(
            session,
            r008_client["ids"]["p1"],
            OntologyCreate(name="P1 graph authorization"),
        )
        graph_iri = f"http://ontology-platform.local/semantic/graph/data/{ontology.id}"
        ad_hoc = SemanticGraphSetModel(
            id=str(uuid4()),
            name="unowned",
            scope_type="ontology_version",
            scope_id="not-a-platform-ontology",
            status="active",
            source_signature="unowned",
        )
        session.add(ad_hoc)
        session.commit()
        ontology_id = ontology.id
        ad_hoc_id = ad_hoc.id

    client = r008_client["client"]
    headers = _bearer(r008_client["p1_model_key"])
    denied_create = client.post(
        "/api/semantic/graph-sets",
        headers=headers,
        json={
            "name": "unowned create",
            "scope_type": "ontology_version",
            "scope_id": "not-a-platform-ontology",
            "members": [{"graph_iri": graph_iri, "role": "asserted_data"}],
        },
    )
    assert denied_create.status_code == 403
    assert client.get(f"/api/semantic/graph-sets/{ad_hoc_id}", headers=headers).status_code == 403

    allowed = client.post(
        "/api/semantic/graph-sets",
        headers=headers,
        json={
            "name": "owned create",
            "scope_type": "ontology",
            "scope_id": ontology_id,
            "members": [{"graph_iri": graph_iri, "role": "asserted_data"}],
        },
    )
    assert allowed.status_code == 200, allowed.text
    assert (
        client.get(f"/api/semantic/graph-sets/{allowed.json()['id']}", headers=headers).status_code
        == 200
    )
    assert (
        client.get(
            "/api/semantic/graph-sets",
            params={"scope_type": "ontology"},
            headers=headers,
        ).status_code
        == 200
    )
    graphs = client.get("/api/semantic/graphs", headers=headers)
    assert graphs.status_code == 200
    assert all(item["owner_id"] == ontology_id for item in graphs.json()["graphs"])
    assert sum(graphs.json()["summary"]["graph_counts_by_category"].values()) == len(
        graphs.json()["graphs"]
    )


def test_client_idempotency_labels_are_not_treated_as_server_resources():
    resources: list[tuple[str, str]] = []

    _collect_resource_ids({"client_batch_id": "client-selected-label"}, resources)

    assert resources == []
