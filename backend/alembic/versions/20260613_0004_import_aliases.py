"""add import aliases

Revision ID: 20260613_0004
Revises: 20260608_0003
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_0004"
down_revision = "20260608_0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("import_aliases"):
        op.create_table(
            "import_aliases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("alias_type", sa.String(length=30), nullable=False),
            sa.Column("alias_name", sa.String(length=100), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "alias_type", "alias_name", name="uq_import_aliases_tenant_type_name"),
        )

    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("import_aliases")}
    if op.f("ix_import_aliases_tenant_id") not in indexes:
        op.create_index(op.f("ix_import_aliases_tenant_id"), "import_aliases", ["tenant_id"], unique=False)
    if op.f("ix_import_aliases_alias_type") not in indexes:
        op.create_index(op.f("ix_import_aliases_alias_type"), "import_aliases", ["alias_type"], unique=False)
    if op.f("ix_import_aliases_target_id") not in indexes:
        op.create_index(op.f("ix_import_aliases_target_id"), "import_aliases", ["target_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_import_aliases_target_id"), table_name="import_aliases")
    op.drop_index(op.f("ix_import_aliases_alias_type"), table_name="import_aliases")
    op.drop_index(op.f("ix_import_aliases_tenant_id"), table_name="import_aliases")
    op.drop_table("import_aliases")
