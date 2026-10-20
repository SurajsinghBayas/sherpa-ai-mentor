"""Background ingestion jobs for uploaded codebases (ZIP, folder, CLI).

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("repo_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="zip"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default=""),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("detail", sa.Text, nullable=False, server_default=""),
        sa.Column("manifest", sa.JSON, nullable=True),
        sa.Column("payload", sa.LargeBinary, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("finished_at", sa.Float, nullable=True))
    op.create_index("ix_ingest_jobs_user", "ingest_jobs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("ingest_jobs")
