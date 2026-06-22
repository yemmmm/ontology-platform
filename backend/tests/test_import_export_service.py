from types import SimpleNamespace
from unittest.mock import call, patch

from app.api.schemas import OntologyImportPayload
from app.services import import_export


def test_import_ontology_remaps_cross_references() -> None:
    payload = OntologyImportPayload(
        ontology={"name": "Company"},
        classes=[
            {
                "id": "old-person",
                "name": "Person",
                "properties": [{"name": "status", "type": "enum", "enum_values": ["active"]}],
            },
            {
                "id": "old-manager",
                "name": "Manager",
                "parent_class_ids": ["old-person"],
            },
        ],
        relation_types=[
            {
                "id": "old-manages",
                "name": "manages",
                "source_class_id": "old-manager",
                "target_class_id": "old-person",
            }
        ],
        entities=[
            {"id": "old-alice", "class_id": "old-manager", "name": "Alice"},
            {"id": "old-bob", "class_id": "old-person", "name": "Bob"},
        ],
        relations=[
            {
                "relation_type_id": "old-manages",
                "source_entity_id": "old-alice",
                "target_entity_id": "old-bob",
            }
        ],
    )

    with (
        patch.object(
            import_export.metadata_service,
            "create_ontology",
            return_value=SimpleNamespace(id="new-ontology"),
        ),
        patch.object(
            import_export.metadata_service,
            "create_class",
            side_effect=[SimpleNamespace(id="new-person"), SimpleNamespace(id="new-manager")],
        ) as create_class,
        patch.object(import_export.metadata_service, "create_property") as create_property,
        patch.object(
            import_export.metadata_service,
            "create_relation_type",
            return_value=SimpleNamespace(id="new-manages"),
        ) as create_relation_type,
        patch.object(
            import_export.graph_service,
            "create_entity",
            side_effect=[{"id": "new-alice"}, {"id": "new-bob"}],
        ) as create_entity,
        patch.object(import_export.graph_service, "create_relation") as create_relation,
        patch.object(import_export, "export_ontology", return_value={"exported": True}),
    ):
        result = import_export.import_ontology(object(), object(), "project", payload)

    assert result == {"exported": True}
    assert create_class.call_args_list[1].args[2].parent_class_ids == ["new-person"]
    assert create_property.call_args.args[2].enum_values == ["active"]
    relation_payload = create_relation_type.call_args.args[2]
    assert relation_payload.source_class_id == "new-manager"
    assert relation_payload.target_class_id == "new-person"
    assert [item.args[3].class_id for item in create_entity.call_args_list] == [
        "new-manager",
        "new-person",
    ]
    imported_relation = create_relation.call_args.args[3]
    assert imported_relation.relation_type_id == "new-manages"
    assert imported_relation.source_entity_id == "new-alice"
    assert imported_relation.target_entity_id == "new-bob"


def test_export_ontology_collects_metadata_and_graph_data() -> None:
    ontology = SimpleNamespace(
        id="ontology",
        project_id="project",
        current_version_id=None,
        name="Company",
        description=None,
        status="draft",
        external_mappings={},
        created_at=None,
        updated_at=None,
        classes=[],
        relation_types=[],
    )

    with (
        patch.object(import_export.metadata_service, "get_ontology_schema", return_value=ontology),
        patch.object(import_export.graph_service, "list_entities", return_value=[{"id": "entity"}]) as entities,
        patch.object(import_export.graph_service, "list_relations", return_value=[{"id": "relation"}]) as relations,
    ):
        result = import_export.export_ontology(object(), object(), "ontology")

    assert result["ontology"]["name"] == "Company"
    assert result["entities"] == [{"id": "entity"}]
    assert result["relations"] == [{"id": "relation"}]
    assert entities.call_args == call(
        entities.call_args.args[0],
        entities.call_args.args[1],
        "ontology",
        class_id=None,
        limit=100,
    )
    assert relations.call_args.kwargs == {
        "entity_id": None,
        "relation_type_id": None,
        "limit": 100,
    }
