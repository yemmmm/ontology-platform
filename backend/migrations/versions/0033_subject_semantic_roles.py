"""R4.0-006 subject-owned keys and project roles (no legacy Grant migration)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_subject_semantic_roles"
down_revision = "0032_semantic_protection_sets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("is_org_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True)))
    # Before this revision users were exclusively administrator login identities.
    op.execute("UPDATE users SET is_org_admin = true")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.add_column("api_keys", sa.Column("user_id", sa.String(36)))
    op.create_foreign_key("fk_api_key_user", "api_keys", "users", ["user_id"], ["id"])
    op.add_column(
        "api_keys",
        sa.Column("is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Only the configured server bootstrap path may mark an existing key.
    op.drop_column("api_keys", "semantic_grants")
    op.create_table(
        "project_user_memberships",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_table(
        "semantic_access_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("grants", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("business_role_iri", sa.String(1024)),
        sa.Column("business_role_ontology_id", sa.String(36)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "id", name="uq_access_role_project_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_access_role_project_name"),
    )
    op.create_table(
        "semantic_access_role_members",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("role_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["project_user_memberships.project_id", "project_user_memberships.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "role_id"],
            ["semantic_access_roles.project_id", "semantic_access_roles.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("semantic_access_role_members")
    op.drop_table("semantic_access_roles")
    op.drop_table("project_user_memberships")
    op.add_column("api_keys", sa.Column("semantic_grants", postgresql.JSONB()))
    op.drop_column("api_keys", "is_bootstrap")
    op.drop_constraint("fk_api_key_user", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "user_id")
    # Key-only subjects must be removed explicitly before downgrading.
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "is_org_admin")
