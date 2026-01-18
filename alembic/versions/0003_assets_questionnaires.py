"""assets and questionnaires

Revision ID: 0003_assets_questionnaires
Revises: 0002_bulk_import
Create Date: 2026-01-10 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_assets_questionnaires"
down_revision = "0002_bulk_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("client_code", sa.String(), nullable=True))
    op.add_column("sites", sa.Column("code", sa.String(), nullable=True))

    op.create_table(
        "assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("site_id", sa.String(), sa.ForeignKey("sites.id"), nullable=True),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("tenant_id", "tag", name="uq_asset_tag"),
    )

    op.create_table(
        "os_types",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("tenant_id", "name", "client_id", name="uq_os_type"),
    )

    op.create_table(
        "questionnaires",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="ATIVO"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("tenant_id", "title", "version", name="uq_questionnaire"),
    )

    op.create_table(
        "questionnaire_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("questionnaire_id", sa.String(), sa.ForeignKey("questionnaires.id"), nullable=False),
        sa.Column("question_text", sa.String(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("answer_type", sa.String(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )


def downgrade() -> None:
    op.drop_table("questionnaire_items")
    op.drop_table("questionnaires")
    op.drop_table("os_types")
    op.drop_table("assets")
    op.drop_column("sites", "code")
    op.drop_column("clients", "client_code")
