"""work orders extended fields

Revision ID: 0004_work_orders_extended
Revises: 0003_assets_questionnaires
Create Date: 2026-01-13 00:20:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_work_orders_extended"
down_revision = "0003_assets_questionnaires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("code_human", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("contract_id", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("site_id", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("requester_name", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("requester_phone", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("responsible_user_id", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("materials", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("conclusion", sa.String(), nullable=True))
    op.add_column("work_orders", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")))
    op.add_column("work_orders", sa.Column("checkin_data", sa.JSON(), nullable=True))
    op.add_column("work_orders", sa.Column("checkout_data", sa.JSON(), nullable=True))
    op.add_column("work_orders", sa.Column("totals", sa.JSON(), nullable=True))
    op.add_column("work_orders", sa.Column("signatures", sa.JSON(), nullable=True))

    op.add_column("work_order_attachments", sa.Column("question_id", sa.String(), nullable=True))
    op.add_column("work_order_attachments", sa.Column("scope", sa.String(), nullable=False, server_default="QUESTION"))
    op.add_column("work_order_attachments", sa.Column("mime", sa.String(), nullable=True))
    op.add_column("work_order_attachments", sa.Column("size", sa.Integer(), nullable=True))
    op.add_column("work_order_attachments", sa.Column("thumb_url", sa.String(), nullable=True))
    op.add_column("work_order_attachments", sa.Column("created_by", sa.String(), nullable=True))

    op.create_foreign_key(
        "fk_work_orders_site",
        "work_orders",
        "sites",
        ["site_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_work_orders_site", "work_orders", type_="foreignkey")
    op.drop_column("work_order_attachments", "created_by")
    op.drop_column("work_order_attachments", "thumb_url")
    op.drop_column("work_order_attachments", "size")
    op.drop_column("work_order_attachments", "mime")
    op.drop_column("work_order_attachments", "scope")
    op.drop_column("work_order_attachments", "question_id")

    op.drop_column("work_orders", "signatures")
    op.drop_column("work_orders", "totals")
    op.drop_column("work_orders", "checkout_data")
    op.drop_column("work_orders", "checkin_data")
    op.drop_column("work_orders", "updated_at")
    op.drop_column("work_orders", "conclusion")
    op.drop_column("work_orders", "materials")
    op.drop_column("work_orders", "responsible_user_id")
    op.drop_column("work_orders", "requester_phone")
    op.drop_column("work_orders", "requester_name")
    op.drop_column("work_orders", "site_id")
    op.drop_column("work_orders", "contract_id")
    op.drop_column("work_orders", "code_human")
