import json
from typing import Any

from neo4j import Driver


def _escape_symbol(symbol: str) -> str:
    return f"`{symbol.replace('`', '``')}`"


def inspect_ontology_graph(driver: Driver, ontology_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return the metadata copied into Neo4j for consistency checks."""
    query = """
    MATCH (entity:Entity {ontology_id: $ontology_id})
    OPTIONAL MATCH (entity)-[relation]->(target:Entity {ontology_id: $ontology_id})
    RETURN collect(DISTINCT {
      id: entity.id,
      project_id: entity.project_id,
      class_id: entity.class_id,
      class_label: entity.class_label,
      labels: labels(entity)
    }) AS entities,
    collect(DISTINCT CASE WHEN relation IS NULL THEN NULL ELSE {
      id: relation.id,
      project_id: relation.project_id,
      relation_type_id: relation.relation_type_id,
      relation_type: relation.relation_type,
      neo4j_type: type(relation)
    } END) AS relations
    """
    with driver.session() as session:
        record = session.run(query, ontology_id=ontology_id).single(strict=True)
        return {
            "entities": [dict(item) for item in record["entities"] if item is not None],
            "relations": [dict(item) for item in record["relations"] if item is not None],
        }


def synchronize_class_entities(
    driver: Driver,
    ontology_id: str,
    class_id: str,
    project_id: str,
    class_label: str,
) -> int:
    """Refresh denormalized class metadata and the dynamic label on matching nodes."""
    with driver.session() as session:
        labels_record = session.run(
            """
            MATCH (entity:Entity {ontology_id: $ontology_id, class_id: $class_id})
            RETURN DISTINCT labels(entity) AS labels
            """,
            ontology_id=ontology_id,
            class_id=class_id,
        )
        old_labels = {
            label
            for record in labels_record
            for label in record["labels"]
            if label != "Entity" and label != class_label
        }
        remove_clause = "".join(f" REMOVE entity:{_escape_symbol(label)}" for label in old_labels)
        query = f"""
        MATCH (entity:Entity {{ontology_id: $ontology_id, class_id: $class_id}})
        SET entity.project_id = $project_id,
            entity.class_label = $class_label,
            entity:{_escape_symbol(class_label)}
        {remove_clause}
        RETURN count(entity) AS updated_count
        """
        record = session.run(
            query,
            ontology_id=ontology_id,
            class_id=class_id,
            project_id=project_id,
            class_label=class_label,
        ).single(strict=True)
        return record["updated_count"]


def synchronize_relation_type_edges(
    driver: Driver,
    ontology_id: str,
    relation_type_id: str,
    project_id: str,
    relation_type: str,
) -> int:
    """Refresh relationship metadata, recreating edges when their Neo4j type changed."""
    escaped_type = _escape_symbol(relation_type)
    query = f"""
    MATCH (source:Entity)-[old]->(target:Entity)
    WHERE old.ontology_id = $ontology_id AND old.relation_type_id = $relation_type_id
    CREATE (source)-[new:{escaped_type}]->(target)
    SET new = properties(old),
        new.project_id = $project_id,
        new.relation_type = $relation_type
    DELETE old
    RETURN count(new) AS updated_count
    """
    with driver.session() as session:
        record = session.run(
            query,
            ontology_id=ontology_id,
            relation_type_id=relation_type_id,
            project_id=project_id,
            relation_type=relation_type,
        ).single(strict=True)
        return record["updated_count"]


def count_graph_usage(
    driver: Driver,
    *,
    project_id: str | None = None,
    ontology_id: str | None = None,
    class_id: str | None = None,
    relation_type_id: str | None = None,
) -> int:
    query = """
    MATCH (entity:Entity)
    WHERE ($project_id IS NULL OR entity.project_id = $project_id)
      AND ($ontology_id IS NULL OR entity.ontology_id = $ontology_id)
      AND ($class_id IS NULL OR entity.class_id = $class_id)
    OPTIONAL MATCH (entity)-[relation]->()
    WHERE $relation_type_id IS NULL OR relation.relation_type_id = $relation_type_id
    RETURN CASE
      WHEN $relation_type_id IS NULL THEN count(DISTINCT entity)
      ELSE count(DISTINCT relation)
    END AS usage_count
    """
    with driver.session() as session:
        record = session.run(
            query,
            project_id=project_id,
            ontology_id=ontology_id,
            class_id=class_id,
            relation_type_id=relation_type_id,
        ).single(strict=True)
        return record["usage_count"]


def _decode_properties(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("properties"), dict):
        return data["properties"]
    raw = data.get("properties_json")
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _encode_graph_values(values: dict[str, Any]) -> dict[str, Any]:
    encoded = dict(values)
    properties = encoded.pop("properties", {})
    encoded["properties_json"] = json.dumps(properties, ensure_ascii=False, sort_keys=True)
    return encoded


def _entity_from_node(node: Any) -> dict[str, Any]:
    data = dict(node)
    return {
        "id": data["id"],
        "project_id": data["project_id"],
        "ontology_id": data["ontology_id"],
        "ontology_version_id": data.get("ontology_version_id"),
        "class_id": data["class_id"],
        "class_label": data["class_label"],
        "name": data["name"],
        "aliases": data.get("aliases", []),
        "properties": _decode_properties(data),
    }


def _relation_from_record(record: Any) -> dict[str, Any]:
    relation = dict(record["relation"])
    return _relation_from_values(relation, record["source_id"], record["target_id"])


def _relation_from_values(relation: dict[str, Any], source_id: str, target_id: str) -> dict[str, Any]:
    return {
        "id": relation["id"],
        "project_id": relation["project_id"],
        "ontology_id": relation["ontology_id"],
        "ontology_version_id": relation.get("ontology_version_id"),
        "relation_type_id": relation["relation_type_id"],
        "relation_type": relation["relation_type"],
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "properties": _decode_properties(relation),
    }


def create_entity_node(driver: Driver, class_label: str, values: dict[str, Any]) -> dict[str, Any]:
    label = _escape_symbol(class_label)
    encoded_values = _encode_graph_values(values)
    query = f"""
    CREATE (entity:Entity:{label})
    SET entity = $values
    RETURN entity
    """
    with driver.session() as session:
        record = session.run(query, values=encoded_values).single(strict=True)
        return _entity_from_node(record["entity"])


def update_entity_node(
    driver: Driver,
    entity_id: str,
    project_id: str,
    ontology_id: str,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    query = """
    MATCH (entity:Entity {id: $entity_id, project_id: $project_id, ontology_id: $ontology_id})
    SET entity += $values
    RETURN entity
    """
    encoded_values = _encode_graph_values(values) if "properties" in values else values
    with driver.session() as session:
        record = session.run(
            query,
            entity_id=entity_id,
            project_id=project_id,
            ontology_id=ontology_id,
            values=encoded_values,
        ).single()
        if record is None:
            return None
        return _entity_from_node(record["entity"])


def get_entity_node(
    driver: Driver,
    entity_id: str,
    project_id: str | None = None,
    ontology_id: str | None = None,
) -> dict[str, Any] | None:
    query = """
    MATCH (entity:Entity {id: $entity_id})
    WHERE ($project_id IS NULL OR entity.project_id = $project_id)
      AND ($ontology_id IS NULL OR entity.ontology_id = $ontology_id)
    RETURN entity
    """
    with driver.session() as session:
        record = session.run(
            query,
            entity_id=entity_id,
            project_id=project_id,
            ontology_id=ontology_id,
        ).single()
        if record is None:
            return None
        return _entity_from_node(record["entity"])


def list_entity_nodes(
    driver: Driver,
    project_id: str,
    ontology_id: str,
    class_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    query = """
    MATCH (entity:Entity {project_id: $project_id, ontology_id: $ontology_id})
    WHERE ($class_id IS NULL OR entity.class_id = $class_id)
    RETURN entity
    ORDER BY entity.name ASC
    LIMIT $limit
    """
    with driver.session() as session:
        records = session.run(
            query,
            project_id=project_id,
            ontology_id=ontology_id,
            class_id=class_id,
            limit=limit,
        )
        return [_entity_from_node(record["entity"]) for record in records]


def search_entity_nodes(
    driver: Driver,
    project_id: str,
    ontology_id: str,
    query_text: str,
    class_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    query = """
    MATCH (entity:Entity {project_id: $project_id, ontology_id: $ontology_id})
    WHERE ($class_id IS NULL OR entity.class_id = $class_id)
      AND (
        $query_text = ""
        OR toLower(entity.name) CONTAINS $query_text
        OR any(alias IN coalesce(entity.aliases, []) WHERE toLower(alias) CONTAINS $query_text)
        OR toLower(coalesce(entity.properties_json, "")) CONTAINS $query_text
      )
    RETURN entity
    ORDER BY entity.name ASC
    LIMIT $limit
    """
    with driver.session() as session:
        records = session.run(
            query,
            project_id=project_id,
            ontology_id=ontology_id,
            query_text=query_text.lower().strip(),
            class_id=class_id,
            limit=limit,
        )
        return [_entity_from_node(record["entity"]) for record in records]


def delete_entity_node(
    driver: Driver,
    entity_id: str,
    project_id: str,
    ontology_id: str,
) -> bool:
    query = """
    MATCH (entity:Entity {id: $entity_id, project_id: $project_id, ontology_id: $ontology_id})
    WITH entity, count { (entity)--() } AS relation_count
    WHERE relation_count = 0
    DELETE entity
    RETURN count(entity) AS deleted_count
    """
    with driver.session() as session:
        record = session.run(
            query,
            entity_id=entity_id,
            project_id=project_id,
            ontology_id=ontology_id,
        ).single()
        return bool(record and record["deleted_count"])


def create_relation_edge(
    driver: Driver,
    relation_type: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    rel_type = _escape_symbol(relation_type)
    encoded_values = _encode_graph_values(values)
    query = f"""
    MATCH (source:Entity {{
      id: $source_entity_id,
      project_id: $project_id,
      ontology_id: $ontology_id
    }})
    MATCH (target:Entity {{
      id: $target_entity_id,
      project_id: $project_id,
      ontology_id: $ontology_id
    }})
    CREATE (source)-[relation:{rel_type}]->(target)
    SET relation = $values
    RETURN relation, source.id AS source_id, target.id AS target_id
    """
    with driver.session() as session:
        record = session.run(
            query,
            source_entity_id=values["source_entity_id"],
            target_entity_id=values["target_entity_id"],
            project_id=values["project_id"],
            ontology_id=values["ontology_id"],
            values=encoded_values,
        ).single(strict=True)
        return _relation_from_record(record)


def delete_relation_edge(
    driver: Driver,
    relation_id: str,
    project_id: str,
    ontology_id: str,
) -> bool:
    query = """
    MATCH ()-[relation {id: $relation_id, project_id: $project_id, ontology_id: $ontology_id}]->()
    DELETE relation
    RETURN count(relation) AS deleted_count
    """
    with driver.session() as session:
        record = session.run(
            query,
            relation_id=relation_id,
            project_id=project_id,
            ontology_id=ontology_id,
        ).single()
        return bool(record and record["deleted_count"])


def list_relation_edges(
    driver: Driver,
    project_id: str,
    ontology_id: str,
    entity_id: str | None,
    relation_type_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    query = """
    MATCH (source:Entity {project_id: $project_id, ontology_id: $ontology_id})
      -[relation]->
      (target:Entity {project_id: $project_id, ontology_id: $ontology_id})
    WHERE ($entity_id IS NULL OR source.id = $entity_id OR target.id = $entity_id)
      AND ($relation_type_id IS NULL OR relation.relation_type_id = $relation_type_id)
    RETURN relation, source.id AS source_id, target.id AS target_id
    ORDER BY relation.id ASC
    LIMIT $limit
    """
    with driver.session() as session:
        records = session.run(
            query,
            project_id=project_id,
            ontology_id=ontology_id,
            entity_id=entity_id,
            relation_type_id=relation_type_id,
            limit=limit,
        )
        return [_relation_from_record(record) for record in records]


def list_entity_relation_edges(
    driver: Driver,
    project_id: str,
    ontology_id: str,
    entity_id: str,
    direction: str,
    relation_type_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    patterns = {
        "outgoing": "(source)-[relation]->(target)",
        "incoming": "(source)<-[relation]-(target)",
        "both": "(source)-[relation]-(target)",
    }
    pattern = patterns[direction]
    query = f"""
    MATCH (source:Entity {{id: $entity_id, project_id: $project_id, ontology_id: $ontology_id}})
    MATCH {pattern}
    WHERE target:Entity
      AND target.project_id = $project_id
      AND target.ontology_id = $ontology_id
      AND ($relation_type_ids IS NULL OR relation.relation_type_id IN $relation_type_ids)
    RETURN relation, startNode(relation).id AS source_id, endNode(relation).id AS target_id
    ORDER BY relation.id ASC
    LIMIT $limit
    """
    with driver.session() as session:
        records = session.run(
            query,
            entity_id=entity_id,
            project_id=project_id,
            ontology_id=ontology_id,
            relation_type_ids=relation_type_ids,
            limit=limit,
        )
        return [_relation_from_record(record) for record in records]


def find_related_entity_nodes(
    driver: Driver,
    project_id: str,
    ontology_id: str,
    entity_id: str,
    depth: int,
    direction: str,
    relation_type_ids: list[str] | None,
    target_class_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    patterns = {
        "outgoing": f"(origin)-[relations*1..{depth}]->(neighbor:Entity)",
        "incoming": f"(origin)<-[relations*1..{depth}]-(neighbor:Entity)",
        "both": f"(origin)-[relations*1..{depth}]-(neighbor:Entity)",
    }
    pattern = patterns[direction]
    query = f"""
    MATCH (origin:Entity {{id: $entity_id, project_id: $project_id, ontology_id: $ontology_id}})
    MATCH path = {pattern}
    WHERE neighbor.project_id = $project_id
      AND neighbor.ontology_id = $ontology_id
      AND origin.id <> neighbor.id
      AND ($target_class_ids IS NULL OR neighbor.class_id IN $target_class_ids)
      AND (
        $relation_type_ids IS NULL
        OR all(relation IN relationships(path) WHERE relation.relation_type_id IN $relation_type_ids)
      )
    WITH neighbor, relationships(path) AS path_relations
    UNWIND path_relations AS relation
    WITH neighbor, relation
    MATCH (source:Entity)-[relation]->(target:Entity)
    WITH neighbor, collect(DISTINCT {{
      relation: properties(relation),
      source_id: source.id,
      target_id: target.id
    }}) AS relation_records
    RETURN neighbor, relation_records
    ORDER BY neighbor.name ASC
    LIMIT $limit
    """
    with driver.session() as session:
        records = session.run(
            query,
            entity_id=entity_id,
            project_id=project_id,
            ontology_id=ontology_id,
            relation_type_ids=relation_type_ids,
            target_class_ids=target_class_ids,
            limit=limit,
        )
        results = []
        for record in records:
            results.append(
                {
                    "entity": _entity_from_node(record["neighbor"]),
                    "relations": [
                        _relation_from_values(item["relation"], item["source_id"], item["target_id"])
                        for item in record["relation_records"]
                    ],
                }
            )
        return results
