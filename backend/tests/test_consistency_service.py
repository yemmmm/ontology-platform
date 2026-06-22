from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories import graph as graph_repository
from app.services import consistency


def ontology_schema():
    return SimpleNamespace(
        id="ontology",
        project_id="project",
        classes=[SimpleNamespace(id="person", normalized_label="Person")],
        relation_types=[SimpleNamespace(id="knows", normalized_type="KNOWS")],
    )


def test_audit_reports_stale_and_orphaned_graph_metadata() -> None:
    graph = {
        "entities": [
            {
                "id": "alice",
                "project_id": "old-project",
                "class_id": "person",
                "class_label": "OldPerson",
                "labels": ["Entity", "OldPerson"],
            },
            {
                "id": "orphan",
                "project_id": "project",
                "class_id": "missing",
                "class_label": "Missing",
                "labels": ["Entity", "Missing"],
            },
        ],
        "relations": [
            {
                "id": "relation",
                "project_id": "project",
                "relation_type_id": "knows",
                "relation_type": "OLD_KNOWS",
                "neo4j_type": "OLD_KNOWS",
            }
        ],
    }

    with (
        patch.object(consistency, "get_ontology_schema", return_value=ontology_schema()),
        patch.object(graph_repository, "inspect_ontology_graph", return_value=graph),
    ):
        result = consistency.audit_ontology_graph(MagicMock(), MagicMock(), "ontology")

    assert not result["consistent"]
    assert {issue["kind"] for issue in result["issues"]} == {
        "stale_entity_metadata",
        "orphan_entity_class",
        "stale_relation_metadata",
    }


def test_repair_refuses_to_guess_how_to_handle_orphaned_data() -> None:
    audit = {"issues": [{"kind": "orphan_entity_class", "graph_id": "entity"}]}
    with (
        patch.object(consistency, "get_ontology_schema", return_value=ontology_schema()),
        patch.object(consistency, "audit_ontology_graph", return_value=audit),
        pytest.raises(HTTPException, match="orphan data") as exc_info,
    ):
        consistency.repair_ontology_graph(MagicMock(), MagicMock(), "ontology")

    assert exc_info.value.status_code == 400


def test_escape_symbol_doubles_neo4j_backticks() -> None:
    assert graph_repository._escape_symbol("unsafe`label") == "`unsafe``label`"
