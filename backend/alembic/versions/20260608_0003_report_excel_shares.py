"""add report excel shares

Revision ID: 20260608_0003
Revises: 20260531_0002
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260608_0003"
down_revision = "20260531_0002"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("report_excel_shares"):
        op.create_table(
            "report_excel_shares",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("file_path", sa.String(length=500), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("report_excel_shares")}
    if op.f("ix_report_excel_shares_created_by") not in indexes:
        op.create_index(op.f("ix_report_excel_shares_created_by"), "report_excel_shares", ["created_by"], unique=False)
    if op.f("ix_report_excel_shares_expires_at") not in indexes:
        op.create_index(op.f("ix_report_excel_shares_expires_at"), "report_excel_shares", ["expires_at"], unique=False)
    if op.f("ix_report_excel_shares_tenant_id") not in indexes:
        op.create_index(op.f("ix_report_excel_shares_tenant_id"), "report_excel_shares", ["tenant_id"], unique=False)
    if op.f("ix_report_excel_shares_token") not in indexes:
        op.create_index(op.f("ix_report_excel_shares_token"), "report_excel_shares", ["token"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_report_excel_shares_token"), table_name="report_excel_shares")
    op.drop_index(op.f("ix_report_excel_shares_tenant_id"), table_name="report_excel_shares")
    op.drop_index(op.f("ix_report_excel_shares_expires_at"), table_name="report_excel_shares")
    op.drop_index(op.f("ix_report_excel_shares_created_by"), table_name="report_excel_shares")
    op.drop_table("report_excel_shares")
