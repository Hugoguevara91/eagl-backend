"""client geocode fields

Revision ID: 0006_client_geocode
Revises: 0005_solver_client
Create Date: 2026-01-15 18:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_client_geocode"
down_revision = "0005_solver_client"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("clients", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("clients", sa.Column("geocoded_at", sa.DateTime(), nullable=True))
    op.add_column("clients", sa.Column("geocode_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "geocode_status")
    op.drop_column("clients", "geocoded_at")
    op.drop_column("clients", "longitude")
    op.drop_column("clients", "latitude")
