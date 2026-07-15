"""backfill default semantic workspaces for existing ontologies

Revision ID: 0025_backfill_workspaces
Revises: 0024_modeling_result_cascade
Create Date: 2026-07-15
"""

from collections.abc import Sequence
import hashlib
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

from app.core.config import Settings

revision: str = "0025_backfill_workspaces"
down_revision: str | None = "0024_modeling_result_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


GRAPH_SPECS = (
    ("asserted_ontology", "ontology", True, 0),
    ("asserted_data", "data", True, 1),
    ("shapes", "shapes", True, 2),
    ("policy", "policy", False, 3),
)


def _id(ontology_id: str, resource: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ontology-platform:{ontology_id}:{resource}"))


def upgrade() -> None:
    bind = op.get_bind()
    prefix = Settings().semantic_graph_iri_prefix.rstrip("/")
    ontology_ids = list(bind.execute(sa.text("SELECT id FROM ontologies")).scalars())
    empty_hash = hashlib.sha256(b"").hexdigest()
    for ontology_id in ontology_ids:
        members = []
        for role, category, editable, sort_order in GRAPH_SPECS:
            graph_iri = f"{prefix}/{category}/{ontology_id}"
            members.append((graph_iri, role, sort_order))
            bind.execute(
                sa.text(
                    """
                    INSERT INTO semantic_graph_registry
                        (id, graph_iri, category, semantic_owner_type, semantic_owner_id,
                         mutable_by_direct_edit, managed, metadata)
                    VALUES
                        (:id, :graph_iri, :category, 'ontology', :ontology_id,
                         :editable, true, '{"workspace_role": "backfilled", "default": true}'::jsonb)
                    ON CONFLICT (graph_iri) DO NOTHING
                    """
                ),
                {
                    "id": _id(ontology_id, f"registry:{role}"),
                    "graph_iri": graph_iri,
                    "category": category,
                    "ontology_id": ontology_id,
                    "editable": editable,
                },
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO semantic_graph_revisions
                        (id, graph_iri, revision, content_hash, metadata)
                    VALUES
                        (:id, :graph_iri, 0, :content_hash,
                         '{"workspace_role": "backfilled", "initial": true}'::jsonb)
                    ON CONFLICT (graph_iri) DO NOTHING
                    """
                ),
                {
                    "id": _id(ontology_id, f"revision:{role}"),
                    "graph_iri": graph_iri,
                    "content_hash": empty_hash,
                },
            )

        graph_set_id = bind.execute(
            sa.text(
                """
                SELECT id FROM semantic_graph_sets
                WHERE scope_type = 'ontology' AND scope_id = :ontology_id AND is_default = true
                LIMIT 1
                """
            ),
            {"ontology_id": ontology_id},
        ).scalar_one_or_none()
        if graph_set_id is None:
            graph_set_id = _id(ontology_id, "graph-set:default")
            bind.execute(
                sa.text(
                    """
                    INSERT INTO semantic_graph_sets
                        (id, name, scope_type, scope_id, status, is_default,
                         source_signature, metadata)
                    VALUES
                        (:id, 'Default workspace', 'ontology', :ontology_id, 'active', true,
                         '', '{"default": true, "workspace_version": "r001-v1", "backfilled": true}'::jsonb)
                    """
                ),
                {"id": graph_set_id, "ontology_id": ontology_id},
            )
        for graph_iri, role, sort_order in members:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO semantic_graph_set_members
                        (id, graph_set_id, graph_iri, role, required, sort_order, metadata)
                    VALUES
                        (:id, :graph_set_id, :graph_iri, :role, true, :sort_order,
                         '{"default": true, "backfilled": true}'::jsonb)
                    ON CONFLICT (graph_set_id, graph_iri) DO NOTHING
                    """
                ),
                {
                    "id": _id(ontology_id, f"member:{role}"),
                    "graph_set_id": graph_set_id,
                    "graph_iri": graph_iri,
                    "role": role,
                    "sort_order": sort_order,
                },
            )
        signature_payload = "|".join(
            f"{role}:{graph_iri}:0:{sort_order}"
            for graph_iri, role, sort_order in members
        )
        signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:32]
        bind.execute(
            sa.text(
                "UPDATE semantic_graph_sets SET source_signature = :signature WHERE id = :id"
            ),
            {"signature": signature, "id": graph_set_id},
        )


def downgrade() -> None:
    # Backfilled rows can become referenced by later modeling history. A schema
    # downgrade therefore leaves them in place instead of deleting user state.
    pass
