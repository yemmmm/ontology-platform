from copy import deepcopy

import pytest
from rdflib import Graph
from rdflib.compare import to_isomorphic
from sqlalchemy import select

from app.core.config import Settings
from app.repositories import models as m
from app.services.checkpoint_data import CheckpointDataError, CheckpointDataService
from app.services.ontology_workspace import OntologyWorkspaceService


class Store:
    def __init__(self):
        self.graphs = {}
        self.fail = False

    def graph_exists(self, iri):
        return iri in self.graphs

    def export_named_graph(self, iri, format):
        return self.graphs[iri]

    def put_named_graph(self, iri, content, format):
        self.graphs[iri] = content
        if self.fail:
            raise RuntimeError("PUT response lost")

    def graph_content_hash(self, iri):
        return str(
            to_isomorphic(Graph().parse(data=self.graphs[iri], format="turtle")).graph_digest()
        )

    def drop_named_graph(self, iri):
        self.graphs.pop(iri, None)


@pytest.fixture
def source(in_memory_session):
    session = in_memory_session
    session.add(m.ProjectModel(id="project", name="Source", normalized_label="Source"))
    session.flush()
    ontology = m.OntologyModel(id="ontology", project_id="project", name="Business")
    session.add(ontology)
    session.flush()
    settings = Settings()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.add(
        m.EvidenceReferenceModel(
            id="reference",
            project_id="project",
            document_name="Interview",
            normalized_document_name="interview",
            excerpt="Approved fact",
            excerpt_hash="hash",
        )
    )
    session.add(
        m.SemanticProtectionSetModel(
            id="protection",
            project_id="project",
            name="Protected",
            allowed_grants=["internal"],
        )
    )
    session.flush()
    session.add(
        m.EvidenceAssociationModel(
            id="association",
            project_id="project",
            ontology_id="ontology",
            evidence_reference_id="reference",
            target_type="class",
            target_id="urn:business:Order",
        )
    )
    session.add(
        m.SemanticProtectionSetMemberModel(
            protection_set_id="protection",
            ontology_id="ontology",
            resource_iri="urn:business:Order",
        )
    )
    session.commit()
    store = Store()
    iri = OntologyWorkspaceService(session, settings).context("ontology")["model_graph_iri"]
    store.graphs[iri] = '<urn:business:Order> <urn:label> "Before checkpoint" .'
    return session, store, settings, iri


def test_fork_uses_saved_data_and_preserves_protection_without_suspended_evidence(source):
    session, store, settings, iri = source
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["ontology"])
    session.commit()
    store.graphs[iri] = '<urn:business:Order> <urn:label> "After checkpoint" .'
    session.get(m.EvidenceReferenceModel, "reference").excerpt = "Later edit"
    session.commit()
    result = service.fork(snapshot, name="Fork", settings=settings)
    mapping = result["identity_mapping"]
    assert result["project_id"] != "project"
    assert "Before checkpoint" in store.graphs[mapping[iri]]
    assert "After checkpoint" in store.graphs[iri]
    assert "reference" not in mapping
    assert "association" not in mapping
    assert session.get(m.EvidenceReferenceModel, "reference").excerpt == "Later edit"
    protected = session.get(m.SemanticProtectionSetModel, mapping["protection"])
    assert protected.allowed_grants == ["internal"]
    workspace = OntologyWorkspaceService(session, settings).context(mapping["ontology"])
    assert workspace["state"] == "ready"
    assert (
        workspace["ontology_id"]
        != OntologyWorkspaceService(session, settings).context("ontology")["ontology_id"]
    )
    assert session.get(m.OntologyModel, "ontology").status == "archived"


def test_corrupt_snapshot_does_not_write(source):
    session, store, settings, _ = source
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["ontology"])
    snapshot["tables"]["projects"][0]["name"] = "Tampered"
    with pytest.raises(CheckpointDataError, match="digest"):
        service.fork(snapshot, name="Fork", settings=settings)
    assert len(list(session.scalars(select(m.ProjectModel)))) == 1


def test_failed_import_cleans_only_new_graphs(source):
    session, store, settings, _ = source
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["ontology"])
    session.commit()
    before = deepcopy(store.graphs)
    store.fail = True
    with pytest.raises(RuntimeError, match="response lost"):
        service.fork(snapshot, name="Fork", settings=settings)
    assert store.graphs == before
    assert len(list(session.scalars(select(m.ProjectModel)))) == 1


def test_lost_commit_ack_keeps_committed_fork_graphs(source, monkeypatch):
    from uuid import uuid4

    session, store, settings, _ = source
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["ontology"])
    session.commit()
    target = str(uuid4())
    original_commit = session.commit

    def lost_ack():
        original_commit()
        raise OSError("commit response lost")

    monkeypatch.setattr(session, "commit", lost_ack)
    with pytest.raises(CheckpointDataError) as error:
        service.fork(snapshot, name="Fork", settings=settings, target_project_id=target)
    assert error.value.code == "fork_commit_unknown"
    assert session.get(m.ProjectModel, target) is not None
    graphs = list(
        session.scalars(
            select(m.SemanticGraphRegistryModel).where(
                m.SemanticGraphRegistryModel.semantic_owner_id != "ontology"
            )
        )
    )
    assert len(graphs) == 1
    assert all(row.graph_iri in store.graphs for row in graphs)


def test_http_capture_fork_and_source_readonly(r008_client):
    from uuid import uuid4

    env = r008_client
    client = env["client"]
    client.app.state.rdf_store = Store()
    headers = {"Authorization": "Bearer " + env["org_key"]}
    project = env["ids"]["p1"]
    created = client.post(
        f"/api/projects/{project}/ontologies", headers=headers, json={"name": "Snapshot ontology"}
    )
    assert created.status_code == 201, created.text
    ontology_id = created.json()["id"]
    capture = client.post(
        "/api/checkpoint-data/capture",
        headers=headers,
        json={"project_id": project, "ontology_ids": [ontology_id]},
    )
    assert capture.status_code == 200, capture.text
    denied = client.post(
        "/api/checkpoint-data/capture",
        headers={"Authorization": "Bearer " + env["p1_admin_key"]},
        json={"project_id": project, "ontology_ids": [ontology_id]},
    )
    assert denied.status_code == 403
    target = str(uuid4())
    fork = client.post(
        "/api/checkpoint-data/fork",
        headers=headers,
        json={"snapshot": capture.json(), "name": "Fork", "target_project_id": target},
    )
    assert fork.status_code == 200, fork.text
    assert fork.json()["project_id"] == target
    assert client.get(f"/api/projects/{project}", headers=headers).status_code == 200
    blocked = client.patch(f"/api/projects/{project}", headers=headers, json={"name": "Rewrite"})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "checkpoint_source_archived"
    with env["factory"]() as db:
        old_graph = db.get(m.OntologyModel, ontology_id).model_graph_iri
    bulk = client.post(
        "/api/semantic/datasets:load",
        headers=headers,
        json={
            "format": "trig",
            "content": f'<{old_graph}> {{ <urn:a> <urn:b> "rewrite" . }}',
        },
    )
    assert bulk.status_code == 409, bulk.text
    allowed = client.patch(f"/api/projects/{target}", headers=headers, json={"name": "Continue"})
    assert allowed.status_code == 200, allowed.text
    duplicate = client.post(
        "/api/checkpoint-data/fork",
        headers=headers,
        json={"snapshot": capture.json(), "name": "Fork", "target_project_id": target},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "fork_target_exists"


def test_multiple_ontologies_custom_shapes_and_rule_cycle(source):
    session, store, settings, _ = source
    second = m.OntologyModel(id="second", project_id="project", name="Second")
    session.add(second)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(second)
    custom = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/shapes/second/custom"
    session.add(
        m.SemanticGraphRegistryModel(
            id="custom",
            graph_iri=custom,
            category="shapes",
            semantic_owner_type="ontology",
            semantic_owner_id="second",
            mutable_by_direct_edit=True,
            managed=True,
        )
    )
    session.add(m.SemanticRuleModel(id="rule", ontology_id="second", rule_iri="urn:rule"))
    session.flush()
    session.add(
        m.SemanticRuleDefinitionModel(
            id="definition",
            semantic_rule_id="rule",
            rule_iri="urn:rule",
            name="Rule",
            language="platform_dsl",
            version="v1",
            body={"statements": []},
        )
    )
    session.flush()
    session.get(m.SemanticRuleModel, "rule").current_definition_id = "definition"
    session.commit()
    store.graphs[custom] = '<urn:Shape> <urn:label> "Custom shape" .'
    service = CheckpointDataService(session, store)
    snapshot = service.capture("project", ["second", "ontology"])
    session.commit()
    result = service.fork(snapshot, name="Multiple", settings=settings)
    mapping = result["identity_mapping"]
    assert len(result["ontology_ids"]) == 2
    assert custom not in mapping
    assert custom not in snapshot["graphs"]
    rule = session.get(m.SemanticRuleModel, mapping["rule"])
    assert rule.current_definition_id == mapping["definition"]
    assert (
        session.get(m.SemanticRuleDefinitionModel, rule.current_definition_id).semantic_rule_id
        == rule.id
    )
