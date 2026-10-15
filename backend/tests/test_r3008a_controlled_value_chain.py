"""R3.0-008A controlled-value L1/L2/L3 chain tests.

In-process FastAPI ``TestClient`` over the real platform control plane and a
real Oxigraph RDF store — never the live 8001 service — following the
R3.0-005 precedent (``test_r3005_authorized_sql_chain.py``). The fixture
seeds the L1/L2/L3 controlled-value shapes through the real product write
path (``KEY_MODEL`` -> Build Session -> applied Modeling Batch) on
top of the R3.0-001 ``industrial_service_v3`` baseline tables/columns; the
domain vocabulary (缺料 / PART_SHORTAGE / WAITING_PARTS ...) lives only in
test data and assertions, never in product code.

Gating: requires ``RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1`` (running local
Oxigraph). ``R3005_SQL_ADAPTER_DSN`` (scenario PostgreSQL) is optional: when
set, the S5 closed-loop SQL is executed and compared against the independent
hard-coded baseline (WO-1001, WO-1008); otherwise the SQL text plus
authorized provenance is asserted and the skip is recorded in the report.
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

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_OXIGRAPH_SPARQL_RUNNER_TESTS") != "1",
    reason="requires a running local Oxigraph server (RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1)",
)

ADAPTER = (
    Path(__file__).resolve().parents[2] / "scripts" / "r3-0-005" / "sql_exec_adapter.py"
)
DSN = os.environ.get("R3005_SQL_ADAPTER_DSN", "")

SCHEMA = "industrial_service_v3"
GRANT_DELAY = "delay-visibility"

UNCONFIRMABLE = {"status": "unconfirmable"}

# Fixture vocabulary (test data only; design §4.3)
CLASS_WORK_ORDER = "work-order"
CLASS_DELAY_REASON = "delay-reason"
CLASS_SPARE_PART = "spare-part"

REL_HAS_DELAY_EVENT = "has-delay-event"
REL_BELONGS_TO = "belongs-to"

PROP_WORK_ORDER_ID = "workOrderId"
PROP_WORK_ORDER_NUMBER = "workOrderNumber"
PROP_STATUS = "status"
PROP_DELAY_EVENT_ID = "delayEventId"
PROP_DELAY_CAUSE = "delayCause"
PROP_DELAY_WORK_ORDER_REF = "delayWorkOrderRef"
PROP_PART_ID = "partId"
PROP_CURRENCY = "currency"

ENTITY_PART_SHORTAGE = "part-shortage"
ENTITY_SUPPLY_CHAIN_ISSUE = "supply-chain-issue"

EM_CAUSE_PS = "em-cause-ps"
EM_STATUS_WP = "em-status-wp"
EM_STATUS_RESOLVED = "em-status-resolved"

TABLE_WO = f"{SCHEMA}.work_orders"
TABLE_DELAY = f"{SCHEMA}.work_order_delay_events"
TABLE_PART = f"{SCHEMA}.spare_parts"

EXPECTED_S5_SQL = (
    f"SELECT wo.work_order_number FROM {TABLE_WO} wo "
    f"JOIN {TABLE_DELAY} de ON de.work_order_id = wo.work_order_id "
    "WHERE de.cause_code = 'PART_SHORTAGE'"
)
S5_BASELINE_ROWS = [["WO-1001"], ["WO-1008"]]


def _seed_items(base: str) -> list[dict]:
    """Fixture items; every payload IRI is absolute (compiler requirement)."""

    def item(item_id: str, kind: str, payload: dict) -> dict:
        # ``ontology_id`` is a forbidden target field in Modeling item
        # payloads; the server injects it from the batch submit envelope.
        return {
            "client_item_id": item_id,
            "command_kind": kind,
            "payload": payload,
            "rationale": "R3.0-008A controlled-value fixture",
            "evidence": [
                {
                    "document_name": "schema-ddl.md",
                    "excerpt": f"{item_id} is grounded in the industrial_service_v3 schema.",
                }
            ],
        }

    def class_item(class_id: str, name: str) -> dict:
        return item(f"class-{class_id}", "create_class", {"class_id": class_id, "name": name})

    def relation_type_item(relation_id: str, name: str, source: str, target: str) -> dict:
        return item(
            f"reltype-{relation_id}",
            "create_relation_type",
            {
                "relation_type_id": relation_id,
                "name": name,
                "source_class_id": source,
                "target_class_id": target,
            },
        )

    def property_item(class_id: str, property_id: str, name: str) -> dict:
        return item(
            f"prop-{property_id}",
            "create_property",
            {"class_id": class_id, "property_id": property_id, "name": name, "datatype": "string"},
        )

    prop = lambda name: f"{base}property/{name}"  # noqa: E731

    def column(property_name: str, column_name: str, role: str | None = None) -> dict:
        entry = {"property_iri": prop(property_name), "column": column_name}
        if role:
            entry["role"] = role
        return entry

    def table_mapping_item(item_id: str, class_id: str, table_name: str, columns: list[dict]):
        return item(
            item_id,
            "create_table_mapping",
            {
                "table_mapping_id": item_id,
                "name": f"{table_name} mapping",
                "mapped_class_iri": f"{base}class/{class_id}",
                "table_name": table_name,
                "column_mappings": columns,
                "schema_source": "industrial-service-v3-schema-2026-09-03",
            },
        )

    return [
        class_item(CLASS_WORK_ORDER, "WorkOrder"),
        class_item(CLASS_DELAY_REASON, "DelayReason"),
        class_item(CLASS_SPARE_PART, "SparePart"),
        relation_type_item(
            REL_HAS_DELAY_EVENT, "hasDelayEvent", CLASS_WORK_ORDER, CLASS_DELAY_REASON
        ),
        relation_type_item(REL_BELONGS_TO, "belongsTo", CLASS_DELAY_REASON, CLASS_DELAY_REASON),
        property_item(CLASS_WORK_ORDER, PROP_WORK_ORDER_ID, "workOrderId"),
        property_item(CLASS_WORK_ORDER, PROP_WORK_ORDER_NUMBER, "workOrderNumber"),
        property_item(CLASS_WORK_ORDER, PROP_STATUS, "status"),
        property_item(CLASS_DELAY_REASON, PROP_DELAY_EVENT_ID, "delayEventId"),
        property_item(CLASS_DELAY_REASON, PROP_DELAY_CAUSE, "delayCause"),
        property_item(CLASS_DELAY_REASON, PROP_DELAY_WORK_ORDER_REF, "delayWorkOrderRef"),
        property_item(CLASS_SPARE_PART, PROP_PART_ID, "partId"),
        property_item(CLASS_SPARE_PART, PROP_CURRENCY, "currency"),
        # L3 carrier: first-class business node + a business relation so the
        # node participates in relation recall (fixture §3.2)
        item(
            f"entity-{ENTITY_PART_SHORTAGE}",
            "create_entity",
            {
                "entity_id": ENTITY_PART_SHORTAGE,
                "class_iri_or_legacy_id": f"{base}class/{CLASS_DELAY_REASON}",
                "label": "缺料",
            },
        ),
        item(
            f"entity-{ENTITY_SUPPLY_CHAIN_ISSUE}",
            "create_entity",
            {
                "entity_id": ENTITY_SUPPLY_CHAIN_ISSUE,
                "class_iri_or_legacy_id": f"{base}class/{CLASS_DELAY_REASON}",
                "label": "供应链问题",
            },
        ),
        item(
            "rel-belongs-to",
            "create_relation",
            {
                "source_entity_iri": f"{base}entity/{ENTITY_PART_SHORTAGE}",
                "relation_type_iri": f"{base}relation-type/{REL_BELONGS_TO}",
                "target_entity_iri": f"{base}entity/{ENTITY_SUPPLY_CHAIN_ISSUE}",
            },
        ),
        table_mapping_item(
            "tm-wo",
            CLASS_WORK_ORDER,
            TABLE_WO,
            [
                column(PROP_WORK_ORDER_ID, "work_order_id", "business_key"),
                column(PROP_WORK_ORDER_NUMBER, "work_order_number"),
                column(PROP_STATUS, "status"),
            ],
        ),
        table_mapping_item(
            "tm-delay",
            CLASS_DELAY_REASON,
            TABLE_DELAY,
            [
                column(PROP_DELAY_EVENT_ID, "delay_event_id", "business_key"),
                column(PROP_DELAY_CAUSE, "cause_code"),
                column(PROP_DELAY_WORK_ORDER_REF, "work_order_id"),
            ],
        ),
        table_mapping_item(
            "tm-part",
            CLASS_SPARE_PART,
            TABLE_PART,
            [
                column(PROP_PART_ID, "part_id", "business_key"),
                column(PROP_CURRENCY, "currency"),
            ],
        ),
        item(
            "jm-wo-delay",
            "create_join_mapping",
            {
                "join_mapping_id": "jm-wo-delay",
                "name": "work order has delay event",
                "relation_type_iri": f"{base}relation-type/{REL_HAS_DELAY_EVENT}",
                "join_direction": "forward",
                "join_path": [
                    {
                        "from_table": TABLE_WO,
                        "to_table": TABLE_DELAY,
                        "from_columns": ["work_order_id"],
                        "to_columns": ["work_order_id"],
                    }
                ],
                "schema_source": "industrial-service-v3-schema-2026-09-03",
            },
        ),
        # L3: two EnumValueMeanings pointing at the same first-class node (A2)
        item(
            EM_CAUSE_PS,
            "create_enum_meaning",
            {
                "enum_meaning_id": EM_CAUSE_PS,
                "name": "delayCause PART_SHORTAGE 缺料",
                "property_iri": prop(PROP_DELAY_CAUSE),
                "enum_value": "PART_SHORTAGE",
                "business_meaning": "缺料",
                "semantic_value": f"{base}entity/{ENTITY_PART_SHORTAGE}",
                "schema_source": "industrial-service-v3-schema-2026-09-03",
            },
        ),
        item(
            EM_STATUS_WP,
            "create_enum_meaning",
            {
                "enum_meaning_id": EM_STATUS_WP,
                "name": "status WAITING_PARTS 缺料待料",
                "property_iri": prop(PROP_STATUS),
                "enum_value": "WAITING_PARTS",
                "business_meaning": "缺料待料",
                "semantic_value": f"{base}entity/{ENTITY_PART_SHORTAGE}",
                "schema_source": "industrial-service-v3-schema-2026-09-03",
            },
        ),
        # L2: no semantic_value
        item(
            EM_STATUS_RESOLVED,
            "create_enum_meaning",
            {
                "enum_meaning_id": EM_STATUS_RESOLVED,
                "name": "status RESOLVED 已完成",
                "property_iri": prop(PROP_STATUS),
                "enum_value": "RESOLVED",
                "business_meaning": "已完成",
                "schema_source": "industrial-service-v3-schema-2026-09-03",
            },
        ),
    ]


class ChainEnv:
    def __init__(self, client, project_id, ontology_id,  base, keys, store):
        self.client = client
        self.project_id = project_id
        self.ontology_id = ontology_id
        self.base = base
        self.keys = keys
        self.store = store
        self.seeding_batch_ids: list[str] = []
        self.variant_batch_ids: list[str] = []

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
    graph_prefix = f"https://r3008a.test/{token}/graph/"
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
            ProjectModel(
                id=project_id, name="R3.0-008A", normalized_label=f"r3008a{token[:8]}"
            )
        )
        ontology = OntologyModel(id=ontology_id, project_id=project_id, name="R3.0-008A O_m")
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
                {"project_id": project_id, "scopes": ["read"], "semantic_grants": [GRANT_DELAY]},
            ),
            ("nogrant", {"project_id": project_id, "scopes": ["read"]}),
        ):
            _record, plaintext = create_api_key(
                session, name=f"r3008a-{name}-{token[:6]}", **kwargs
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
        env = ChainEnv(client, project_id, ontology_id, ontology_id, base, keys, store)
        _seed_fixture(env, settings, model_revision)
        yield env

    # Cleanup: drop the token-scoped Oxigraph graphs; the SQLite control
    # plane (project, keys, graph sets) dies with the in-memory engine.
    for category in ("ontology", "data", "shapes", "policy"):
        store.update_sparql(f"DROP SILENT GRAPH <{graph_prefix}{category}/{ontology_id}>")
    engine.dispose()


def _submit_batch(
    env: ChainEnv,
    settings: Settings,
    session_id: str,
    model_revision: int,
    items: list[dict],
    *,
    batch: str,
    key: str,
    mode: str,
    lease_token: str | None = None,
):
    return env.client.post(
        f"/api/build-sessions/{session_id}/modeling-batches",
        json={
            "client_batch_id": batch,
            "ontology_id": env.ontology_id,
            "idempotency_key": key,
            "mode": mode,
            "expected_model_revision": model_revision,
            "lease_token": lease_token,
            "items": items,
        },
        headers=env.headers("model"),
    )


def _seed_fixture(env: ChainEnv, settings: Settings, model_revision: int) -> None:
    created = env.client.post(
        f"/api/projects/{env.project_id}/build-sessions",
        json={"client_session_id": "r3008a-seed"},
        headers=env.headers("model"),
    )
    assert created.status_code in {200, 201}, created.text
    session_id = created.json()["id"]

    lease = env.client.post(
        f"/api/build-sessions/{session_id}/ontology-leases/{env.ontology_id}:acquire",
        json={"client_request_id": "r3008a-lease-1", "expected_session_revision": 1},
        headers=env.headers("model"),
    )
    assert lease.status_code == 200, lease.text
    lease_token = lease.json()["lease_token"]

    applied = _submit_batch(
        env,
        settings,
        session_id,
        model_revision,
        _seed_items(env.base),
        batch="r3008a-seed-apply",
        key="r3008a-seed-apply-key",
        mode="apply_atomic",
        lease_token=lease_token,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["attempt_status"] == "applied", applied.json()
    env.seeding_batch_ids.append(applied.json()["batch_id"])
    env.seed_session_id = session_id
    env.seed_lease_token = lease_token

    # Protection set via the model-scope management surface (R3.0-004):
    # the only protected member is the L3 node itself.
    protected = env.client.post(
        f"/api/projects/{env.project_id}/protection-sets",
        json={
            "name": "PS_DELAY",
            "description": "delay cause module",
            "allowed_grants": [GRANT_DELAY],
            "members": [
                {"resource_iri": env.iri(f"entity/{ENTITY_PART_SHORTAGE}")},
            ],
        },
        headers=env.headers("model"),
    )
    assert protected.status_code == 201, protected.text


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


class ControlledValueChain:
    """Deterministic consumer chain over authorized HTTP reads (test-side
    mechanical rules, design §3.6); no product code."""

    def __init__(self, env: ChainEnv, key_name: str):
        self.env = env
        self.headers = env.headers(key_name)

    def locate(self, terms: list[str], resource_types: list[str]) -> list[dict]:
        response = self.env.client.post(
            "/api/semantic/context:query",
            json={
                "project_id": self.env.project_id,
                "scope_mode": "project",
                "queries": [" ".join(terms)],
                "resource_types": resource_types,
                "search_mode": "lexical",
                "limit": 30,
            },
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        return response.json().get("primary_matches") or []

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

    def _mapping_rows(self, model: str) -> list[dict]:
        body = self._read_model(model)
        return (body or {}).get("items") or []

    def enum_meanings(self) -> list[dict]:
        meanings = []
        for row in self._mapping_rows("enum-meaning-list"):
            fields = row.get("detail_fields") or {}
            meanings.append(
                {
                    "iri": row["iri"],
                    "mapped_property": fields.get("mapped_property"),
                    "enum_value": fields.get("enum_value"),
                    "business_meaning": fields.get("business_meaning"),
                    "semantic_value": fields.get("semantic_value"),
                }
            )
        return meanings

    def enum_meaning_detail(self, entity_iri: str) -> dict | None:
        # the detail template binds ?enum_meaning to VALUES <{entity_iri}>,
        # so the entity query parameter is mandatory here
        rows = (self._read_model("enum-meaning-detail", entity_iri=entity_iri) or {}).get(
            "items"
        ) or []
        for row in rows:
            if row["iri"] == entity_iri:
                return row
        return rows[0] if rows else None

    def table_mappings(self) -> list[dict]:
        mappings = []
        for row in self._mapping_rows("table-mapping-list"):
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
        for row in self._mapping_rows("join-mapping-list"):
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

    @staticmethod
    def property_index(mappings: list[dict]) -> dict[str, tuple[str, str]]:
        index: dict[str, tuple[str, str]] = {}
        for mapping in mappings:
            for property_iri, column in mapping["columns"]:
                index.setdefault(property_iri, (mapping["table"], column))
        return index

    # -- S3/S4/S5: L3 recall + semantic_value linkage -----------------------

    def l3_resource_candidates(self, term: str) -> list[dict]:
        vocab_prefix = f"{self.env.base}vocab/"
        candidates = []
        for match in self.locate([term], ["instance", "mapping"]):
            if match.get("kind") != "instance":
                continue
            types = (match.get("data") or {}).get("rdf_types") or []
            if types and not any(str(value).startswith(vocab_prefix) for value in types):
                candidates.append(match)
        return candidates

    def linked_enum_candidates(self, term: str) -> list[dict]:
        """Mapping candidates in the same response whose data.semantic_value
        equals a recalled L3 candidate IRI."""
        l3_iris = {match["iri"] for match in self.l3_resource_candidates(term)}
        linked = []
        for match in self.locate([term], ["instance", "mapping"]):
            if match.get("kind") != "mapping":
                continue
            if (match.get("data") or {}).get("semantic_value") in l3_iris:
                linked.append(match)
        return linked

    def business_meaning_candidates(self, term: str) -> list[dict]:
        return [
            match
            for match in self.locate([term], ["mapping"])
            if (match.get("data") or {}).get("business_meaning")
        ]

    def derive_enum_filter_sql(self, enum_candidate: dict) -> str | None:
        """Mechanical per-enum derivation: mapped property -> authorized
        column -> table; single-table filter SQL."""
        data = enum_candidate.get("data") or {}
        prop_index = self.property_index(self.table_mappings())
        mapped_property = data.get("mapped_property")
        enum_value = data.get("enum_value")
        if not mapped_property or not enum_value or mapped_property not in prop_index:
            return None
        table, column = prop_index[mapped_property]
        return f"SELECT count(*) FROM {table} WHERE \"{column}\" = '{enum_value}'"

    def derive_delay_orders_sql(self, term: str = "缺料") -> dict:
        """Representative question: orders delayed because of the recalled
        business value. Mechanically: an L3 candidate recalled by the term, a
        mapping candidate linked via semantic_value whose enum-encoded column
        lives on a table other than the order table (the delay encoding), a
        join to the order table via authorized JoinMappings, and the order
        number projection. Any missing link -> uniform unconfirmable."""
        order_table = TABLE_WO
        mappings = self.table_mappings()
        prop_index = self.property_index(mappings)
        l3 = self.l3_resource_candidates(term)
        linked = self.linked_enum_candidates(term)
        if not l3 or not linked:
            return dict(UNCONFIRMABLE)
        cause_links = []
        for candidate in linked:
            mapped_property = (candidate.get("data") or {}).get("mapped_property")
            if mapped_property in prop_index and prop_index[mapped_property][0] != order_table:
                cause_links.append(candidate)
        if not cause_links:
            return dict(UNCONFIRMABLE)
        candidate = cause_links[0]
        data = candidate["data"]
        enum_value = data.get("enum_value")
        delay_table, delay_column = prop_index[data["mapped_property"]]
        projection = prop_index.get(self.env.iri(f"property/{PROP_WORK_ORDER_NUMBER}"))
        if not enum_value or not projection or projection[0] != order_table:
            return dict(UNCONFIRMABLE)

        # join closure via authorized JoinMappings (BFS, R3.0-005 rule)
        adjacency: dict[str, list[dict]] = {}
        for edge in self.join_edges():
            adjacency.setdefault(edge["from_table"], []).append(edge)
            adjacency.setdefault(edge["to_table"], []).append(edge)
        queue = deque([(order_table, [])])
        seen = {order_table}
        path = None
        while queue:
            node, steps = queue.popleft()
            if node == delay_table:
                path = steps
                break
            for edge in adjacency.get(node, []):
                neighbor = edge["to_table"] if edge["from_table"] == node else edge["from_table"]
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, [*steps, edge]))
        if path is None:
            return dict(UNCONFIRMABLE)

        alias_map = {
            "work_orders": "wo",
            "work_order_delay_events": "de",
            "spare_parts": "sp",
        }

        def alias_for(table: str) -> str:
            return alias_map.get(table.split(".")[-1], table.split(".")[-1])

        join_clauses = []
        current_table = order_table
        current_alias = alias_for(order_table)
        for step in path:
            if step["from_table"] == current_table:
                left_columns, right_columns = step["from_columns"], step["to_columns"]
                right_table = step["to_table"]
            else:
                left_columns, right_columns = step["to_columns"], step["from_columns"]
                right_table = step["from_table"]
            right_alias = alias_for(right_table)
            on_clause = " AND ".join(
                f"{right_alias}.{right_columns[index]} = {current_alias}.{left_columns[index]}"
                for index in range(len(left_columns))
            )
            join_clauses.append(f"JOIN {right_table} {right_alias} ON {on_clause}")
            current_table, current_alias = right_table, right_alias
        filter_alias = current_alias
        sql = (
            f"SELECT wo.{projection[1]} FROM {order_table} wo "
            + " ".join(join_clauses)
            + f" WHERE {filter_alias}.{delay_column} = '{enum_value}'"
        )
        # provenance closure: every identifier appeared in authorized reads
        authorized_tables = {mapping["table"] for mapping in mappings}
        assert order_table in authorized_tables and delay_table in authorized_tables
        return {"status": "ok", "sql": sql}


def _assert_forbidden_absent(env: ChainEnv, serialized: str) -> None:
    for substring in (
        "part-shortage",
        "PartShortage",
        "缺料",
        "PART_SHORTAGE",
        "WAITING_PARTS",
        GRANT_DELAY,
        "protection",
        "PS_DELAY",
    ):
        assert substring not in serialized, substring


# ---------------------------------------------------------------------------
# Fixture baseline / S1 (L1 literal chain)
# ---------------------------------------------------------------------------


def test_graph_set_contains_asserted_data_member(chain_env):
    """Fixture precondition (design hypothesis 2 / review note 3): the default
    graph set carries an asserted_data role member graph, proven end to end
    by the S3 recall below."""
    with chain_env.client.app.state.session_factory() as session:
        roles = session.scalars(
            select(SemanticGraphSetMemberModel.role).where(
                SemanticGraphSetMemberModel.ontology_id == chain_env.ontology_id
            )
        ).all()
    assert "asserted_data" in roles


def test_s1_l1_literal_chain(chain_env):
    chain = ControlledValueChain(chain_env, "grant")
    mappings = chain.table_mappings()
    prop_index = chain.property_index(mappings)
    currency_iri = chain_env.iri(f"property/{PROP_CURRENCY}")
    assert prop_index[currency_iri] == (TABLE_PART, "currency")
    # L1 form: the confirmed literal is used directly; no EnumValueMeaning
    # and no value node exists for currency
    assert not any(
        meaning["mapped_property"] == currency_iri for meaning in chain.enum_meanings()
    )
    sql = f"SELECT count(*) FROM {TABLE_PART} WHERE currency = 'CNY'"
    assert TABLE_PART in {mapping["table"] for mapping in mappings}
    if DSN:
        assert run_sql(sql)["rows"][0][0] > 0


# ---------------------------------------------------------------------------
# S2 (L2 enum chain) / S3 (L3 projection and recall) / S4 (double reference)
# ---------------------------------------------------------------------------


def test_s2_l2_enum_chain_has_no_semantic_value_key(chain_env):
    chain = ControlledValueChain(chain_env, "grant")
    matches = chain.locate(["已完成"], ["mapping"])
    hits = [
        match
        for match in matches
        if (match.get("data") or {}).get("business_meaning") == "已完成"
    ]
    assert hits, matches
    data = hits[0]["data"]
    assert data["enum_value"] == "RESOLVED"
    assert data["mapped_property"] == chain_env.iri(f"property/{PROP_STATUS}")
    assert "semantic_value" not in data
    prop_index = chain.property_index(chain.table_mappings())
    table, column = prop_index[data["mapped_property"]]
    sql = chain.derive_enum_filter_sql(hits[0])
    assert sql == f"SELECT count(*) FROM {table} WHERE \"{column}\" = 'RESOLVED'"
    detail = chain.enum_meaning_detail(hits[0]["iri"])
    fields = (detail or {}).get("detail_fields") or {}
    assert fields.get("semantic_value") is None


def test_s3_l3_projection_and_recall(chain_env):
    chain = ControlledValueChain(chain_env, "grant")
    part_shortage_iri = chain_env.iri(f"entity/{ENTITY_PART_SHORTAGE}")

    resource = chain.l3_resource_candidates("缺料")
    assert any(match["iri"] == part_shortage_iri for match in resource)
    types = next(
        match["data"]["rdf_types"]
        for match in resource
        if match["iri"] == part_shortage_iri
    )
    assert chain_env.iri(f"class/{CLASS_DELAY_REASON}") in types

    linked = chain.linked_enum_candidates("缺料")
    linked_iris = {match["iri"] for match in linked}
    assert {
        chain_env.iri(f"enum-meaning/{EM_CAUSE_PS}"),
        chain_env.iri(f"enum-meaning/{EM_STATUS_WP}"),
    } <= linked_iris
    for match in linked:
        assert match["data"]["semantic_value"] == part_shortage_iri

    detail_rows = {
        row["iri"]: (row.get("detail_fields") or {}).get("semantic_value")
        for row in chain._mapping_rows("enum-meaning-list")
    }
    assert detail_rows[chain_env.iri(f"enum-meaning/{EM_CAUSE_PS}")] == part_shortage_iri
    assert detail_rows[chain_env.iri(f"enum-meaning/{EM_STATUS_WP}")] == part_shortage_iri
    assert detail_rows[chain_env.iri(f"enum-meaning/{EM_STATUS_RESOLVED}")] is None

    detail = chain.enum_meaning_detail(chain_env.iri(f"enum-meaning/{EM_CAUSE_PS}"))
    assert detail
    assert (detail.get("detail_fields") or {}).get("semantic_value") == part_shortage_iri


def test_s4_double_reference_yields_one_business_node(chain_env):
    chain = ControlledValueChain(chain_env, "grant")
    resource = chain.l3_resource_candidates("缺料")
    assert [match["iri"] for match in resource] == [
        chain_env.iri(f"entity/{ENTITY_PART_SHORTAGE}")
    ]
    linked = chain.linked_enum_candidates("缺料")
    assert len(linked) == 2
    sqls = sorted(chain.derive_enum_filter_sql(match) for match in linked)
    assert sqls == [
        f"SELECT count(*) FROM {TABLE_DELAY} WHERE \"cause_code\" = 'PART_SHORTAGE'",
        f"SELECT count(*) FROM {TABLE_WO} WHERE \"status\" = 'WAITING_PARTS'",
    ]


# ---------------------------------------------------------------------------
# S5 representative question closed loop (+ optional adapter execution)
# ---------------------------------------------------------------------------


def test_s5_delayed_by_shortage_orders_closed_loop(chain_env):
    chain = ControlledValueChain(chain_env, "grant")
    result = chain.derive_delay_orders_sql("缺料")
    assert result["status"] == "ok", result
    assert result["sql"] == EXPECTED_S5_SQL
    if not DSN:
        pytest.skip("R3005_SQL_ADAPTER_DSN is not set (scenario PostgreSQL unavailable)")
    executed = run_sql(result["sql"])
    assert [list(row) for row in executed["rows"]] == S5_BASELINE_ROWS


def test_s5c_broken_chain_matrix(chain_env):
    """Each S5c variant terminates the representative chain in the uniform
    unconfirmable state; variant (i) additionally proves the downgrade is not
    destruction (L2 fallback via business_meaning)."""
    chain = ControlledValueChain(chain_env, "grant")
    assert chain.derive_delay_orders_sql("缺料")["status"] == "ok"

    session_id = chain_env.seed_session_id
    lease_token = chain_env.seed_lease_token

    def apply_variant(items: list[dict], batch: str):
        response = chain_env.client.get(
            f"/api/build-sessions/{session_id}/modeling-batches/{batch}",
            headers=chain_env.headers("model"),
        )
        assert response.status_code == 404, response.text  # not yet submitted
        with chain_env.client.app.state.session_factory() as db:
            version = OntologyModelRevisionService(
                db, chain_env.client.app.state.settings
            ).version_for(chain_env.ontology_id)
        submitted = _submit_batch(
            chain_env,
            chain_env.client.app.state.settings,
            session_id,
            version,
            items,
            batch=batch,
            key=f"{batch}-key",
            mode="apply_atomic",
            lease_token=lease_token,
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["attempt_status"] == "applied", submitted.json()
        chain_env.variant_batch_ids.append(submitted.json()["batch_id"])

    def item(item_id: str, kind: str, payload: dict) -> dict:
        return {
            "client_item_id": item_id,
            "command_kind": kind,
            "payload": payload,
            "rationale": "R3.0-008A S5c fixture variant (registered baseline)",
            "evidence": [
                {"document_name": "schema-ddl.md", "excerpt": f"{item_id} variant."}
            ],
        }

    # (i) clear EM-CAUSE-PS semantic_value: L3 -> L2 downgrade
    apply_variant(
        [
            item(
                "s5c-i-clear",
                "update_enum_meaning",
                {
                    "enum_meaning_id": EM_CAUSE_PS,
                    "semantic_value": None,
                },
            )
        ],
        "r3008a-s5c-i",
    )
    assert chain.derive_delay_orders_sql("缺料") == UNCONFIRMABLE
    # downgrade is not destruction: the L2 business_meaning fallback still
    # recalls the enum and derives its own filter SQL
    fallback = [
        match
        for match in chain.business_meaning_candidates("缺料")
        if (match.get("data") or {}).get("enum_value") == "PART_SHORTAGE"
    ]
    assert fallback
    assert "semantic_value" not in (fallback[0].get("data") or {})
    assert chain.derive_enum_filter_sql(fallback[0]) == (
        f"SELECT count(*) FROM {TABLE_DELAY} WHERE \"cause_code\" = 'PART_SHORTAGE'"
    )

    # (ii) delete the delay-events TableMapping (join first, then the table
    # mapping, so the G3 reverse gate stays satisfied)
    apply_variant(
        [
            item(
                "s5c-ii-del-join",
                "delete_join_mapping",
                {"join_mapping_id": "jm-wo-delay"},
            )
        ],
        "r3008a-s5c-ii-join",
    )
    apply_variant(
        [
            item(
                "s5c-ii-del-table",
                "delete_table_mapping",
                {"table_mapping_id": "tm-delay"},
            )
        ],
        "r3008a-s5c-ii-table",
    )
    result = chain.derive_delay_orders_sql("缺料")
    assert result == UNCONFIRMABLE

    # (iii) delete EM-CAUSE-PS entirely
    apply_variant(
        [
            item(
                "s5c-iii-del-enum",
                "delete_enum_meaning",
                {"enum_meaning_id": EM_CAUSE_PS},
            )
        ],
        "r3008a-s5c-iii",
    )
    assert not [
        match
        for match in chain.business_meaning_candidates("缺料")
        if (match.get("data") or {}).get("enum_value") == "PART_SHORTAGE"
    ]
    assert chain.derive_delay_orders_sql("缺料") == UNCONFIRMABLE

    # (iv) clear EM-STATUS-WP business_meaning: lexical recall finds nothing
    # to link, the chain stays unconfirmable
    apply_variant(
        [
            item(
                "s5c-iv-clear-bm",
                "update_enum_meaning",
                {
                    "enum_meaning_id": EM_STATUS_WP,
                    "business_meaning": None,
                },
            )
        ],
        "r3008a-s5c-iv",
    )
    assert chain.derive_delay_orders_sql("缺料") == UNCONFIRMABLE
    assert not chain.business_meaning_candidates("缺料待料")


# ---------------------------------------------------------------------------
# F1 / F2 — authorization: traceless hiding for the unauthorized principal
# ---------------------------------------------------------------------------


def test_f1_f2_unauthorized_l3_is_traceless(chain_env):
    chain = ControlledValueChain(chain_env, "nogrant")

    # the L3 resource candidate, both linked mapping candidates, and the
    # enum-meaning rows are all hidden; the chain is uniformly unconfirmable
    protected = chain.derive_delay_orders_sql("缺料")
    nonexistent = chain.derive_delay_orders_sql("从未见过的业务值")
    assert protected == UNCONFIRMABLE
    assert nonexistent == UNCONFIRMABLE
    assert protected == nonexistent  # indistinguishable terminal states

    # F2 scope = the surfaces F1 enumerates: the chain terminal states, the
    # mapping candidates, the enum-meaning rows, and the L3 resource
    # candidates. (The EM instance-kind resource projection carries no
    # semanticValue field, so per design decision 4 it is not part of the
    # semanticValue-linked traceless contract; hiding it is the protection
    # set's per-member choice, not this chain's.)
    serialized = json.dumps(
        [
            protected,
            nonexistent,
            [match for match in chain.locate(["缺料", "延期"], ["mapping"])],
            chain._mapping_rows("enum-meaning-list"),
            chain.l3_resource_candidates("缺料"),
        ],
        ensure_ascii=False,
    )
    _assert_forbidden_absent(chain_env, serialized)

    # traceless subset contract: unprotected resources stay visible
    ok = [
        match
        for match in chain.locate(["已完成"], ["mapping"])
        if (match.get("data") or {}).get("business_meaning") == "已完成"
    ]
    assert ok
    assert chain.derive_enum_filter_sql(ok[0]) == (
        f"SELECT count(*) FROM {TABLE_WO} WHERE \"status\" = 'RESOLVED'"
    )


# ---------------------------------------------------------------------------
# F5 — RDF never copies business rows
# ---------------------------------------------------------------------------


def test_f5_rdf_has_no_business_rows(chain_env):
    store = chain_env.store
    graphs = " ".join(
        f"<{chain_env.client.app.state.settings.semantic_graph_iri_prefix.rstrip('/')}"
        f"/{category}/{chain_env.ontology_id}>"
        for category in ("ontology", "data")
    )
    query = f"""
    SELECT ?s ?p ?o WHERE {{ VALUES ?g {{ {graphs} }} GRAPH ?g {{ ?s ?p ?o . }} }}
    """
    result = store.query_sparql(query, timeout_seconds=10, limit=5000)
    serialized = json.dumps(
        [
            [str(binding.get("s")), str(binding.get("p")), str(binding.get("o"))]
            for binding in result.result.get("results", {}).get("bindings", [])
        ],
        ensure_ascii=False,
    )
    for row_marker in ("WO-1001", "WO-1008", "DELAY-1001", "INC-", "EVT-"):
        assert row_marker not in serialized
    # no subject is typed as the WorkOrder/DelayReason/SparePart business
    # classes carrying row identity (the only typed instances are the two
    # fixture value nodes)
    work_order_class = chain_env.iri(f"class/{CLASS_WORK_ORDER}")
    assert f"http://www.w3.org/1999/02/22-rdf-syntax-ns#type\", \"{work_order_class}" not in (
        serialized
    )


# ---------------------------------------------------------------------------
# F6 — zero modeling activity during consumption
# ---------------------------------------------------------------------------


def test_f6_no_new_modeling_activity_during_consumption(chain_env):
    factory = chain_env.client.app.state.session_factory
    with factory() as session:
        before_batches = set(session.scalars(select(ModelingBatchModel.id)).all())
        before_sessions = len(session.scalars(select(BuildSessionModel.id)).all())

    for key in ("grant", "nogrant"):
        chain = ControlledValueChain(chain_env, key)
        assert chain.derive_delay_orders_sql("缺料") in (
            {"status": "ok", "sql": EXPECTED_S5_SQL},
            UNCONFIRMABLE,
        )
        chain.locate(["已完成"], ["mapping"])

    with factory() as session:
        after_batches = set(session.scalars(select(ModelingBatchModel.id)).all())
        after_sessions = len(session.scalars(select(BuildSessionModel.id)).all())
    assert after_batches == before_batches
    assert after_sessions == before_sessions
