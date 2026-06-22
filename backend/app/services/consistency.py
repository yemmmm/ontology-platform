from typing import Any

from neo4j import Driver
from sqlalchemy.orm import Session

from app.repositories import graph as graph_repo
from app.services.metadata import bad_request, get_ontology, get_ontology_schema


def audit_ontology_graph(
    session: Session,
    driver: Driver,
    ontology_id: str,
) -> dict[str, Any]:
    ontology = get_ontology_schema(session, ontology_id)
    graph = graph_repo.inspect_ontology_graph(driver, ontology_id)
    classes = {item.id: item for item in ontology.classes}
    relation_types = {item.id: item for item in ontology.relation_types}
    issues: list[dict[str, str]] = []

    for entity in graph["entities"]:
        class_ = classes.get(entity["class_id"])
        if class_ is None:
            issues.append({"kind": "orphan_entity_class", "graph_id": entity["id"]})
            continue
        labels = set(entity["labels"]) - {"Entity"}
        if (
            entity["project_id"] != ontology.project_id
            or entity["class_label"] != class_.normalized_label
            or labels != {class_.normalized_label}
        ):
            issues.append({"kind": "stale_entity_metadata", "graph_id": entity["id"]})

    for relation in graph["relations"]:
        relation_type = relation_types.get(relation["relation_type_id"])
        if relation_type is None:
            issues.append({"kind": "orphan_relation_type", "graph_id": relation["id"]})
            continue
        if (
            relation["project_id"] != ontology.project_id
            or relation["relation_type"] != relation_type.normalized_type
            or relation["neo4j_type"] != relation_type.normalized_type
        ):
            issues.append({"kind": "stale_relation_metadata", "graph_id": relation["id"]})

    return {
        "ontology_id": ontology_id,
        "consistent": not issues,
        "entity_count": len(graph["entities"]),
        "relation_count": len(graph["relations"]),
        "issues": issues,
    }


def repair_ontology_graph(
    session: Session,
    driver: Driver,
    ontology_id: str,
) -> dict[str, Any]:
    ontology = get_ontology_schema(session, ontology_id)
    before = audit_ontology_graph(session, driver, ontology_id)
    orphan_kinds = {"orphan_entity_class", "orphan_relation_type"}
    if any(issue["kind"] in orphan_kinds for issue in before["issues"]):
        raise bad_request(
            "Graph contains orphan data; restore its PostgreSQL schema or delete the graph data first"
        )

    updated_entities = sum(
        graph_repo.synchronize_class_entities(
            driver,
            ontology.id,
            class_.id,
            ontology.project_id,
            class_.normalized_label,
        )
        for class_ in ontology.classes
    )
    updated_relations = sum(
        graph_repo.synchronize_relation_type_edges(
            driver,
            ontology.id,
            relation_type.id,
            ontology.project_id,
            relation_type.normalized_type,
        )
        for relation_type in ontology.relation_types
    )
    return {
        **audit_ontology_graph(session, driver, ontology_id),
        "updated_entities": updated_entities,
        "updated_relations": updated_relations,
    }


def ensure_metadata_not_in_use(
    driver: Driver,
    resource: str,
    **filters: str,
) -> None:
    if graph_repo.count_graph_usage(driver, **filters):
        raise bad_request(f"Cannot delete {resource} while Neo4j graph data still references it")


def synchronize_class(session: Session, driver: Driver, class_id: str) -> int:
    from app.services.metadata import get_class

    class_ = get_class(session, class_id)
    ontology = get_ontology(session, class_.ontology_id)
    return graph_repo.synchronize_class_entities(
        driver, ontology.id, class_.id, ontology.project_id, class_.normalized_label
    )


def synchronize_relation_type(session: Session, driver: Driver, relation_type_id: str) -> int:
    from app.services.metadata import get_relation_type

    relation_type = get_relation_type(session, relation_type_id)
    ontology = get_ontology(session, relation_type.ontology_id)
    return graph_repo.synchronize_relation_type_edges(
        driver,
        ontology.id,
        relation_type.id,
        ontology.project_id,
        relation_type.normalized_type,
    )
