from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.api.schemas import (
    ClassCreate,
    EntityCreate,
    OntologyCreate,
    ProjectCreate,
    PropertyDefCreate,
    RelationCreate,
    RelationTypeCreate,
)
from app.core.config import Settings
from app.repositories.models import ProjectModel
from app.repositories.neo4j import create_neo4j_driver, ensure_graph_constraints
from app.repositories.postgres import create_session_factory
from app.services import graph as graph_service
from app.services.embedding import EmbeddingClient
from app.services import metadata as metadata_service


PROJECT_NAME = "Demo - Smart Manufacturing Knowledge Graph"
ONTOLOGY_NAME = "Smart Manufacturing Ontology"


@dataclass(frozen=True)
class ClassSpec:
    name: str
    description: str
    aliases: list[str]
    properties: list[dict[str, Any]]


@dataclass(frozen=True)
class RelationTypeSpec:
    name: str
    source: str
    target: str
    description: str
    inverse_name: str | None = None


def prop(
    name: str,
    type_: str,
    description: str,
    *,
    required: bool = False,
    multi_valued: bool = False,
    enum_values: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "description": description,
        "required": required,
        "multi_valued": multi_valued,
        "enum_values": enum_values or [],
    }


CLASS_SPECS = [
    ClassSpec(
        name="Organization",
        description="Manufacturers, suppliers, labs, and service partners.",
        aliases=["Company", "Partner"],
        properties=[
            prop("industry", "string", "Primary industry segment.", required=True),
            prop("region", "string", "Operating region.", required=True),
            prop("tier", "enum", "Supply chain tier.", enum_values=["OEM", "Tier 1", "Tier 2", "Lab"]),
        ],
    ),
    ClassSpec(
        name="Person",
        description="People who own, operate, or analyze manufacturing activities.",
        aliases=["Expert", "Operator"],
        properties=[
            prop("role", "string", "Business or technical role.", required=True),
            prop("seniority", "enum", "Seniority band.", enum_values=["Lead", "Senior", "Mid"]),
            prop("skills", "string", "Important skills.", multi_valued=True),
        ],
    ),
    ClassSpec(
        name="Product",
        description="Manufactured products and product lines.",
        aliases=["SKU", "Equipment"],
        properties=[
            prop("category", "string", "Product category.", required=True),
            prop("lifecycle_stage", "enum", "Current lifecycle stage.", enum_values=["Design", "Pilot", "Mass Production"]),
            prop("annual_volume", "number", "Expected annual production volume."),
        ],
    ),
    ClassSpec(
        name="Component",
        description="Parts and subassemblies used by products.",
        aliases=["Part", "Module"],
        properties=[
            prop("material", "string", "Main material.", required=True),
            prop("criticality", "enum", "Operational criticality.", enum_values=["High", "Medium", "Low"]),
            prop("lead_time_days", "number", "Typical procurement lead time."),
        ],
    ),
    ClassSpec(
        name="Dataset",
        description="Operational, inspection, and quality datasets.",
        aliases=["Data Asset"],
        properties=[
            prop("source_system", "string", "Originating system.", required=True),
            prop("record_count", "number", "Approximate record count."),
            prop("freshness", "enum", "Refresh cadence.", enum_values=["Streaming", "Daily", "Weekly"]),
        ],
    ),
    ClassSpec(
        name="Model",
        description="Analytics and machine learning models used in production.",
        aliases=["AI Model"],
        properties=[
            prop("model_type", "string", "Model family.", required=True),
            prop("metric", "string", "Primary evaluation metric."),
            prop("score", "number", "Latest evaluation score."),
        ],
    ),
    ClassSpec(
        name="Facility",
        description="Plants, lines, labs, and warehouses.",
        aliases=["Site", "Plant"],
        properties=[
            prop("location", "string", "Facility location.", required=True),
            prop("capacity", "number", "Nominal weekly output capacity."),
            prop("certifications", "string", "Certifications.", multi_valued=True),
        ],
    ),
    ClassSpec(
        name="Process",
        description="Manufacturing and quality processes.",
        aliases=["Operation"],
        properties=[
            prop("process_type", "string", "Process category.", required=True),
            prop("cycle_time_minutes", "number", "Average cycle time."),
            prop("automation_level", "enum", "Automation level.", enum_values=["Manual", "Semi-auto", "Automated"]),
        ],
    ),
]


RELATION_TYPE_SPECS = [
    RelationTypeSpec("Employs", "Organization", "Person", "Organization employs or contracts a person.", "employed_by"),
    RelationTypeSpec("Owns Facility", "Organization", "Facility", "Organization owns or operates a facility.", "owned_by"),
    RelationTypeSpec("Manufactures", "Organization", "Product", "Organization manufactures a product.", "manufactured_by"),
    RelationTypeSpec("Contains Component", "Product", "Component", "Product contains a component.", "used_in_product"),
    RelationTypeSpec("Supplies Component", "Organization", "Component", "Organization supplies a component.", "supplied_by"),
    RelationTypeSpec("Uses Dataset", "Model", "Dataset", "Model uses a dataset.", "used_by_model"),
    RelationTypeSpec("Deployed In Product", "Model", "Product", "Model is deployed in or supports a product.", "uses_model"),
    RelationTypeSpec("Runs Process", "Facility", "Process", "Facility runs a process.", "run_at"),
    RelationTypeSpec("Supports Process", "Person", "Process", "Person supports a process.", "supported_by"),
    RelationTypeSpec("Develops Model", "Organization", "Model", "Organization develops or maintains a model.", "developed_by"),
]


ENTITY_SPECS: dict[str, list[dict[str, Any]]] = {
    "Organization": [
        {"name": "Atlas Robotics", "properties": {"industry": "Industrial robotics", "region": "APAC", "tier": "OEM"}},
        {"name": "Nova Precision", "properties": {"industry": "CNC machining", "region": "East China", "tier": "Tier 1"}},
        {"name": "Helio Sensors", "properties": {"industry": "Industrial sensors", "region": "Singapore", "tier": "Tier 2"}},
        {"name": "Quartz Battery Systems", "properties": {"industry": "Battery modules", "region": "Korea", "tier": "Tier 1"}},
        {"name": "Meridian AI Lab", "properties": {"industry": "Applied AI", "region": "Singapore", "tier": "Lab"}},
        {"name": "Orion Logistics", "properties": {"industry": "Manufacturing logistics", "region": "SEA", "tier": "Tier 2"}},
        {"name": "Pioneer Drives", "properties": {"industry": "Servo drives", "region": "Japan", "tier": "Tier 1"}},
        {"name": "Vertex Vision", "properties": {"industry": "Machine vision", "region": "Taiwan", "tier": "Tier 2"}},
    ],
    "Person": [
        {"name": "Maya Chen", "properties": {"role": "Manufacturing lead", "seniority": "Lead", "skills": ["line balancing", "MES"]}},
        {"name": "Ethan Park", "properties": {"role": "Quality engineer", "seniority": "Senior", "skills": ["SPC", "vision inspection"]}},
        {"name": "Priya Raman", "properties": {"role": "Data scientist", "seniority": "Senior", "skills": ["forecasting", "anomaly detection"]}},
        {"name": "Luis Ortega", "properties": {"role": "Maintenance engineer", "seniority": "Mid", "skills": ["PLC", "predictive maintenance"]}},
        {"name": "Nina Zhao", "properties": {"role": "Supply planner", "seniority": "Senior", "skills": ["MRP", "risk analysis"]}},
        {"name": "Oliver Tan", "properties": {"role": "Process engineer", "seniority": "Mid", "skills": ["SMT", "DOE"]}},
        {"name": "Sara Kim", "properties": {"role": "Product manager", "seniority": "Lead", "skills": ["roadmap", "customer feedback"]}},
        {"name": "Wei Lin", "properties": {"role": "Automation architect", "seniority": "Lead", "skills": ["robotics", "controls"]}},
    ],
    "Product": [
        {"name": "AR-200 Assembly Robot", "properties": {"category": "Robot arm", "lifecycle_stage": "Mass Production", "annual_volume": 1200}},
        {"name": "VX-Inspect Station", "properties": {"category": "Inspection station", "lifecycle_stage": "Pilot", "annual_volume": 300}},
        {"name": "QB-48 Battery Pack", "properties": {"category": "Battery system", "lifecycle_stage": "Mass Production", "annual_volume": 20000}},
        {"name": "PD-S900 Servo Drive", "properties": {"category": "Drive controller", "lifecycle_stage": "Mass Production", "annual_volume": 8500}},
        {"name": "Atlas Mobile Base", "properties": {"category": "AMR platform", "lifecycle_stage": "Design", "annual_volume": 500}},
        {"name": "Thermal Control Unit", "properties": {"category": "Thermal module", "lifecycle_stage": "Pilot", "annual_volume": 1500}},
        {"name": "Edge Gateway X1", "properties": {"category": "Industrial gateway", "lifecycle_stage": "Mass Production", "annual_volume": 6000}},
        {"name": "Smart Torque Tool", "properties": {"category": "Assembly tool", "lifecycle_stage": "Pilot", "annual_volume": 900}},
    ],
    "Component": [
        {"name": "Harmonic Reducer HR-17", "properties": {"material": "Alloy steel", "criticality": "High", "lead_time_days": 45}},
        {"name": "Vision Sensor VS-4K", "properties": {"material": "CMOS assembly", "criticality": "High", "lead_time_days": 30}},
        {"name": "Battery Cell BC-2170", "properties": {"material": "Lithium-ion", "criticality": "High", "lead_time_days": 60}},
        {"name": "Servo PCB SP-12", "properties": {"material": "FR4 copper", "criticality": "Medium", "lead_time_days": 21}},
        {"name": "Torque Transducer TT-80", "properties": {"material": "Stainless steel", "criticality": "Medium", "lead_time_days": 28}},
        {"name": "Thermal Pad TP-6", "properties": {"material": "Silicone", "criticality": "Low", "lead_time_days": 12}},
        {"name": "Lidar Module LM-16", "properties": {"material": "Optical assembly", "criticality": "High", "lead_time_days": 38}},
        {"name": "Edge Compute Board ECB-2", "properties": {"material": "PCB assembly", "criticality": "Medium", "lead_time_days": 25}},
    ],
    "Dataset": [
        {"name": "SMT Defect Images 2026Q1", "properties": {"source_system": "Vision archive", "record_count": 180000, "freshness": "Daily"}},
        {"name": "Robot Joint Telemetry", "properties": {"source_system": "IIoT historian", "record_count": 5200000, "freshness": "Streaming"}},
        {"name": "Supplier OTIF Records", "properties": {"source_system": "ERP", "record_count": 94000, "freshness": "Daily"}},
        {"name": "Battery Aging Curves", "properties": {"source_system": "Lab LIMS", "record_count": 42000, "freshness": "Weekly"}},
        {"name": "Torque Trace Archive", "properties": {"source_system": "MES", "record_count": 870000, "freshness": "Streaming"}},
        {"name": "Warranty Claim Notes", "properties": {"source_system": "CRM", "record_count": 22000, "freshness": "Daily"}},
    ],
    "Model": [
        {"name": "Vision Defect Classifier", "properties": {"model_type": "CNN", "metric": "F1", "score": 0.94}},
        {"name": "Joint Failure Predictor", "properties": {"model_type": "Gradient boosting", "metric": "AUC", "score": 0.89}},
        {"name": "Supplier Risk Scorer", "properties": {"model_type": "Graph model", "metric": "Precision@20", "score": 0.81}},
        {"name": "Battery Life Estimator", "properties": {"model_type": "Survival model", "metric": "MAE", "score": 0.12}},
        {"name": "Torque Anomaly Detector", "properties": {"model_type": "Autoencoder", "metric": "Recall", "score": 0.91}},
    ],
    "Facility": [
        {"name": "Suzhou Assembly Plant", "properties": {"location": "Suzhou", "capacity": 4500, "certifications": ["ISO 9001", "IATF 16949"]}},
        {"name": "Singapore AI Lab", "properties": {"location": "Singapore", "capacity": 120, "certifications": ["ISO 27001"]}},
        {"name": "Busan Battery Line", "properties": {"location": "Busan", "capacity": 9000, "certifications": ["ISO 14001", "UL"]}},
        {"name": "Nagoya Drive Plant", "properties": {"location": "Nagoya", "capacity": 3000, "certifications": ["ISO 9001"]}},
    ],
    "Process": [
        {"name": "Final Assembly", "properties": {"process_type": "Assembly", "cycle_time_minutes": 18, "automation_level": "Semi-auto"}},
        {"name": "Optical Inspection", "properties": {"process_type": "Quality", "cycle_time_minutes": 4, "automation_level": "Automated"}},
        {"name": "Battery Formation", "properties": {"process_type": "Electrochemical", "cycle_time_minutes": 720, "automation_level": "Automated"}},
    ],
}


def cleanup_existing_demo(session: Any, driver: Any) -> None:
    existing = session.scalars(select(ProjectModel).where(ProjectModel.name == PROJECT_NAME)).first()
    if existing is None:
        return

    with driver.session() as neo4j_session:
        neo4j_session.run(
            """
            MATCH (entity:Entity {project_id: $project_id})-[relation]-()
            DELETE relation
            """,
            project_id=existing.id,
        )
        neo4j_session.run(
            """
            MATCH (entity:Entity {project_id: $project_id})
            DELETE entity
            """,
            project_id=existing.id,
        )

    session.delete(existing)
    session.commit()


def create_classes(session: Any, ontology_id: str) -> dict[str, str]:
    class_ids: dict[str, str] = {}
    for spec in CLASS_SPECS:
        class_ = metadata_service.create_class(
            session,
            ontology_id,
            ClassCreate(name=spec.name, description=spec.description, aliases=spec.aliases),
        )
        class_ids[spec.name] = class_.id
        for property_spec in spec.properties:
            metadata_service.create_property(
                session,
                class_.id,
                PropertyDefCreate(**property_spec),
            )
    return class_ids


def create_relation_types(
    session: Any,
    ontology_id: str,
    class_ids: dict[str, str],
) -> dict[str, str]:
    relation_type_ids: dict[str, str] = {}
    for spec in RELATION_TYPE_SPECS:
        relation_type = metadata_service.create_relation_type(
            session,
            ontology_id,
            RelationTypeCreate(
                name=spec.name,
                description=spec.description,
                source_class_id=class_ids[spec.source],
                target_class_id=class_ids[spec.target],
                inverse_name=spec.inverse_name,
            ),
        )
        relation_type_ids[spec.name] = relation_type.id
    return relation_type_ids


def create_entities(
    session: Any,
    driver: Any,
    ontology_id: str,
    class_ids: dict[str, str],
    embedding_client: EmbeddingClient,
) -> dict[str, str]:
    entity_ids: dict[str, str] = {}
    for class_name, entities in ENTITY_SPECS.items():
        for entity_spec in entities:
            entity = graph_service.create_entity(
                session,
                driver,
                ontology_id,
                EntityCreate(
                    class_id=class_ids[class_name],
                    name=entity_spec["name"],
                    aliases=entity_spec.get("aliases", []),
                    properties=entity_spec["properties"],
                ),
                embedding_client,
            )
            entity_ids[entity["name"]] = entity["id"]
    return entity_ids


def relation(
    relation_type: str,
    source: str,
    target: str,
    **properties: Any,
) -> tuple[str, str, str, dict[str, Any]]:
    return relation_type, source, target, properties


def create_relations(
    session: Any,
    driver: Any,
    ontology_id: str,
    relation_type_ids: dict[str, str],
    entity_ids: dict[str, str],
) -> int:
    relation_specs = [
        relation("Employs", "Atlas Robotics", "Maya Chen", since="2021-03-01"),
        relation("Employs", "Nova Precision", "Oliver Tan", since="2022-07-01"),
        relation("Employs", "Helio Sensors", "Ethan Park", since="2020-11-01"),
        relation("Employs", "Meridian AI Lab", "Priya Raman", since="2023-02-01"),
        relation("Employs", "Orion Logistics", "Nina Zhao", since="2021-09-01"),
        relation("Employs", "Pioneer Drives", "Wei Lin", since="2019-05-01"),
        relation("Employs", "Quartz Battery Systems", "Luis Ortega", since="2022-01-01"),
        relation("Employs", "Atlas Robotics", "Sara Kim", since="2020-04-01"),
        relation("Owns Facility", "Atlas Robotics", "Suzhou Assembly Plant", ownership="operator"),
        relation("Owns Facility", "Meridian AI Lab", "Singapore AI Lab", ownership="operator"),
        relation("Owns Facility", "Quartz Battery Systems", "Busan Battery Line", ownership="owner"),
        relation("Owns Facility", "Pioneer Drives", "Nagoya Drive Plant", ownership="owner"),
        relation("Manufactures", "Atlas Robotics", "AR-200 Assembly Robot", status="active"),
        relation("Manufactures", "Atlas Robotics", "Atlas Mobile Base", status="pilot"),
        relation("Manufactures", "Vertex Vision", "VX-Inspect Station", status="pilot"),
        relation("Manufactures", "Quartz Battery Systems", "QB-48 Battery Pack", status="active"),
        relation("Manufactures", "Pioneer Drives", "PD-S900 Servo Drive", status="active"),
        relation("Manufactures", "Nova Precision", "Smart Torque Tool", status="pilot"),
        relation("Contains Component", "AR-200 Assembly Robot", "Harmonic Reducer HR-17", quantity=6),
        relation("Contains Component", "AR-200 Assembly Robot", "Servo PCB SP-12", quantity=4),
        relation("Contains Component", "VX-Inspect Station", "Vision Sensor VS-4K", quantity=2),
        relation("Contains Component", "QB-48 Battery Pack", "Battery Cell BC-2170", quantity=96),
        relation("Contains Component", "PD-S900 Servo Drive", "Servo PCB SP-12", quantity=1),
        relation("Contains Component", "Thermal Control Unit", "Thermal Pad TP-6", quantity=8),
        relation("Contains Component", "Atlas Mobile Base", "Lidar Module LM-16", quantity=1),
        relation("Contains Component", "Edge Gateway X1", "Edge Compute Board ECB-2", quantity=1),
        relation("Contains Component", "Smart Torque Tool", "Torque Transducer TT-80", quantity=1),
        relation("Supplies Component", "Helio Sensors", "Vision Sensor VS-4K", risk="medium"),
        relation("Supplies Component", "Quartz Battery Systems", "Battery Cell BC-2170", risk="high"),
        relation("Supplies Component", "Pioneer Drives", "Servo PCB SP-12", risk="medium"),
        relation("Supplies Component", "Nova Precision", "Harmonic Reducer HR-17", risk="medium"),
        relation("Supplies Component", "Vertex Vision", "Edge Compute Board ECB-2", risk="low"),
        relation("Develops Model", "Meridian AI Lab", "Vision Defect Classifier", owner_team="quality-ai"),
        relation("Develops Model", "Meridian AI Lab", "Joint Failure Predictor", owner_team="reliability-ai"),
        relation("Develops Model", "Meridian AI Lab", "Supplier Risk Scorer", owner_team="planning-ai"),
        relation("Develops Model", "Quartz Battery Systems", "Battery Life Estimator", owner_team="battery-ai"),
        relation("Develops Model", "Nova Precision", "Torque Anomaly Detector", owner_team="process-ai"),
        relation("Uses Dataset", "Vision Defect Classifier", "SMT Defect Images 2026Q1", split="train"),
        relation("Uses Dataset", "Joint Failure Predictor", "Robot Joint Telemetry", split="train"),
        relation("Uses Dataset", "Supplier Risk Scorer", "Supplier OTIF Records", split="train"),
        relation("Uses Dataset", "Battery Life Estimator", "Battery Aging Curves", split="train"),
        relation("Uses Dataset", "Torque Anomaly Detector", "Torque Trace Archive", split="train"),
        relation("Uses Dataset", "Supplier Risk Scorer", "Warranty Claim Notes", split="features"),
        relation("Deployed In Product", "Vision Defect Classifier", "VX-Inspect Station", environment="edge"),
        relation("Deployed In Product", "Joint Failure Predictor", "AR-200 Assembly Robot", environment="cloud"),
        relation("Deployed In Product", "Battery Life Estimator", "QB-48 Battery Pack", environment="cloud"),
        relation("Deployed In Product", "Torque Anomaly Detector", "Smart Torque Tool", environment="edge"),
        relation("Runs Process", "Suzhou Assembly Plant", "Final Assembly", shift="A/B"),
        relation("Runs Process", "Suzhou Assembly Plant", "Optical Inspection", shift="A/B"),
        relation("Runs Process", "Busan Battery Line", "Battery Formation", shift="24x7"),
        relation("Supports Process", "Maya Chen", "Final Assembly", responsibility="owner"),
        relation("Supports Process", "Ethan Park", "Optical Inspection", responsibility="quality"),
        relation("Supports Process", "Luis Ortega", "Battery Formation", responsibility="maintenance"),
    ]

    for relation_type, source, target, properties in relation_specs:
        graph_service.create_relation(
            session,
            driver,
            ontology_id,
            RelationCreate(
                relation_type_id=relation_type_ids[relation_type],
                source_entity_id=entity_ids[source],
                target_entity_id=entity_ids[target],
                properties=properties,
            ),
        )
    return len(relation_specs)


def count_specs(entity_specs: dict[str, Iterable[dict[str, Any]]]) -> int:
    return sum(len(list(items)) for items in entity_specs.values())


def main() -> None:
    settings = Settings()
    session_factory = create_session_factory(settings)
    driver = create_neo4j_driver(settings)
    ensure_graph_constraints(driver, settings.embedding_dimensions)
    embedding_client = EmbeddingClient(settings)

    with session_factory() as session:
        cleanup_existing_demo(session, driver)
        project = metadata_service.create_project(
            session,
            ProjectCreate(
                name=PROJECT_NAME,
                description="Demo project seeded for UI and graph exploration.",
            ),
        )
        ontology = metadata_service.create_ontology(
            session,
            project.id,
            OntologyCreate(
                name=ONTOLOGY_NAME,
                description="A compact smart manufacturing ontology with demo instance data.",
                external_mappings={"seed": "backend/scripts/seed_demo_ontology.py"},
            ),
        )
        class_ids = create_classes(session, ontology.id)
        relation_type_ids = create_relation_types(session, ontology.id, class_ids)
        entity_ids = create_entities(
            session, driver, ontology.id, class_ids, embedding_client
        )
        relation_count = create_relations(session, driver, ontology.id, relation_type_ids, entity_ids)

        print(f"Seeded project: {project.name} ({project.id})")
        print(f"Seeded ontology: {ontology.name} ({ontology.id})")
        print(f"Classes: {len(class_ids)}")
        print(f"Relation types: {len(relation_type_ids)}")
        print(f"Entities: {len(entity_ids)}")
        print(f"Relations: {relation_count}")

    driver.close()


if __name__ == "__main__":
    expected_entity_count = count_specs(ENTITY_SPECS)
    if expected_entity_count != 50:
        raise RuntimeError(f"Expected 50 entity specs, found {expected_entity_count}")
    main()
