from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.config import Settings
from app.domain.naming import normalize_neo4j_label, normalize_neo4j_relationship_type
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetModel,
    SemanticRuleDefinitionModel,
)
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_graph_registry import SemanticGraphRegistryService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_rule_definition import SemanticRuleDefinitionService


PROJECT_NAME = "Reasoning Graph Test Data"
ONTOLOGY_NAME = "Supply Chain Reasoning Test Ontology"

CLASS_IDS = {
    "Organization": "class:Organization",
    "Product": "class:Product",
    "Component": "class:Component",
    "Facility": "class:Facility",
    "Batch": "class:Batch",
    "Inspection": "class:Inspection",
    "Issue": "class:Issue",
    "Model": "class:Model",
}

RELATION_TYPE_IDS = {
    "SUPPLIES": "relation:SUPPLIES",
    "CONTAINS": "relation:CONTAINS",
    "PRODUCED_AT": "relation:PRODUCED_AT",
    "PRODUCED_BATCH": "relation:PRODUCED_BATCH",
    "INSPECTED_BY": "relation:INSPECTED_BY",
    "DETECTED_ISSUE": "relation:DETECTED_ISSUE",
    "USES_COMPONENT": "relation:USES_COMPONENT",
    "MONITORS": "relation:MONITORS",
    "DERIVED_RISK": "relation:DERIVED_RISK",
    "DERIVED_REVIEW_REQUIRED": "relation:DERIVED_REVIEW_REQUIRED",
    "DERIVED_CRITICAL_SUPPLIER": "relation:DERIVED_CRITICAL_SUPPLIER",
    "DERIVED_MODEL_CANDIDATE": "relation:DERIVED_MODEL_CANDIDATE",
}

RELATION_DOMAINS = {
    "SUPPLIES": ("Organization", "Component"),
    "CONTAINS": ("Product", "Component"),
    "PRODUCED_AT": ("Product", "Facility"),
    "PRODUCED_BATCH": ("Product", "Batch"),
    "INSPECTED_BY": ("Batch", "Inspection"),
    "DETECTED_ISSUE": ("Batch", "Issue"),
    "USES_COMPONENT": ("Issue", "Component"),
    "MONITORS": ("Model", "Organization"),
    "DERIVED_RISK": ("Product", "Component"),
    "DERIVED_REVIEW_REQUIRED": ("Batch", "Inspection"),
    "DERIVED_CRITICAL_SUPPLIER": ("Organization", "Product"),
    "DERIVED_MODEL_CANDIDATE": ("Model", "Organization"),
}

DATA_PROPERTY_LABELS = {
    "criticality": "Criticality",
    "single_source": "Single Source",
    "status": "Status",
    "scrap_rate": "Scrap Rate",
    "warranty_claims": "Warranty Claims",
    "supplier_score": "Supplier Score",
    "rule_test_fixture": "Rule Test Fixture",
}

INFERRED_RELATION_TYPES = {
    "SUPPLY_DEPENDENCY": "Supply Dependency",
    "PRODUCT_DEPENDENCY": "Product Dependency",
    "QUALITY_SIGNAL": "Quality Signal",
    "MODEL_MONITORING_SIGNAL": "Model Monitoring Signal",
}

SUBPROPERTY_AXIOMS = {
    "SUPPLIES": "SUPPLY_DEPENDENCY",
    "CONTAINS": "PRODUCT_DEPENDENCY",
    "DETECTED_ISSUE": "QUALITY_SIGNAL",
    "MONITORS": "MODEL_MONITORING_SIGNAL",
}


@dataclass(frozen=True)
class EntitySpec:
    key: str
    class_name: str
    name: str
    properties: dict[str, Any]
    aliases: list[str] | None = None


@dataclass(frozen=True)
class RelationSpec:
    relation_type: str
    source: str
    target: str
    properties: dict[str, Any]


def entity(
    key: str,
    class_name: str,
    name: str,
    **properties: Any,
) -> EntitySpec:
    return EntitySpec(key=key, class_name=class_name, name=name, properties=properties)


def relation(
    relation_type: str,
    source: str,
    target: str,
    **properties: Any,
) -> RelationSpec:
    return RelationSpec(
        relation_type=relation_type,
        source=source,
        target=target,
        properties=properties,
    )


ENTITIES = [
    entity(
        "org_atlas", "Organization", "Atlas Robotics", tier="OEM", region="APAC", supplier_score=92
    ),
    entity(
        "org_nova",
        "Organization",
        "Nova Precision",
        tier="Tier 1",
        region="China",
        supplier_score=78,
    ),
    entity(
        "org_helio",
        "Organization",
        "Helio Sensors",
        tier="Tier 2",
        region="Singapore",
        supplier_score=81,
    ),
    entity(
        "org_quartz",
        "Organization",
        "Quartz Battery",
        tier="Tier 1",
        region="Korea",
        supplier_score=68,
    ),
    entity(
        "org_vertex",
        "Organization",
        "Vertex Vision",
        tier="Tier 2",
        region="Taiwan",
        supplier_score=75,
    ),
    entity(
        "org_pioneer",
        "Organization",
        "Pioneer Drives",
        tier="Tier 1",
        region="Japan",
        supplier_score=88,
    ),
    entity(
        "org_orion",
        "Organization",
        "Orion Logistics",
        tier="Service",
        region="SEA",
        supplier_score=70,
    ),
    entity(
        "org_meridian",
        "Organization",
        "Meridian AI Lab",
        tier="Lab",
        region="Singapore",
        supplier_score=95,
    ),
    entity(
        "product_ar200",
        "Product",
        "AR-200 Assembly Robot",
        family="robotics",
        lifecycle="mass_production",
        revenue_impact="high",
    ),
    entity(
        "product_vx",
        "Product",
        "VX Inspect Station",
        family="inspection",
        lifecycle="pilot",
        revenue_impact="medium",
    ),
    entity(
        "product_qb48",
        "Product",
        "QB-48 Battery Pack",
        family="battery",
        lifecycle="mass_production",
        revenue_impact="high",
    ),
    entity(
        "product_pd900",
        "Product",
        "PD-S900 Servo Drive",
        family="drive",
        lifecycle="mass_production",
        revenue_impact="high",
    ),
    entity(
        "product_amr",
        "Product",
        "Atlas Mobile Base",
        family="mobile_robot",
        lifecycle="design",
        revenue_impact="medium",
    ),
    entity(
        "product_tcu",
        "Product",
        "Thermal Control Unit",
        family="thermal",
        lifecycle="pilot",
        revenue_impact="medium",
    ),
    entity(
        "component_reducer",
        "Component",
        "Harmonic Reducer HR-17",
        criticality="high",
        lead_time_days=45,
        single_source=True,
    ),
    entity(
        "component_sensor",
        "Component",
        "Vision Sensor VS-4K",
        criticality="high",
        lead_time_days=30,
        single_source=True,
    ),
    entity(
        "component_cell",
        "Component",
        "Battery Cell BC-2170",
        criticality="high",
        lead_time_days=60,
        single_source=True,
    ),
    entity(
        "component_pcb",
        "Component",
        "Servo PCB SP-12",
        criticality="medium",
        lead_time_days=21,
        single_source=False,
    ),
    entity(
        "component_torque",
        "Component",
        "Torque Transducer TT-80",
        criticality="medium",
        lead_time_days=28,
        single_source=False,
    ),
    entity(
        "component_pad",
        "Component",
        "Thermal Pad TP-6",
        criticality="low",
        lead_time_days=12,
        single_source=False,
    ),
    entity(
        "component_lidar",
        "Component",
        "Lidar Module LM-16",
        criticality="high",
        lead_time_days=38,
        single_source=True,
    ),
    entity(
        "component_board",
        "Component",
        "Edge Compute Board ECB-2",
        criticality="medium",
        lead_time_days=25,
        single_source=False,
    ),
    entity(
        "facility_suzhou",
        "Facility",
        "Suzhou Assembly Plant",
        location="Suzhou",
        certification="IATF16949",
        capacity=4500,
    ),
    entity(
        "facility_sg_lab",
        "Facility",
        "Singapore AI Lab",
        location="Singapore",
        certification="ISO27001",
        capacity=120,
    ),
    entity(
        "facility_busan",
        "Facility",
        "Busan Battery Line",
        location="Busan",
        certification="UL",
        capacity=9000,
    ),
    entity(
        "facility_nagoya",
        "Facility",
        "Nagoya Drive Plant",
        location="Nagoya",
        certification="ISO9001",
        capacity=3000,
    ),
    entity(
        "facility_taipei",
        "Facility",
        "Taipei Vision Cell",
        location="Taipei",
        certification="ISO9001",
        capacity=1600,
    ),
    entity(
        "facility_suzhou_rework",
        "Facility",
        "Suzhou Rework Cell",
        location="Suzhou",
        certification="ISO9001",
        capacity=350,
    ),
    entity(
        "batch_ar_jun",
        "Batch",
        "AR200-2026-06-A",
        lot_size=120,
        scrap_rate=0.018,
        warranty_claims=2,
    ),
    entity(
        "batch_ar_jul",
        "Batch",
        "AR200-2026-07-A",
        lot_size=140,
        scrap_rate=0.041,
        warranty_claims=7,
    ),
    entity(
        "batch_vx_jun", "Batch", "VX-2026-06-P", lot_size=30, scrap_rate=0.052, warranty_claims=1
    ),
    entity(
        "batch_qb_jun", "Batch", "QB48-2026-06-A", lot_size=900, scrap_rate=0.012, warranty_claims=3
    ),
    entity(
        "batch_qb_jul",
        "Batch",
        "QB48-2026-07-A",
        lot_size=950,
        scrap_rate=0.067,
        warranty_claims=18,
    ),
    entity(
        "batch_pd_jun",
        "Batch",
        "PD900-2026-06-A",
        lot_size=420,
        scrap_rate=0.019,
        warranty_claims=1,
    ),
    entity(
        "batch_tcu_jul", "Batch", "TCU-2026-07-P", lot_size=80, scrap_rate=0.034, warranty_claims=0
    ),
    entity(
        "batch_amr_jul", "Batch", "AMR-2026-07-D", lot_size=18, scrap_rate=0.044, warranty_claims=0
    ),
    entity(
        "inspection_optical",
        "Inspection",
        "Optical Inspection",
        method="vision",
        defect_threshold=0.03,
    ),
    entity(
        "inspection_torque",
        "Inspection",
        "Torque Trace Review",
        method="trace_analysis",
        defect_threshold=0.025,
    ),
    entity(
        "inspection_battery",
        "Inspection",
        "Battery Formation Review",
        method="formation_curve",
        defect_threshold=0.04,
    ),
    entity(
        "inspection_supplier",
        "Inspection",
        "Supplier OTIF Audit",
        method="erp_audit",
        defect_threshold=0.02,
    ),
    entity(
        "issue_reducer",
        "Issue",
        "Reducer backlash drift",
        severity="high",
        status="open",
        defect_rate=0.046,
    ),
    entity(
        "issue_sensor",
        "Issue",
        "Sensor calibration shift",
        severity="medium",
        status="open",
        defect_rate=0.033,
    ),
    entity(
        "issue_cell",
        "Issue",
        "Cell impedance spread",
        severity="high",
        status="open",
        defect_rate=0.071,
    ),
    entity(
        "issue_pcb",
        "Issue",
        "PCB solder void",
        severity="medium",
        status="monitoring",
        defect_rate=0.026,
    ),
    entity(
        "issue_lidar",
        "Issue",
        "Lidar blind-zone false positive",
        severity="medium",
        status="open",
        defect_rate=0.039,
    ),
    entity(
        "issue_pad",
        "Issue",
        "Thermal pad compression set",
        severity="low",
        status="monitoring",
        defect_rate=0.018,
    ),
    entity(
        "model_supplier",
        "Model",
        "Supplier Risk Scorer",
        model_type="graph_score",
        metric="precision_at_20",
        score=0.82,
    ),
    entity(
        "model_quality",
        "Model",
        "Quality Escape Predictor",
        model_type="gradient_boosting",
        metric="auc",
        score=0.88,
    ),
    entity(
        "model_battery",
        "Model",
        "Battery Life Estimator",
        model_type="survival",
        metric="mae",
        score=0.12,
    ),
    entity(
        "model_vision",
        "Model",
        "Vision Defect Classifier",
        model_type="cnn",
        metric="f1",
        score=0.94,
    ),
]


RELATIONS = [
    relation("SUPPLIES", "org_nova", "component_reducer", risk="medium", on_time_rate=0.91),
    relation("SUPPLIES", "org_helio", "component_sensor", risk="medium", on_time_rate=0.89),
    relation("SUPPLIES", "org_quartz", "component_cell", risk="high", on_time_rate=0.76),
    relation("SUPPLIES", "org_pioneer", "component_pcb", risk="low", on_time_rate=0.96),
    relation("SUPPLIES", "org_nova", "component_torque", risk="medium", on_time_rate=0.88),
    relation("SUPPLIES", "org_orion", "component_pad", risk="low", on_time_rate=0.94),
    relation("SUPPLIES", "org_vertex", "component_lidar", risk="high", on_time_rate=0.72),
    relation("SUPPLIES", "org_vertex", "component_board", risk="medium", on_time_rate=0.84),
    relation("CONTAINS", "product_ar200", "component_reducer", quantity=6),
    relation("CONTAINS", "product_ar200", "component_pcb", quantity=4),
    relation("CONTAINS", "product_vx", "component_sensor", quantity=2),
    relation("CONTAINS", "product_qb48", "component_cell", quantity=96),
    relation("CONTAINS", "product_pd900", "component_pcb", quantity=1),
    relation("CONTAINS", "product_amr", "component_lidar", quantity=1),
    relation("CONTAINS", "product_amr", "component_board", quantity=1),
    relation("CONTAINS", "product_tcu", "component_pad", quantity=8),
    relation("PRODUCED_AT", "product_ar200", "facility_suzhou", line="A"),
    relation("PRODUCED_AT", "product_vx", "facility_taipei", line="V1"),
    relation("PRODUCED_AT", "product_qb48", "facility_busan", line="B"),
    relation("PRODUCED_AT", "product_pd900", "facility_nagoya", line="D"),
    relation("PRODUCED_AT", "product_amr", "facility_suzhou_rework", line="R"),
    relation("PRODUCED_AT", "product_tcu", "facility_suzhou", line="T"),
    relation("PRODUCED_BATCH", "product_ar200", "batch_ar_jun", period="2026-06"),
    relation("PRODUCED_BATCH", "product_ar200", "batch_ar_jul", period="2026-07"),
    relation("PRODUCED_BATCH", "product_vx", "batch_vx_jun", period="2026-06"),
    relation("PRODUCED_BATCH", "product_qb48", "batch_qb_jun", period="2026-06"),
    relation("PRODUCED_BATCH", "product_qb48", "batch_qb_jul", period="2026-07"),
    relation("PRODUCED_BATCH", "product_pd900", "batch_pd_jun", period="2026-06"),
    relation("PRODUCED_BATCH", "product_tcu", "batch_tcu_jul", period="2026-07"),
    relation("PRODUCED_BATCH", "product_amr", "batch_amr_jul", period="2026-07"),
    relation("INSPECTED_BY", "batch_ar_jun", "inspection_torque", result="pass"),
    relation("INSPECTED_BY", "batch_ar_jul", "inspection_torque", result="fail"),
    relation("INSPECTED_BY", "batch_vx_jun", "inspection_optical", result="fail"),
    relation("INSPECTED_BY", "batch_qb_jun", "inspection_battery", result="pass"),
    relation("INSPECTED_BY", "batch_qb_jul", "inspection_battery", result="fail"),
    relation("INSPECTED_BY", "batch_pd_jun", "inspection_torque", result="pass"),
    relation("INSPECTED_BY", "batch_tcu_jul", "inspection_optical", result="review"),
    relation("INSPECTED_BY", "batch_amr_jul", "inspection_optical", result="review"),
    relation("DETECTED_ISSUE", "batch_ar_jul", "issue_reducer", evidence="torque_trace"),
    relation("DETECTED_ISSUE", "batch_vx_jun", "issue_sensor", evidence="vision_defect"),
    relation("DETECTED_ISSUE", "batch_qb_jul", "issue_cell", evidence="formation_curve"),
    relation("DETECTED_ISSUE", "batch_pd_jun", "issue_pcb", evidence="xray_sample"),
    relation("DETECTED_ISSUE", "batch_amr_jul", "issue_lidar", evidence="field_trial"),
    relation("DETECTED_ISSUE", "batch_tcu_jul", "issue_pad", evidence="thermal_cycle"),
    relation("USES_COMPONENT", "issue_reducer", "component_reducer", confidence=0.91),
    relation("USES_COMPONENT", "issue_sensor", "component_sensor", confidence=0.82),
    relation("USES_COMPONENT", "issue_cell", "component_cell", confidence=0.94),
    relation("USES_COMPONENT", "issue_pcb", "component_pcb", confidence=0.61),
    relation("USES_COMPONENT", "issue_lidar", "component_lidar", confidence=0.78),
    relation("USES_COMPONENT", "issue_pad", "component_pad", confidence=0.55),
    relation("MONITORS", "model_supplier", "org_quartz", purpose="supplier_risk"),
    relation("MONITORS", "model_supplier", "org_vertex", purpose="supplier_risk"),
    relation("MONITORS", "model_quality", "batch_ar_jul", purpose="quality_escape"),
    relation("MONITORS", "model_quality", "batch_vx_jun", purpose="quality_escape"),
    relation("MONITORS", "model_quality", "batch_qb_jul", purpose="quality_escape"),
    relation("MONITORS", "model_battery", "batch_qb_jun", purpose="life_estimation"),
    relation("MONITORS", "model_battery", "batch_qb_jul", purpose="life_estimation"),
    relation("MONITORS", "model_vision", "batch_vx_jun", purpose="visual_defects"),
    relation("MONITORS", "model_vision", "batch_amr_jul", purpose="visual_defects"),
    relation(
        "DERIVED_RISK",
        "product_ar200",
        "component_reducer",
        rule_id="R1",
        reason="contains high-criticality single-source component with open issue",
    ),
    relation(
        "DERIVED_RISK",
        "product_qb48",
        "component_cell",
        rule_id="R1",
        reason="contains high-criticality single-source component with open issue",
    ),
    relation(
        "DERIVED_RISK",
        "product_amr",
        "component_lidar",
        rule_id="R1",
        reason="contains high-criticality single-source component with open issue",
    ),
    relation(
        "DERIVED_REVIEW_REQUIRED",
        "batch_ar_jul",
        "inspection_torque",
        rule_id="R2",
        reason="scrap_rate > 0.04 or failed inspection",
    ),
    relation(
        "DERIVED_REVIEW_REQUIRED",
        "batch_vx_jun",
        "inspection_optical",
        rule_id="R2",
        reason="scrap_rate > 0.04 or failed inspection",
    ),
    relation(
        "DERIVED_REVIEW_REQUIRED",
        "batch_qb_jul",
        "inspection_battery",
        rule_id="R2",
        reason="scrap_rate > 0.04 or failed inspection",
    ),
    relation(
        "DERIVED_CRITICAL_SUPPLIER",
        "org_quartz",
        "product_qb48",
        rule_id="R3",
        reason="supplier provides high-criticality component used by high-impact product",
    ),
    relation(
        "DERIVED_CRITICAL_SUPPLIER",
        "org_vertex",
        "product_amr",
        rule_id="R3",
        reason="supplier provides high-criticality component used by product under review",
    ),
    relation(
        "DERIVED_MODEL_CANDIDATE",
        "model_quality",
        "batch_qb_jul",
        rule_id="R4",
        reason="high scrap and warranty claims",
    ),
    relation(
        "DERIVED_MODEL_CANDIDATE",
        "model_supplier",
        "org_quartz",
        rule_id="R4",
        reason="high supplier risk and low on-time rate",
    ),
]


RULE_DESCRIPTIONS = [
    {
        "id": "R1",
        "name": "High-risk product component",
        "logic": "Product CONTAINS Component where criticality=high and single_source=true; an Issue USES_COMPONENT the same Component with status=open.",
    },
    {
        "id": "R2",
        "name": "Batch requires quality review",
        "logic": "Batch has scrap_rate > 0.04 or INSPECTED_BY result=fail.",
    },
    {
        "id": "R3",
        "name": "Critical supplier",
        "logic": "Organization SUPPLIES Component where criticality=high, and a Product CONTAINS that Component.",
    },
    {
        "id": "R4",
        "name": "Model monitoring candidate",
        "logic": "Batch has high scrap/warranty claims or Organization has risky supply relation.",
    },
]


def semantic_graph_iris(settings: Settings, ontology_id: str) -> dict[str, str]:
    prefix = settings.semantic_graph_iri_prefix.rstrip("/")
    return {
        "ontology": f"{prefix}/ontology/{ontology_id}/reasoning-test",
        "data": f"{prefix}/data/{ontology_id}/reasoning-test",
    }


def seeded_rule_iris(settings: Settings) -> list[str]:
    return [
        iri_for_rule(settings, "R1"),
        iri_for_rule(settings, "R2"),
        iri_for_rule(settings, "R3"),
        iri_for_rule(settings, "R4A"),
        iri_for_rule(settings, "R4B"),
    ]


def cleanup_existing(
    session: Any, rdf_store: RdfStoreRepository, settings: Settings
) -> None:
    for rule in session.scalars(
        select(SemanticRuleDefinitionModel).where(
            SemanticRuleDefinitionModel.rule_iri.in_(seeded_rule_iris(settings))
        )
    ):
        session.delete(rule)
    session.commit()

    existing = session.scalars(
        select(ProjectModel).where(ProjectModel.name == PROJECT_NAME)
    ).first()
    if existing is None:
        return

    existing_ontologies = list(
        session.scalars(select(OntologyModel).where(OntologyModel.project_id == existing.id))
    )
    for ontology in existing_ontologies:
        graph_iris = semantic_graph_iris(settings, ontology.id)
        for graph_iri in graph_iris.values():
            rdf_store.drop_named_graph(graph_iri)
        for graph_set in session.scalars(
            select(SemanticGraphSetModel).where(SemanticGraphSetModel.scope_id == ontology.id)
        ):
            session.delete(graph_set)

    session.delete(existing)
    session.commit()


def create_project_and_ontology(session: Any) -> tuple[ProjectModel, OntologyModel]:
    project = ProjectModel(
        id=str(uuid4()),
        name=PROJECT_NAME,
        normalized_label=normalize_neo4j_label(PROJECT_NAME),
        description=(
            "Seeded graph fixture for validating search, graph traversal, "
            "relation filtering, and deterministic reasoning examples."
        ),
    )
    session.add(project)
    session.flush()

    ontology = OntologyModel(
        id=str(uuid4()),
        project_id=project.id,
        name=ONTOLOGY_NAME,
        description="50 entity supply-chain graph with explicit rule-test patterns.",
        external_mappings={
            "seed": "backend/scripts/seed_reasoning_graph_test_data.py",
            "entity_count": len(ENTITIES),
            "relation_count": len(RELATIONS),
            "rule_hints": RULE_DESCRIPTIONS,
            "class_ids": CLASS_IDS,
            "relation_type_ids": RELATION_TYPE_IDS,
        },
    )
    session.add(ontology)
    session.commit()
    session.refresh(project)
    session.refresh(ontology)
    return project, ontology


def iri_for_class(settings: Settings, class_name: str) -> str:
    return f"{settings.semantic_base_iri.rstrip('/')}/test/class/{class_name}"


def iri_for_entity(settings: Settings, key: str) -> str:
    return f"{settings.semantic_base_iri.rstrip('/')}/test/entity/{key}"


def iri_for_relation(settings: Settings, relation_type: str) -> str:
    normalised = normalize_neo4j_relationship_type(relation_type).lower()
    return f"{settings.semantic_base_iri.rstrip('/')}/test/relation/{normalised}"


def iri_for_data_property(settings: Settings, property_name: str) -> str:
    return f"{settings.semantic_base_iri.rstrip('/')}/test/property/{property_name}"


def iri_for_rule(settings: Settings, rule_id: str) -> str:
    return f"{settings.semantic_base_iri.rstrip('/')}/test/rule/{rule_id.lower()}"


def ttl_literal(value: Any) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ttl_value(value: Any) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean>'
    if isinstance(value, int) and not isinstance(value, bool):
        return f'"{value}"^^<http://www.w3.org/2001/XMLSchema#integer>'
    if isinstance(value, float):
        return f'"{value}"^^<http://www.w3.org/2001/XMLSchema#decimal>'
    return ttl_literal(value)


def build_ontology_turtle(settings: Settings) -> str:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
    ]
    for class_name in CLASS_IDS:
        lines.extend(
            [
                f"<{iri_for_class(settings, class_name)}> a owl:Class ;",
                f"  rdfs:label {ttl_literal(class_name)} .",
                "",
            ]
        )
    for relation_type, (source_class, target_class) in RELATION_DOMAINS.items():
        super_relation = SUBPROPERTY_AXIOMS.get(relation_type)
        super_axiom = (
            f" ;\n  rdfs:subPropertyOf <{iri_for_relation(settings, super_relation)}>"
            if super_relation
            else ""
        )
        lines.extend(
            [
                f"<{iri_for_relation(settings, relation_type)}> a owl:ObjectProperty ;",
                f"  rdfs:label {ttl_literal(relation_type.replace('_', ' ').title())} ;",
                f"  rdfs:domain <{iri_for_class(settings, source_class)}> ;",
                f"  rdfs:range <{iri_for_class(settings, target_class)}>{super_axiom} .",
                "",
            ]
        )
    for relation_type, label in INFERRED_RELATION_TYPES.items():
        lines.extend(
            [
                f"<{iri_for_relation(settings, relation_type)}> a owl:ObjectProperty ;",
                f"  rdfs:label {ttl_literal(label)} .",
                "",
            ]
        )
    for property_name, label in DATA_PROPERTY_LABELS.items():
        lines.extend(
            [
                f"<{iri_for_data_property(settings, property_name)}> a owl:DatatypeProperty ;",
                f"  rdfs:label {ttl_literal(label)} .",
                "",
            ]
        )
    return "\n".join(lines)


def build_data_turtle(settings: Settings) -> str:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
    ]
    for spec in ENTITIES:
        properties = {
            **spec.properties,
            "rule_test_fixture": True,
        }
        property_lines = [
            f"  <{iri_for_data_property(settings, property_name)}> {ttl_value(value)}"
            for property_name, value in sorted(properties.items())
            if property_name in DATA_PROPERTY_LABELS
        ]
        lines.append(
            f"<{iri_for_entity(settings, spec.key)}> a owl:NamedIndividual, "
            f"<{iri_for_class(settings, spec.class_name)}> ;"
        )
        lines.append(f"  rdfs:label {ttl_literal(spec.name)}" + (" ;" if property_lines else " ."))
        for index, property_line in enumerate(property_lines):
            lines.append(property_line + (" ." if index == len(property_lines) - 1 else " ;"))
        lines.append("")
    for spec in RELATIONS:
        if spec.relation_type.startswith("DERIVED_"):
            continue
        lines.append(
            f"<{iri_for_entity(settings, spec.source)}> "
            f"<{iri_for_relation(settings, spec.relation_type)}> "
            f"<{iri_for_entity(settings, spec.target)}> ."
        )
    lines.append("")
    return "\n".join(lines)


def upsert_graph_revision(
    session: Any,
    graph_iri: str,
    content_hash: str | None,
    *,
    changed_by: str,
) -> None:
    revision = session.scalar(
        select(SemanticGraphRevisionModel).where(SemanticGraphRevisionModel.graph_iri == graph_iri)
    )
    if revision is None:
        revision = SemanticGraphRevisionModel(
            id=str(uuid4()),
            graph_iri=graph_iri,
            revision=1,
            content_hash=content_hash,
            changed_by=changed_by,
            revision_metadata={"seed": "reasoning_graph_test_data"},
        )
        session.add(revision)
    else:
        revision.revision += 1
        revision.content_hash = content_hash
        revision.changed_by = changed_by
        revision.revision_metadata = {
            **(revision.revision_metadata or {}),
            "seed": "reasoning_graph_test_data",
        }


def create_semantic_workspace(
    session: Any,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    ontology: OntologyModel,
) -> tuple[str, dict[str, str]]:
    graph_iris = semantic_graph_iris(settings, ontology.id)
    rdf_store.put_named_graph(graph_iris["ontology"], build_ontology_turtle(settings), "turtle")
    rdf_store.put_named_graph(graph_iris["data"], build_data_turtle(settings), "turtle")

    registry = SemanticGraphRegistryService(session, settings)
    registry.register_graph(
        graph_iris["ontology"],
        owner_type="ontology",
        owner_id=ontology.id,
        created_by="seed:reasoning-graph-test-data",
        metadata={"seed": "reasoning_graph_test_data", "role": "asserted_ontology"},
    )
    registry.register_graph(
        graph_iris["data"],
        owner_type="ontology",
        owner_id=ontology.id,
        created_by="seed:reasoning-graph-test-data",
        metadata={"seed": "reasoning_graph_test_data", "role": "asserted_data"},
    )
    upsert_graph_revision(
        session,
        graph_iris["ontology"],
        rdf_store.graph_content_hash(graph_iris["ontology"]),
        changed_by="seed:reasoning-graph-test-data",
    )
    upsert_graph_revision(
        session,
        graph_iris["data"],
        rdf_store.graph_content_hash(graph_iris["data"]),
        changed_by="seed:reasoning-graph-test-data",
    )
    session.commit()

    graph_set = SemanticGraphSetService(session, settings).create_graph_set(
        name=f"{ontology.name} active workspace",
        scope_type="ontology",
        scope_id=ontology.id,
        members=[
            {"graph_iri": graph_iris["ontology"], "role": "asserted_ontology", "sort_order": 0},
            {"graph_iri": graph_iris["data"], "role": "asserted_data", "sort_order": 1},
        ],
        created_by="seed:reasoning-graph-test-data",
        metadata={"seed": "reasoning_graph_test_data"},
    )
    return graph_set.id, graph_iris


def _term(iri: str) -> str:
    return f"<{iri}>"


def _literal(value: Any) -> str:
    return ttl_value(value)


def build_rule_definitions(settings: Settings) -> list[dict[str, Any]]:
    def relation(relation_type: str) -> str:
        return _term(iri_for_relation(settings, relation_type))

    def prop(property_name: str) -> str:
        return _term(iri_for_data_property(settings, property_name))

    fixture = f"?fixture {prop('rule_test_fixture')} {_literal(True)} ."
    return [
        {
            "rule_id": "R1",
            "name": "High-risk product component",
            "priority": 10,
            "language": "sparql_construct",
            "body": {
                "template": f"""
CONSTRUCT {{
  ?product {relation("DERIVED_RISK")} ?component .
}}
WHERE {{
  GRAPH ?g {{
    ?product {relation("CONTAINS")} ?component .
    ?component {prop("criticality")} {_literal("high")} .
    ?component {prop("single_source")} {_literal(True)} .
    ?issue {relation("USES_COMPONENT")} ?component .
    ?issue {prop("status")} {_literal("open")} .
    {fixture.replace("?fixture", "?product")}
  }}
}}
"""
            },
        },
        {
            "rule_id": "R2",
            "name": "Batch requires quality review",
            "priority": 20,
            "language": "sparql_construct",
            "body": {
                "template": f"""
CONSTRUCT {{
  ?batch {relation("DERIVED_REVIEW_REQUIRED")} ?inspection .
}}
WHERE {{
  GRAPH ?g {{
    ?batch {relation("INSPECTED_BY")} ?inspection .
    ?batch {prop("scrap_rate")} ?scrap_rate .
    {fixture.replace("?fixture", "?batch")}
    FILTER(?scrap_rate > 0.04)
  }}
}}
"""
            },
        },
        {
            "rule_id": "R3",
            "name": "Critical supplier",
            "priority": 30,
            "language": "sparql_construct",
            "body": {
                "template": f"""
CONSTRUCT {{
  ?supplier {relation("DERIVED_CRITICAL_SUPPLIER")} ?product .
}}
WHERE {{
  GRAPH ?g {{
    ?supplier {relation("SUPPLIES")} ?component .
    ?component {prop("criticality")} {_literal("high")} .
    ?product {relation("CONTAINS")} ?component .
    {fixture.replace("?fixture", "?supplier")}
  }}
}}
"""
            },
        },
        {
            "rule_id": "R4A",
            "name": "Model candidate for high-scrap batch",
            "priority": 40,
            "language": "sparql_construct",
            "body": {
                "template": f"""
CONSTRUCT {{
  ?model {relation("DERIVED_MODEL_CANDIDATE")} ?batch .
}}
WHERE {{
  GRAPH ?g {{
    ?model {relation("MONITORS")} ?batch .
    ?batch {prop("scrap_rate")} ?scrap_rate .
    {fixture.replace("?fixture", "?model")}
    FILTER(?scrap_rate > 0.04)
  }}
}}
"""
            },
        },
        {
            "rule_id": "R4B",
            "name": "Model candidate for low-score supplier",
            "priority": 41,
            "language": "sparql_construct",
            "body": {
                "template": f"""
CONSTRUCT {{
  ?model {relation("DERIVED_MODEL_CANDIDATE")} ?supplier .
}}
WHERE {{
  GRAPH ?g {{
    ?model {relation("MONITORS")} ?supplier .
    ?supplier {prop("supplier_score")} ?score .
    {fixture.replace("?fixture", "?model")}
    FILTER(?score < 70)
  }}
}}
"""
            },
        },
    ]


def create_rule_definitions(session: Any, settings: Settings, graph_set_id: str) -> list[str]:
    service = SemanticRuleDefinitionService(session, settings)
    rule_ids: list[str] = []
    for spec in build_rule_definitions(settings):
        rule = service.create_rule(
            rule_iri=iri_for_rule(settings, spec["rule_id"]),
            name=f"{ONTOLOGY_NAME}: {spec['name']}",
            language=spec["language"],
            body=spec["body"],
            input_roles=["asserted_data"],
            output_kind="assertion",
            requires_review=False,
            priority=spec["priority"],
            safety_profile={
                "max_generated_statements": 1000,
                "timeout_seconds": 10,
            },
            status="active",
            created_by="seed:reasoning-graph-test-data",
            metadata={
                "seed": "reasoning_graph_test_data",
                "graph_set_id": graph_set_id,
                "rule_id": spec["rule_id"],
            },
        )
        rule_ids.append(rule.id)
    return rule_ids


def main() -> None:
    if len(ENTITIES) != 50:
        raise RuntimeError(f"Expected 50 entities, found {len(ENTITIES)}")

    settings = Settings()
    session_factory = create_session_factory(settings)
    rdf_store = RdfStoreRepository(settings.oxigraph_url)

    with session_factory() as session:
        cleanup_existing(session, rdf_store, settings)
        project, ontology = create_project_and_ontology(session)
        graph_set_id, graph_iris = create_semantic_workspace(
            session, rdf_store, settings, ontology
        )
        rule_definition_ids = create_rule_definitions(session, settings, graph_set_id)

        print(f"Seeded project: {project.name} ({project.id})")
        print(f"Seeded ontology: {ontology.name} ({ontology.id})")
        print(f"Seeded graph set: {graph_set_id}")
        print(f"Active semantic rules: {len(rule_definition_ids)}")
        print(f"Ontology graph: {graph_iris['ontology']}")
        print(f"Data graph: {graph_iris['data']}")
        print("Rule hints:")
        for rule in RULE_DESCRIPTIONS:
            print(f"- {rule['id']} {rule['name']}: {rule['logic']}")


if __name__ == "__main__":
    main()
