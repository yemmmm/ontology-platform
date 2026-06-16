from neo4j import Driver, GraphDatabase

from app.core.config import Settings


def create_neo4j_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def verify_neo4j(driver: Driver) -> None:
    driver.verify_connectivity()


def ensure_graph_constraints(driver: Driver) -> None:
    statements = [
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
        "CREATE INDEX entity_project_id IF NOT EXISTS FOR (e:Entity) ON (e.project_id)",
        "CREATE INDEX entity_ontology_id IF NOT EXISTS FOR (e:Entity) ON (e.ontology_id)",
        "CREATE INDEX entity_class_id IF NOT EXISTS FOR (e:Entity) ON (e.class_id)",
        "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement)
