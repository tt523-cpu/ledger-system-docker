"""tenant isolate master data

Revision ID: 20260531_0002
Revises: 20260529_0001
Create Date: 2026-05-31 18:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260531_0002"
down_revision = "20260529_0001"
branch_labels = None
depends_on = None


def _ensure_tenant_column(table_name: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(table_name)}
    if "tenant_id" not in columns:
        op.add_column(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
    indexes = {i["name"] for i in inspector.get_indexes(table_name)}
    idx_name = f"ix_{table_name}_tenant_id"
    if idx_name not in indexes:
        op.create_index(idx_name, table_name, ["tenant_id"], unique=False)


def _drop_single_name_unique(table_name: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for cons in inspector.get_unique_constraints(table_name):
        cols = cons.get("column_names") or []
        if cols == ["name"] and cons.get("name"):
            op.drop_constraint(cons["name"], table_name, type_="unique")
            return


def upgrade() -> None:
    for table in ["platforms", "shifts", "accounts", "payment_methods", "categories", "entry_types"]:
        _ensure_tenant_column(table)

    op.execute(
        """
        UPDATE platforms p
        JOIN tenant_platform_access tpa ON tpa.platform_id = p.id
        SET p.tenant_id = tpa.tenant_id
        WHERE p.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE platforms p
        SET p.tenant_id = (SELECT MIN(id) FROM tenants)
        WHERE p.tenant_id IS NULL
        """
    )
    for table in ["shifts", "accounts", "payment_methods", "categories", "entry_types"]:
        op.execute(f"UPDATE {table} SET tenant_id = (SELECT MIN(id) FROM tenants) WHERE tenant_id IS NULL")

    for table in ["platforms", "shifts", "accounts", "payment_methods", "categories", "entry_types"]:
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)
        op.create_foreign_key(f"fk_{table}_tenant_id", table, "tenants", ["tenant_id"], ["id"])

    _drop_single_name_unique("platforms")
    _drop_single_name_unique("shifts")
    _drop_single_name_unique("accounts")
    _drop_single_name_unique("payment_methods")
    _drop_single_name_unique("categories")
    _drop_single_name_unique("entry_types")

    op.create_unique_constraint("uq_platforms_tenant_name", "platforms", ["tenant_id", "name"])
    op.create_unique_constraint("uq_shifts_tenant_name", "shifts", ["tenant_id", "name"])
    op.create_unique_constraint("uq_accounts_tenant_name", "accounts", ["tenant_id", "name"])
    op.create_unique_constraint("uq_payment_methods_tenant_name", "payment_methods", ["tenant_id", "name"])
    op.create_unique_constraint("uq_categories_tenant_name", "categories", ["tenant_id", "name"])
    op.create_unique_constraint("uq_entry_types_tenant_name", "entry_types", ["tenant_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_platforms_tenant_name", "platforms", type_="unique")
    op.drop_constraint("uq_shifts_tenant_name", "shifts", type_="unique")
    op.drop_constraint("uq_accounts_tenant_name", "accounts", type_="unique")
    op.drop_constraint("uq_payment_methods_tenant_name", "payment_methods", type_="unique")
    op.drop_constraint("uq_categories_tenant_name", "categories", type_="unique")
    op.drop_constraint("uq_entry_types_tenant_name", "entry_types", type_="unique")

    op.create_unique_constraint("platforms_name_key", "platforms", ["name"])
    op.create_unique_constraint("shifts_name_key", "shifts", ["name"])
    op.create_unique_constraint("accounts_name_key", "accounts", ["name"])
    op.create_unique_constraint("payment_methods_name_key", "payment_methods", ["name"])
    op.create_unique_constraint("categories_name_key", "categories", ["name"])
    op.create_unique_constraint("entry_types_name_key", "entry_types", ["name"])

    for table in ["platforms", "shifts", "accounts", "payment_methods", "categories", "entry_types"]:
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
