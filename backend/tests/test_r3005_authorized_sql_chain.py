"""R3.0-005 A3/A4: mechanical authorized-SQL chain tests.

In-process FastAPI ``TestClient`` over the real platform control plane
(SQLAlchemy session) and a real Oxigraph RDF store — never the live 8001
service. Fixture semantics are seeded through the real product write path
(``KEY_MODEL`` principal -> Build Session -> Modeling Batch dry-run -> apply),
following the R3.0-003 precedent; table/column names are relocated onto the
R3.0-001 ``industrial_service_v3`` baseline loaded by the scenario loader.

The mechanical derivation rules below are test/assertion-layer code (design
§3.4), not product code. They cover **direct column mappings only**: metric ->
SELECT aggregation(measure column) FROM main table [joins mechanically
assembled from JoinMapping steps] WHERE declarative filters (property IRI ->
column, enum values validated through EnumValueMeaning) GROUP BY grain
properties. Every identifier must close against the authorized read surface
or the chain terminates in the uniform "unconfirmable" state.

Derived-expression metrics (``valueExpression``) are NOT mechanically
translated: per the R3.0-003 contract ``valueExpression`` is platform-opaque
free text, so expression -> SQL interpretation belongs to the consumer (the
real-LLM smoke rounds). The mechanical chain verifies derived metrics for
**read closure only** — the authorized read surface returns the complete
``valueExpression`` text plus every mapping it references. No expression DSL
and no generic translator is introduced for this requirement.

Gating: requires ``RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1`` (running local
Oxigraph) and ``R3005_SQL_ADAPTER_DSN`` (scenario PostgreSQL); skips cleanly
otherwise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import DEFAULT_SEMANTIC_BASE_IRI, Settings
from app.main import create_app
from app.repositories.models import (
    BuildSessionModel,
    ModelingBatchModel,
    OntologyModel,
    ProjectModel,
)
from app.repositories.postgres import Base
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.ontology_workspace import OntologyWorkspaceService

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("RUN_OXIGRAPH_SPARQL_RUNNER_TESTS") != "1",
        reason="requires a running local Oxigraph server (RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1)",
    ),
    pytest.mark.skipif(
        not os.environ.get("R3005_SQL_ADAPTER_DSN"),
        reason="R3005_SQL_ADAPTER_DSN is not set (scenario PostgreSQL unavailable)",
    ),
]

ADAPTER = (
    Path(__file__).resolve().parents[2] / "scripts" / "r3-0-005" / "sql_exec_adapter.py"
)
DSN = os.environ["R3005_SQL_ADAPTER_DSN"] if os.environ.get("R3005_SQL_ADAPTER_DSN") else ""

SCHEMA = "industrial_service_v3"

# ---------------------------------------------------------------------------
# Fixture semantic content (R3.0-003 fixture shape relocated onto the
# industrial_service_v3 baseline; domain names live only in test data).
# ---------------------------------------------------------------------------

CLASS_WORK_ORDER = "work-order"
CLASS_INCIDENT = "incident"
CLASS_ASSET = "asset"
CLASS_EQUIPMENT_MODEL = "equipment-model"
CLASS_SPARE_PART = "spare-part"

REL_ADDRESSES_INCIDENT = "addresses-incident"
REL_INVOLVES_ASSET = "involves-asset"
REL_HAS_MODEL = "has-model"

PROP_WO_ID = "workOrderId"
PROP_STATUS_CODE = "statusCode"
PROP_OPENED_AT = "openedAt"
PROP_RESOLVED_AT = "resolvedAt"
PROP_INCIDENT_REF = "incidentRef"
PROP_RESOLUTION_DURATION = "resolutionDuration"
PROP_INCIDENT_ID = "incidentId"
PROP_REPORTED_AT = "reportedAt"
PROP_ASSET_REF = "assetRef"
PROP_ASSET_ID = "assetId"
PROP_MODEL_REF = "modelRef"
PROP_MODEL_ID = "modelId"
PROP_MODEL_NAME = "modelName"
PROP_PART_ID = "partId"
PROP_STANDARD_COST = "standardCost"

METRIC_MTTR = "metric-mttr"
METRIC_PARTCOST = "metric-partcost"

GRANT_COST = "cost-visibility"

UNCONFIRMABLE = {"status": "unconfirmable"}

_AGGREGATIONS = {"avg": "AVG", "sum": "SUM", "min": "MIN", "max": "MAX", "count": "COUNT"}


def _seed_items(base: str) -> list[dict]:
    """Fixture items; every payload IRI is absolute (compiler requirement)."""

    def item(item_id: str, kind: str, payload: dict) -> dict:
        # NB: ``ontology_id`` is a forbidden target field in Modeling item
        # payloads; the server injects it from the batch submit envelope.
        return {
            "client_item_id": item_id,
            "command_kind": kind,
            "payload": payload,
            "rationale": "R3.0-005 mechanical chain fixture",
            "evidence": [
                {
                    "document_name": "schema-ddl.md",
                    "excerpt": f"{item_id} is grounded in the industrial_service_v3 schema.",
                }
            ],
        }

    def class_item(class_id: str, name: str) -> dict:
        return item(f"class-{class_id}", "create_class", {"class_id": class_id, "name": name})

    def relation_item(relation_id: str, name: str, source: str, target: str) -> dict:
        return item(
            f"rel-{relation_id}",
            "create_relation_type",
            {
                "relation_type_id": relation_id,
                "name": name,
                "source_class_id": source,
                "target_class_id": target,
            },
        )

    def property_item(class_id: str, property_id: str, name: str, datatype: str) -> dict:
        return item(
            f"prop-{property_id}",
            "create_property",
            {
                "class_id": class_id,
                "property_id": property_id,
                "name": name,
                "datatype": datatype,
            },
        )

    prop = lambda name: f"{base}property/{name}"  # noqa: E731
    table = lambda name: f"{SCHEMA}.{name}"  # noqa: E731

    def column(property_name: str, column_name: str, role: str | None = None) -> dict:
        entry = {"property_iri": prop(property_name), "column": column_name}
        if role:
            entry["role"] = role
        return entry

    def table_mapping_item(
        item_id: str, class_id: str, table_name: str, columns: list[dict]
    ) -> dict:
        return item(
            item_id,
            "create_table_mapping",
            {
                "table_mapping_id": item_id,
                "name": f"{table_name} mapping",
                "mapped_class_iri": f"{base}class/{class_id}",
                "table_name": table_name,
                "column_mappings": columns,
                "schema_source": "industrial-service-v3-schema-2026-08-22",
            },
        )

    def join_mapping_item(
        item_id: str, relation_id: str, from_table: str, to_table: str, column_name: str
    ) -> dict:
        return item(
            item_id,
            "create_join_mapping",
            {
                "join_mapping_id": item_id,
                "name": f"{from_table} to {to_table}",
                "relation_type_iri": f"{base}relation-type/{relation_id}",
                "join_direction": "forward",
                "join_path": [
                    {
                        "from_table": from_table,
                        "to_table": to_table,
                        "from_columns": [column_name],
                        "to_columns": [column_name],
                    }
                ],
                "schema_source": "industrial-service-v3-schema-2026-08-22",
            },
        )

    return [
        class_item(CLASS_WORK_ORDER, "WorkOrder"),
        class_item(CLASS_INCIDENT, "Incident"),
        class_item(CLASS_ASSET, "Asset"),
        class_item(CLASS_EQUIPMENT_MODEL, "EquipmentModel"),
        class_item(CLASS_SPARE_PART, "SparePart"),
        relation_item(
            REL_ADDRESSES_INCIDENT, "addressesIncident", CLASS_WORK_ORDER, CLASS_INCIDENT
        ),
        relation_item(REL_INVOLVES_ASSET, "involvesAsset", CLASS_INCIDENT, CLASS_ASSET),
        relation_item(REL_HAS_MODEL, "hasModel", CLASS_ASSET, CLASS_EQUIPMENT_MODEL),
        property_item(CLASS_WORK_ORDER, PROP_WO_ID, "workOrderId", "xsd:string"),
        property_item(CLASS_WORK_ORDER, PROP_STATUS_CODE, "statusCode", "xsd:string"),
        property_item(CLASS_WORK_ORDER, PROP_OPENED_AT, "openedAt", "xsd:dateTime"),
        property_item(CLASS_WORK_ORDER, PROP_RESOLVED_AT, "resolvedAt", "xsd:dateTime"),
        property_item(CLASS_WORK_ORDER, PROP_INCIDENT_REF, "incidentRef", "xsd:string"),
        property_item(
            CLASS_WORK_ORDER, PROP_RESOLUTION_DURATION, "resolutionDuration", "xsd:decimal"
        ),
        property_item(CLASS_INCIDENT, PROP_INCIDENT_ID, "incidentId", "xsd:string"),
        property_item(CLASS_INCIDENT, PROP_REPORTED_AT, "reportedAt", "xsd:dateTime"),
        property_item(CLASS_INCIDENT, PROP_ASSET_REF, "assetRef", "xsd:string"),
        property_item(CLASS_ASSET, PROP_ASSET_ID, "assetId", "xsd:string"),
        property_item(CLASS_ASSET, PROP_MODEL_REF, "modelRef", "xsd:string"),
        property_item(CLASS_EQUIPMENT_MODEL, PROP_MODEL_ID, "modelId", "xsd:string"),
        property_item(CLASS_EQUIPMENT_MODEL, PROP_MODEL_NAME, "modelName", "xsd:string"),
        property_item(CLASS_SPARE_PART, PROP_PART_ID, "partId", "xsd:string"),
        property_item(CLASS_SPARE_PART, PROP_STANDARD_COST, "standardCost", "xsd:decimal"),
        table_mapping_item(
            "tm-wo",
            CLASS_WORK_ORDER,
            table("work_orders"),
            [
                column(PROP_WO_ID, "work_order_id", "business_key"),
                column(PROP_STATUS_CODE, "status"),
                column(PROP_OPENED_AT, "opened_at"),
                column(PROP_RESOLVED_AT, "resolved_at"),
                column(PROP_INCIDENT_REF, "incident_id"),
            ],
        ),
        table_mapping_item(
            "tm-incident",
            CLASS_INCIDENT,
            table("incidents"),
            [
                column(PROP_INCIDENT_ID, "incident_id", "business_key"),
                column(PROP_ASSET_REF, "asset_id"),
                column(PROP_REPORTED_AT, "reported_at"),
            ],
        ),
        table_mapping_item(
            "tm-asset",
            CLASS_ASSET,
            table("assets"),
            [
                column(PROP_ASSET_ID, "asset_id", "business_key"),
                column(PROP_MODEL_REF, "model_id"),
            ],
        ),
        table_mapping_item(
            "tm-model",
            CLASS_EQUIPMENT_MODEL,
            table("equipment_models"),
            [
                column(PROP_MODEL_ID, "model_id", "business_key"),
                column(PROP_MODEL_NAME, "model_name"),
            ],
        ),
        table_mapping_item(
            "tm-part",
            CLASS_SPARE_PART,
            table("spare_parts"),
            [
                column(PROP_PART_ID, "part_id", "business_key"),
                column(PROP_STANDARD_COST, "standard_cost"),
            ],
        ),
        join_mapping_item(
            "jm-wo-incident",
            REL_ADDRESSES_INCIDENT,
            table("work_orders"),
            table("incidents"),
            "incident_id",
        ),
        join_mapping_item(
            "jm-incident-asset",
            REL_INVOLVES_ASSET,
            table("incidents"),
            table("assets"),
            "asset_id",
        ),
        join_mapping_item(
            "jm-asset-model",
            REL_HAS_MODEL,
            table("assets"),
            table("equipment_models"),
            "model_id",
        ),
        item(
            "em-status-resolved",
            "create_enum_meaning",
            {
                "enum_meaning_id": "em-status-resolved",
                "name": "status RESOLVED",
                "property_iri": prop(PROP_STATUS_CODE),
                "enum_value": "RESOLVED",
                "business_meaning": "已完成工单",
                "schema_source": "industrial-service-v3-schema-2026-08-22",
            },
        ),
        item(
            METRIC_MTTR,
            "create_metric_definition",
            {
                "metric_id": METRIC_MTTR,
                "name": "平均解决时长",
                "description": "各设备型号的平均解决时长（小时）",
                "grain": [prop(PROP_MODEL_NAME)],
                "time_field": prop(PROP_OPENED_AT),
                "measure_property_iri": prop(PROP_RESOLUTION_DURATION),
                "value_expression": (
                    "解决时长 resolutionDuration = work_orders.resolved_at - "
                    "incidents.reported_at，单位小时；reported_at 经 "
                    "work_orders→incidents 关联取得"
                ),
                "aggregation": "avg",
                "filters": [
                    {"field": prop(PROP_STATUS_CODE), "operator": "eq", "value": "RESOLVED"}
                ],
                "null_value_rule": "resolved_at 或 reported_at 为空的工单不计入分子",
                "denominator_rule": "分母为过滤后的已完成工单",
                "schema_source": "industrial-service-v3-schema-2026-08-22",
                "semantic_version": "v1",
            },
        ),
        item(
            METRIC_PARTCOST,
            "create_metric_definition",
            {
                "metric_id": METRIC_PARTCOST,
                "name": "备件平均标准成本",
                "description": "全部备件的平均标准成本（公共口径）",
                "grain": [],
                "time_field": prop(PROP_PART_ID),
                "measure_property_iri": prop(PROP_STANDARD_COST),
                "aggregation": "avg",
                "filters": [],
                "null_value_rule": "standard_cost 非空（表约束保证）",
                "denominator_rule": "分母为全部备件",
                "schema_source": "industrial-service-v3-schema-2026-08-22",
                "semantic_version": "v1",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Fixture: platform under test (in-process app + real stores)
# ---------------------------------------------------------------------------


class ChainEnv:
    def __init__(self, client, project_id, ontology_id,  base, keys):
        self.client = client
        self.project_id = project_id
        self.ontology_id = ontology_id
        self.base = base
        self.keys = keys
        self.seeding_batch_ids: list[str] = []

    def iri(self, path: str) -> str:
        return f"{self.base}{path}"

    def headers(self, name: str) -> dict:
        return {"Authorization": f"Bearer {self.keys[name]}"}


@pytest.fixture()
def chain_env():
    token = uuid.uuid4().hex
    # The read-model SPARQL templates resolve the ``op:`` vocabulary to the
    # DEFAULT semantic base IRI at import time (R3.0-003 D1 lesson), so the
    # fixture keeps the default base and isolates on the token-scoped graph
    # prefix instead; resource IRIs live inside those graphs.
    base = DEFAULT_SEMANTIC_BASE_IRI
    graph_prefix = f"https://r3005.test/{token}/graph/"
    settings = Settings(
        semantic_graph_iri_prefix=graph_prefix,
        semantic_product_write_mode="rdf_primary",
    )
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    project_id = f"p{token[:12]}"
    ontology_id = f"o{token[:12]}"
    with factory() as session:
        session.add(
            ProjectModel(id=project_id, name="R3.0-005", normalized_label=f"r3005{token[:8]}")
        )
        ontology = OntologyModel(id=ontology_id, project_id=project_id, name="R3.0-005 O_m")
        session.add(ontology)
        session.flush()
        OntologyWorkspaceService(session, settings).ensure(ontology)
        session.commit()
        ontology_id = session.scalars(
            select(SemanticGraphSetModel.id).where(
                SemanticGraphSetModel.scope_id == ontology_id,
                SemanticGraphSetModel.is_default.is_(True),
            )
        ).one()
        keys = {}
        for name, kwargs in (
            ("admin", {"project_id": None, "scopes": ["admin"]}),
            ("model", {"project_id": project_id, "scopes": ["model"]}),
            (
                "grant",
                {"project_id": project_id, "scopes": ["read"], "semantic_grants": [GRANT_COST]},
            ),
            ("nogrant", {"project_id": project_id, "scopes": ["read"]}),
        ):
            _record, plaintext = create_api_key(
                session, name=f"r3005-{name}-{token[:6]}", **kwargs
            )
            keys[name] = plaintext
        session.commit()
        model_revision = OntologyModelRevisionService(session, settings).version_for(
            ontology_id
        )

    store = RdfStoreRepository(os.environ.get("OXIGRAPH_URL", "http://127.0.0.1:7878"))
    app = create_app()
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.rdf_store = store

    with TestClient(app) as client:
        env = ChainEnv(client, project_id, ontology_id, ontology_id, base, keys)
        _seed_fixture(env, model_revision)
        yield env

    # Cleanup: drop the token-scoped Oxigraph graphs; the SQLite control
    # plane (project, keys, graph sets) dies with the in-memory engine.
    for category in ("ontology", "data", "shapes", "policy"):
        store.update_sparql(f"DROP SILENT GRAPH <{graph_prefix}{category}/{ontology_id}>")
    engine.dispose()


def _seed_fixture(env: ChainEnv, model_revision: int) -> None:
    client, headers = env.client, env.headers("model")

    created = client.post(
        f"/api/projects/{env.project_id}/build-sessions",
        json={"client_session_id": "r3005-seed"},
        headers=headers,
    )
    assert created.status_code in {200, 201}, created.text
    session_id = created.json()["id"]

    lease = client.post(
        f"/api/build-sessions/{session_id}/ontology-leases/{env.ontology_id}:acquire",
        json={"client_request_id": "r3005-lease-1", "expected_session_revision": 1},
        headers=headers,
    )
    assert lease.status_code == 200, lease.text
    lease_token = lease.json()["lease_token"]

    def submit(mode: str, batch: str, key: str, token: str | None = None):
        return client.post(
            f"/api/build-sessions/{session_id}/modeling-batches",
            json={
                "client_batch_id": batch,
                "ontology_id": env.ontology_id,
                "idempotency_key": key,
                "mode": mode,
                "expected_model_revision": model_revision,
                "lease_token": token,
                "items": _seed_items(env.base),
            },
            headers=headers,
        )

    dry = submit("dry_run", "r3005-seed-dry", "r3005-seed-dry-key")
    assert dry.status_code == 200, dry.text
    assert dry.json()["attempt_status"] == "validated", dry.json()
    env.seeding_batch_ids.append(dry.json()["batch_id"])

    applied = submit(
        "apply_atomic", "r3005-seed-apply", "r3005-seed-apply-key", token=lease_token
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["attempt_status"] == "applied", applied.json()
    env.seeding_batch_ids.append(applied.json()["batch_id"])

    # Protection set via the model-scope management surface (R3.0-004).
    protected = client.post(
        f"/api/projects/{env.project_id}/protection-sets",
        json={
            "name": "PS_COST",
            "description": "spare-part cost module",
            "allowed_grants": [GRANT_COST],
            "members": [
                {"resource_iri": env.iri(f"metric/{METRIC_PARTCOST}")},
                {"resource_iri": env.iri(f"property/{PROP_STANDARD_COST}")},
                {"resource_iri": env.iri("table-mapping/tm-part")},
            ],
        },
        headers=headers,
    )
    assert protected.status_code == 201, protected.text


# ---------------------------------------------------------------------------
# Mechanical consumer chain (test-side rules, design §3.4)
# ---------------------------------------------------------------------------


def run_sql(sql: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ADAPTER)],
        input=json.dumps({"sql": sql}),
        capture_output=True,
        text=True,
        env={**os.environ, "R3005_SQL_ADAPTER_DSN": DSN},
        timeout=60,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 0 and payload["ok"] is True, payload
    return payload


class AuthorizedChain:
    """The deterministic consumer chain over authorized HTTP reads."""

    def __init__(self, env: ChainEnv, key_name: str):
        self.env = env
        self.headers = env.headers(key_name)

    # -- design step 2: locate resources via context:query ------------------

    def locate(self, terms: list[str], resource_types: list[str]) -> list[dict]:
        response = self.env.client.post(
            "/api/semantic/context:query",
            json={
                "project_id": self.env.project_id,
                "scope_mode": "project",
                "queries": [" ".join(terms)],
                "resource_types": resource_types,
                "search_mode": "lexical",
                "limit": 20,
            },
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        return response.json().get("primary_matches") or []

    # -- design step 2: exact reads via detail templates ---------------------

    def _read_model(self, model: str, entity_iri: str | None = None) -> dict | None:
        params = {"entity": entity_iri} if entity_iri else {}
        response = self.env.client.get(
            f"/api/semantic/ontologies/{self.env.ontology_id}/read-models/{model}",
            params=params,
            headers=self.headers,
        )
        if response.status_code != 200:
            return None
        return response.json()

    def metric_detail(self, metric_iri: str) -> dict | None:
        body = self._read_model("metric-detail", metric_iri)
        items = (body or {}).get("items") or []
        return items[0] if items else None

    def _mapping_rows(self, model: str) -> list[dict] | None:
        body = self._read_model(model)
        return None if body is None else (body.get("items") or [])

    def table_mappings(self) -> list[dict]:
        mappings = []
        for row in self._mapping_rows("table-mapping-list") or []:
            fields = row.get("detail_fields") or {}
            try:
                columns = json.loads(fields.get("column_mappings") or "[]")
            except json.JSONDecodeError:
                columns = []
            mappings.append(
                {
                    "iri": row["iri"],
                    "table": fields.get("table_name"),
                    "columns": [
                        (entry["property_iri"], entry["column"]) for entry in columns
                    ],
                }
            )
        return mappings

    def join_edges(self) -> list[dict]:
        edges = []
        for row in self._mapping_rows("join-mapping-list") or []:
            fields = row.get("detail_fields") or {}
            try:
                path = json.loads(fields.get("join_path") or "[]")
            except json.JSONDecodeError:
                path = []
            for step in path:
                edges.append(
                    {
                        "from_table": step["from_table"],
                        "to_table": step["to_table"],
                        "from_columns": step["from_columns"],
                        "to_columns": step["to_columns"],
                    }
                )
        return edges

    def enum_meanings(self) -> list[dict]:
        meanings = []
        for row in self._mapping_rows("enum-meaning-list") or []:
            fields = row.get("detail_fields") or {}
            meanings.append(
                {
                    "mapped_property": fields.get("mapped_property"),
                    "enum_value": fields.get("enum_value"),
                    "business_meaning": fields.get("business_meaning"),
                }
            )
        return meanings

    # -- design step 3/4: derivation with provenance closure -----------------

    @staticmethod
    def _property_index(mappings: list[dict]) -> dict[str, tuple[str, str]]:
        index: dict[str, tuple[str, str]] = {}
        for mapping in mappings:
            for property_iri, column in mapping["columns"]:
                index.setdefault(property_iri, (mapping["table"], column))
        return index

    def derive_metric_sql(self, metric_iri: str) -> dict:
        detail = self.metric_detail(metric_iri)
        if detail is None:
            return dict(UNCONFIRMABLE)
        fields = detail.get("detail_fields") or {}
        try:
            grain = json.loads(fields.get("grain") or "[]")
            filters = json.loads(fields.get("filters") or "[]")
        except json.JSONDecodeError:
            return dict(UNCONFIRMABLE)
        aggregation = fields.get("aggregation")
        if aggregation not in _AGGREGATIONS:
            return dict(UNCONFIRMABLE)

        mappings = self.table_mappings()
        if not mappings:
            return dict(UNCONFIRMABLE)
        prop_index = self._property_index(mappings)
        authorized_columns = {
            (mapping["table"], column)
            for mapping in mappings
            for _prop, column in mapping["columns"]
        }

        # Direct column mappings only (design §3.4): the measure property must
        # resolve to an authorized mapped column. Derived-expression metrics
        # (valueExpression) are consumer-interpreted and never mechanically
        # translated — no expression DSL exists on this path.
        measure_iri = fields.get("measure")
        used_columns: set[str] = set()
        null_guards: list[str] = []
        if not measure_iri or measure_iri not in prop_index:
            return dict(UNCONFIRMABLE)
        main_table, measure_column = prop_index[measure_iri]
        expression = f'a0."{measure_column}"'
        used_columns.add(measure_column)

        # filters: property IRI -> column, enum value validated via meanings
        meanings = self.enum_meanings()
        conditions = list(null_guards)
        filter_targets: list[tuple[str, str]] = []
        for entry in filters:
            field_iri = entry.get("field")
            operator = entry.get("operator")
            value = entry.get("value")
            if field_iri not in prop_index or operator != "eq":
                return dict(UNCONFIRMABLE)
            table, column = prop_index[field_iri]
            if table != main_table:
                return dict(UNCONFIRMABLE)
            if not any(
                meaning["mapped_property"] == field_iri
                and meaning["enum_value"] == value
                for meaning in meanings
            ):
                return dict(UNCONFIRMABLE)
            conditions.append(f"a0.\"{column}\" = '{value}'")
            used_columns.add(column)
            filter_targets.append((table, column))

        # grain: property IRIs -> columns, joined mechanically when remote
        grain_targets: list[tuple[str, str]] = []
        for grain_iri in grain:
            if grain_iri not in prop_index:
                return dict(UNCONFIRMABLE)
            grain_targets.append(prop_index[grain_iri])
        used_columns.update(column for _table, column in grain_targets)

        join_clauses, alias_of = self._join_path(main_table, grain_targets)
        if join_clauses is None:
            return dict(UNCONFIRMABLE)

        grain_selects = [f'{alias_of[table]}."{column}"' for table, column in grain_targets]
        select_list = [
            *grain_selects,
            f"{_AGGREGATIONS[aggregation]}({expression}) AS metric_value",
        ]
        sql = f"SELECT {', '.join(select_list)}\nFROM {main_table} a0"
        if join_clauses:
            sql += "\n" + "\n".join(join_clauses)
        if conditions:
            sql += "\nWHERE " + " AND ".join(conditions)
        if grain_selects:
            sql += "\nGROUP BY " + ", ".join(grain_selects)
            sql += "\nORDER BY " + ", ".join(grain_selects)

        # provenance closure: every identifier used by the SQL appeared in
        # an authorized detail_fields response
        used_tables = set(alias_of)
        known_tables = {mapping["table"] for mapping in mappings}
        assert used_tables <= known_tables
        projection_targets = grain_targets + filter_targets
        for table, column in projection_targets:
            assert (table, column) in authorized_columns
        return {
            "status": "ok",
            "sql": sql,
            "provenance": {
                "tables": sorted(used_tables),
                "columns": sorted(used_columns),
                "metric_iri": metric_iri,
            },
        }

    def _join_path(
        self, main_table: str, grain_targets: list[tuple[str, str]]
    ) -> tuple[list[str] | None, dict[str, str] | None]:
        """BFS over authorized JoinMapping steps; returns (clauses, aliases)."""
        adjacency: dict[str, list[dict]] = {}
        for edge in self.join_edges():
            adjacency.setdefault(edge["from_table"], []).append(edge)
            adjacency.setdefault(edge["to_table"], []).append(edge)
        needed = {table for table, _column in grain_targets if table != main_table}
        alias_of = {main_table: "a0"}
        clauses: list[str] = []
        for target in sorted(needed):
            if target in alias_of:
                continue
            path = self._bfs(adjacency, main_table, target)
            if path is None:
                return None, None
            current = main_table
            for step in path:
                if step["from_table"] == current:
                    left, right = step["from_table"], step["to_table"]
                    left_columns, right_columns = step["from_columns"], step["to_columns"]
                else:
                    left, right = step["to_table"], step["from_table"]
                    left_columns, right_columns = step["to_columns"], step["from_columns"]
                if right in alias_of:
                    current = right
                    continue
                alias = f"a{len(alias_of)}"
                alias_of[right] = alias
                on = " AND ".join(
                    f"{alias}.\"{right_columns[index]}\" = "
                    f"{alias_of[left]}.\"{left_columns[index]}\""
                    for index in range(len(left_columns))
                )
                clauses.append(f"JOIN {right} {alias} ON {on}")
                current = right
        return clauses, alias_of

    @staticmethod
    def _bfs(adjacency: dict[str, list[dict]], start: str, goal: str) -> list[dict] | None:
        queue = deque([(start, [])])
        seen = {start}
        while queue:
            node, path = queue.popleft()
            if node == goal:
                return path
            for edge in adjacency.get(node, []):
                neighbor = (
                    edge["to_table"] if edge["from_table"] == node else edge["from_table"]
                )
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, [*path, edge]))
        return None

    # -- Q1 shape: enum-validated count over the mapped class table ----------

    def derive_resolved_count_sql(self, business_meaning: str) -> dict:
        matches = self.locate(["工单", business_meaning], ["mapping"])
        enum_hits = [
            match
            for match in matches
            if (match.get("data") or {}).get("business_meaning") == business_meaning
        ]
        if not enum_hits:
            return dict(UNCONFIRMABLE)
        data = enum_hits[0]["data"]
        mapped_property = data.get("mapped_property")
        enum_value = data.get("enum_value")
        prop_index = self._property_index(self.table_mappings())
        if mapped_property not in prop_index:
            return dict(UNCONFIRMABLE)
        table, column = prop_index[mapped_property]
        return {
            "status": "ok",
            "sql": f"SELECT count(*) FROM {table} WHERE \"{column}\" = '{enum_value}'",
            "provenance": {"tables": [table], "columns": [column]},
        }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_seeding_batches_applied_and_registered_as_baseline(chain_env):
    """F6 baseline: the only Modeling Batches are the seeding dry-run and
    apply batches (the registered baseline); exactly one Build Session."""
    assert len(chain_env.seeding_batch_ids) == 2
    with chain_env.client.app.state.session_factory() as session:
        batches = session.scalars(select(ModelingBatchModel.id)).all()
        sessions = session.scalars(select(BuildSessionModel.id)).all()
    assert set(batches) == set(chain_env.seeding_batch_ids)
    assert len(list(sessions)) == 1


def test_s3_authorized_chain_resolved_work_order_count(chain_env):
    chain = AuthorizedChain(chain_env, "grant")
    result = chain.derive_resolved_count_sql("已完成工单")
    assert result["status"] == "ok", result
    derived = run_sql(result["sql"])
    baseline = run_sql(
        "SELECT count(*) FROM industrial_service_v3.work_orders "
        "WHERE status = 'RESOLVED'"
    )
    assert derived["rows"] == baseline["rows"]
    assert derived["rows"][0][0] > 0


def test_s3_authorized_chain_derived_metric_read_closure(chain_env):
    """Q2 derived metric (avg resolutionDuration): the mechanical chain only
    verifies READ CLOSURE (design §3.4) — the authorized read surface returns
    the complete valueExpression text plus every mapping it references. The
    expression -> SQL translation itself is consumer interpretation, verified
    numerically by the S5 real-LLM smoke round, never by a mechanical
    translator (no expression DSL exists on this path)."""
    chain = AuthorizedChain(chain_env, "grant")
    metric_iri = chain_env.iri(f"metric/{METRIC_MTTR}")

    matches = chain.locate(["平均解决时长"], ["metric"])
    assert any(m["iri"] == metric_iri for m in matches), matches
    # context:query metric candidates intentionally omit value_expression
    # (R3.0-003 frozen surface); the text comes from the metric-detail template.
    assert "value_expression" not in (matches[0].get("data") or {})

    detail = chain.metric_detail(metric_iri)
    assert detail, "metric-detail must return the metric to an authorized principal"
    fields = detail.get("detail_fields") or {}
    text = fields.get("value_expression") or ""
    # complete frozen business wording: resolution = resolved_at - reported_at,
    # reported_at reached through the incidents join
    assert "resolved_at" in text and "reported_at" in text
    assert "work_orders" in text and "incidents" in text

    # read closure: every mapping referenced by the derived metric resolves
    # on the authorized read surface
    mappings = chain.table_mappings()
    prop_index = chain._property_index(mappings)
    authorized_columns = {
        (mapping["table"], column) for mapping in mappings for _prop, column in mapping["columns"]
    }
    assert (f"{SCHEMA}.work_orders", "resolved_at") in authorized_columns
    assert (f"{SCHEMA}.incidents", "reported_at") in authorized_columns
    grain = json.loads(fields.get("grain") or "[]")
    assert len(grain) == 1 and grain[0] in prop_index
    filters = json.loads(fields.get("filters") or "[]")
    assert filters and filters[0]["field"] in prop_index

    # join closure: authorized JoinMappings connect the expression/grain span
    # work_orders -> incidents (reported_at) -> assets -> equipment_models
    span = {frozenset((edge["from_table"], edge["to_table"])) for edge in chain.join_edges()}
    assert frozenset((f"{SCHEMA}.work_orders", f"{SCHEMA}.incidents")) in span
    assert frozenset((f"{SCHEMA}.incidents", f"{SCHEMA}.assets")) in span
    assert frozenset((f"{SCHEMA}.assets", f"{SCHEMA}.equipment_models")) in span

    # the mechanical derivation does NOT translate the derived expression:
    # the measure property has no direct column mapping, so the mechanical
    # chain terminates unconfirmable instead of guessing SQL (design §3.4)
    assert chain.derive_metric_sql(metric_iri) == UNCONFIRMABLE


def test_s4_authorized_cost_metric_chain(chain_env):
    chain = AuthorizedChain(chain_env, "grant")
    located = chain.locate(["备件平均标准成本"], ["metric"])
    assert any(m["iri"] == chain_env.iri(f"metric/{METRIC_PARTCOST}") for m in located)

    result = chain.derive_metric_sql(chain_env.iri(f"metric/{METRIC_PARTCOST}"))
    assert result["status"] == "ok", result
    derived = run_sql(result["sql"])
    baseline = run_sql(f"SELECT AVG(standard_cost) FROM {SCHEMA}.spare_parts")
    assert len(derived["rows"]) == 1
    assert float(derived["rows"][0][0]) == pytest.approx(
        float(baseline["rows"][0][0]), rel=1e-9
    )


def _forbidden_substrings(env: ChainEnv) -> list[str]:
    return [
        "spare_parts",
        "standard_cost",
        "standardCost",
        "cost-visibility",
        "protection",
        "PS_COST",
        METRIC_PARTCOST,
        "备件平均标准成本",
        env.iri("table-mapping/tm-part"),
    ]


def test_b4_nogrant_cost_chain_is_uniformly_unconfirmable(chain_env):
    chain = AuthorizedChain(chain_env, "nogrant")
    metric_iri = chain_env.iri(f"metric/{METRIC_PARTCOST}")

    protected = chain.derive_metric_sql(metric_iri)
    nonexistent = chain.derive_metric_sql(chain_env.iri("metric/never-created-metric"))
    assert protected == UNCONFIRMABLE
    assert nonexistent == UNCONFIRMABLE
    assert protected == nonexistent  # indistinguishable terminal states

    forbidden = _forbidden_substrings(chain_env)
    serialized = json.dumps([protected, nonexistent], ensure_ascii=False)
    for substring in forbidden:
        assert substring not in serialized

    # wide-scope reads stay trace-free for the unauthorized principal
    listing = chain._read_model("table-mapping-list")
    listing_text = json.dumps(listing, ensure_ascii=False)
    for substring in forbidden:
        assert substring not in listing_text
    matches = chain.locate(["备件", "标准成本"], ["metric", "mapping"])
    matches_text = json.dumps(matches, ensure_ascii=False)
    for substring in forbidden:
        assert substring not in matches_text

    # the same principal still answers unprotected questions normally
    ok = chain.derive_resolved_count_sql("已完成工单")
    assert ok["status"] == "ok"


def test_b5_unmapped_concept_is_unconfirmable(chain_env):
    chain = AuthorizedChain(chain_env, "grant")
    matches = chain.locate(["仓库", "库存变动"], ["mapping"])
    # the gap fixture: warehouses/inventory_movements have no mappings at all
    serialized = json.dumps(matches, ensure_ascii=False)
    assert "warehouses" not in serialized
    assert "inventory_movements" not in serialized

    known_tables = {mapping["table"] for mapping in chain.table_mappings()}
    assert f"{SCHEMA}.warehouses" not in known_tables
    assert f"{SCHEMA}.inventory_movements" not in known_tables

    # the mechanical chain has no mapping row to close provenance on
    prop_index = chain._property_index(chain.table_mappings())
    assert not any("仓库" in iri or "库存" in iri for iri in prop_index)


def test_f6_no_new_modeling_activity_during_consumption(chain_env):
    """After the seeding batch, consumption chains create no Build Session /
    Modeling Batch (A6 accounting scope: post-seeding only)."""
    factory = chain_env.client.app.state.session_factory
    with factory() as session:
        before_batches = len(session.scalars(select(ModelingBatchModel.id)).all())
        before_sessions = len(session.scalars(select(BuildSessionModel.id)).all())

    for key in ("grant", "nogrant"):
        chain = AuthorizedChain(chain_env, key)
        assert chain.derive_resolved_count_sql("已完成工单")["status"] == "ok"
        # grant: cost metric resolves; nogrant: uniformly unconfirmable —
        # either way no modeling activity is triggered
        chain.derive_metric_sql(chain_env.iri(f"metric/{METRIC_MTTR}"))
        chain.derive_metric_sql(chain_env.iri(f"metric/{METRIC_PARTCOST}"))

    with factory() as session:
        after_batches = len(session.scalars(select(ModelingBatchModel.id)).all())
        after_sessions = len(session.scalars(select(BuildSessionModel.id)).all())
    assert (after_batches, after_sessions) == (before_batches, before_sessions)
