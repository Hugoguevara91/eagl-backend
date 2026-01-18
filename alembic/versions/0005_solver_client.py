"""solver client fields

Revision ID: 0005_solver_client
Revises: 0004_work_orders_extended
Create Date: 2026-01-15 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_solver_client"
down_revision = "0004_work_orders_extended"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("problem_session", sa.Column("client_id", sa.String(), nullable=True))
    op.add_column("problem_session", sa.Column("client_name_snapshot", sa.String(), nullable=True))
    op.add_column("problem_session", sa.Column("client_other_text", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_problem_session_client",
        "problem_session",
        "clients",
        ["client_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_problem_session_client", "problem_session", type_="foreignkey")
    op.drop_column("problem_session", "client_other_text")
    op.drop_column("problem_session", "client_name_snapshot")
    op.drop_column("problem_session", "client_id")
