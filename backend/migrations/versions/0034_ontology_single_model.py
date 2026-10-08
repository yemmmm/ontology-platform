"""R4.0-026: merge asserted models and retire GraphSet persistence."""

from pathlib import Path
import json
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034_ontology_single_model"
down_revision = "0033_subject_semantic_roles"
branch_labels = None
depends_on = None


def upgrade():
    from app.core.config import Settings
    from app.repositories.rdf_store import RdfStoreRepository
    from app.services.ontology_single_graph_migration import (
        merge_model_graphs,
        model_content_hash,
        migrate_reference_scopes,
    )

    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM ontology_write_fences")):
        raise RuntimeError("R4.0-026: settle retained Modeling Attempt writes before migration")
    ontologies = list(
        connection.execute(sa.text("SELECT * FROM ontologies ORDER BY id FOR UPDATE")).mappings()
    )
    registry = list(connection.execute(sa.text("SELECT * FROM semantic_graph_registry")).mappings())
    scopes = list(connection.execute(sa.text("SELECT * FROM semantic_graph_sets")).mappings())
    members = list(
        connection.execute(sa.text("SELECT * FROM semantic_graph_set_members")).mappings()
    )
    references = migrate_reference_scopes(ontologies, registry, scopes, members)
    settings = Settings()
    store = RdfStoreRepository(settings.oxigraph_url)
    plans = []
    # Validate ALL merges before the first RDF mutation.
    for ontology in ontologies:
        oid = ontology["id"]
        iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{oid}"
        rows = [
            row
            for row in registry
            if row["semantic_owner_type"] == "ontology"
            and row["semantic_owner_id"] == oid
            and row["category"] in {"ontology", "data", "policy"}
        ]
        contents = {
            row["graph_iri"]: store.get_graph(row["graph_iri"], "turtle")
            if store.graph_exists(row["graph_iri"])
            else ""
            for row in rows
        }
        if store.graph_exists(iri) and iri not in contents:
            from sqlalchemy.engine import make_url

            retained = (
                Path(".local/r4-0-026-migration")
                / make_url(settings.database_url).database
                / f"{oid}.json"
            )
            if not retained.exists() or json.loads(retained.read_text()).get("target") != iri:
                raise RuntimeError(f"R4.0-026 target storage is already occupied: {oid}, {iri}")
        graph = merge_model_graphs(contents)
        previous = connection.scalar(
            sa.text(
                "SELECT coalesce(max(revision),0) FROM semantic_graph_revisions WHERE graph_iri = ANY(:iris)"
            ),
            {"iris": list(contents)},
        )
        plans.append((oid, iri, contents, graph, int(previous or 0) + 1))
    # Retained originals permit deterministic rerun after a lost SQL COMMIT response.
    from sqlalchemy.engine import make_url

    archive = Path(".local/r4-0-026-migration") / make_url(settings.database_url).database
    archive.mkdir(parents=True, exist_ok=True)
    for oid, iri, contents, graph, revision_number in plans:
        path = archive / f"{oid}.json"
        if not path.exists():
            path.write_text(
                json.dumps(
                    {"ontology_id": oid, "target": iri, "original_graphs": contents},
                    ensure_ascii=False,
                )
            )
        path.chmod(0o600)
        store.put_named_graph(iri, graph.serialize(format="turtle"), "turtle")
        from rdflib import Graph

        actual = (
            Graph().parse(data=store.get_graph(iri, "turtle"), format="turtle")
            if store.graph_exists(iri)
            else Graph()
        )
        if model_content_hash(actual) != model_content_hash(graph):
            raise RuntimeError(f"R4.0-026 model readback mismatch: {oid}")
    op.add_column("ontologies", sa.Column("model_graph_iri", sa.Text()))
    op.add_column(
        "ontologies", sa.Column("model_revision", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("ontologies", sa.Column("model_content_hash", sa.String(64)))
    op.add_column(
        "ontologies",
        sa.Column("reference_ontology_ids", JSONB(), server_default="[]", nullable=False),
    )
    op.create_unique_constraint("uq_ontologies_model_graph_iri", "ontologies", ["model_graph_iri"])
    for oid, iri, contents, graph, revision_number in plans:
        connection.execute(
            sa.text(
                "UPDATE ontologies SET model_graph_iri=:iri, model_revision=:revision, model_content_hash=:hash WHERE id=:oid"
            ),
            {
                "oid": oid,
                "iri": iri,
                "revision": revision_number,
                "hash": model_content_hash(graph),
            },
        )
        connection.execute(
            sa.text("""
            INSERT INTO semantic_graph_registry
              (id,graph_iri,category,semantic_owner_type,semantic_owner_id,
               mutable_by_direct_edit,managed,metadata)
            VALUES (:id,:iri,'ontology','ontology',:oid,true,true,'{}')
            ON CONFLICT (graph_iri) DO UPDATE SET category='ontology',
              semantic_owner_type='ontology',semantic_owner_id=:oid,
              metadata='{}',mutable_by_direct_edit=true
        """),
            {"id": str(uuid5(NAMESPACE_URL, f"model-registry:{oid}")), "iri": iri, "oid": oid},
        )
        connection.execute(
            sa.text("""
            INSERT INTO semantic_graph_revisions (id,graph_iri,revision,content_hash,metadata)
            VALUES (:id,:iri,:revision,:hash,'{}')
            ON CONFLICT (graph_iri) DO UPDATE SET revision=:revision,content_hash=:hash
        """),
            {
                "id": str(uuid5(NAMESPACE_URL, f"model-revision:{oid}")),
                "iri": iri,
                "revision": revision_number,
                "hash": model_content_hash(graph),
            },
        )
    for oid, dependencies in references.items():
        connection.execute(
            sa.text(
                "UPDATE ontologies SET reference_ontology_ids=CAST(:ids AS jsonb) WHERE id=:oid"
            ),
            {"oid": oid, "ids": json.dumps(dependencies)},
        )
    inspector = sa.inspect(connection)
    for table in inspector.get_table_names():
        if table in {"semantic_graph_sets", "semantic_graph_set_members"}:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        for old, new in [
            ("graph_set_id", "ontology_id"),
            ("target_graph_set_id", "target_ontology_id"),
            ("source_graph_iris", "model_graph_iris"),
        ]:
            if old not in columns:
                continue
            for fk in inspector.get_foreign_keys(table):
                if (
                    old in fk["constrained_columns"]
                    and fk["referred_table"] == "semantic_graph_sets"
                ):
                    op.drop_constraint(fk["name"], table, type_="foreignkey")
            if new in columns:
                op.drop_column(table, old)
            else:
                if old.endswith("graph_set_id"):
                    connection.execute(
                        sa.text(
                            f'UPDATE "{table}" t SET "{old}"=s.scope_id FROM semantic_graph_sets s WHERE t."{old}"=s.id AND s.scope_type=\'ontology\''
                        )
                    )
                op.alter_column(table, old, new_column_name=new)
    # Old disposable index partitions are never advertised as the new model.
    connection.execute(sa.text("DELETE FROM semantic_retrieval_documents"))
    connection.execute(sa.text("UPDATE semantic_projection_manifests SET status='stale'"))
    connection.execute(
        sa.text(
            "UPDATE semantic_projection_jobs SET status='stale' WHERE status IN ('pending','running')"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM semantic_graph_registry r WHERE r.semantic_owner_type='ontology' AND EXISTS(SELECT 1 FROM ontologies o WHERE o.id=r.semantic_owner_id AND r.graph_iri<>o.model_graph_iri)"
        )
    )
    op.drop_table("semantic_graph_set_members")
    op.drop_table("semantic_graph_sets")


def downgrade():
    raise RuntimeError(
        "Single-model migration is irreversible; restore the retained SQL/RDF checkpoint"
    )
