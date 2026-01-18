"""scan module tables

Revision ID: 0007_scan_module
Revises: 0006_client_geocode
Create Date: 2026-01-16 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_scan_module"
down_revision = "0006_client_geocode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("tipo_equipamento", sa.String(), nullable=False),
        sa.Column("marca", sa.String(), nullable=False),
        sa.Column("modelo", sa.String(), nullable=False),
        sa.Column("problema_texto", sa.String(), nullable=False),
        sa.Column("problema_tags", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("openai_model", sa.String(), nullable=True),
        sa.Column("confidence_overall", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("os_id", sa.String(), nullable=True),
        sa.Column("asset_id", sa.String(), nullable=True),
    )

    op.create_table(
        "scan_images",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scan_id", sa.String(), sa.ForeignKey("scan_sessions.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("storage_url", sa.String(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "scan_signals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scan_id", sa.String(), sa.ForeignKey("scan_sessions.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "scan_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scan_id", sa.String(), sa.ForeignKey("scan_sessions.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scan_results")
    op.drop_table("scan_signals")
    op.drop_table("scan_images")
    op.drop_table("scan_sessions")
