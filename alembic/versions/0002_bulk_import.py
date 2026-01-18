"""bulk import/export tables

Revision ID: 0002_bulk_import
Revises: 
Create Date: 2026-01-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_bulk_import"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("entity", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="upsert"),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("file_url", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("template_version", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("error_report_url", sa.String(), nullable=True),
        sa.Column("preview_json", sa.JSON(), nullable=True),
        sa.Column("logs_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("tenant_id", "entity", "file_hash", name="uq_import_dedup"),
    )
    op.create_index("ix_import_jobs_tenant_id", "import_jobs", ["tenant_id"])
    op.create_index("ix_import_jobs_entity", "import_jobs", ["entity"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])

    op.create_table(
        "import_row_errors",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("import_job_id", sa.String(), sa.ForeignKey("import_jobs.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="error"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.create_index("ix_import_row_errors_job", "import_row_errors", ["import_job_id"])

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("entity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("file_url", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_hash", sa.String(), nullable=True),
        sa.Column("template_version", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_export_jobs_tenant_id", "export_jobs", ["tenant_id"])
    op.create_index("ix_export_jobs_entity", "export_jobs", ["entity"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_entity", table_name="export_jobs")
    op.drop_index("ix_export_jobs_tenant_id", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_index("ix_import_row_errors_job", table_name="import_row_errors")
    op.drop_table("import_row_errors")
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_entity", table_name="import_jobs")
    op.drop_index("ix_import_jobs_tenant_id", table_name="import_jobs")
    op.drop_table("import_jobs")
