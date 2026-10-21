"""Repo snapshots in the database, per-user quotas, pgvector embeddings (Postgres only).

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # amazon.nova-2-multimodal-embeddings-v1:0 at embeddingDimension=1024


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, server_default=""),
        sa.Column("source", sa.String(1000), nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False, server_default="git"),
        sa.Column("branch", sa.String(200), nullable=False, server_default=""),
        sa.Column("commit", sa.String(64), nullable=False, server_default=""),
        sa.Column("indexed_at", sa.Float, nullable=False, server_default="0"),
        sa.Column("files_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunks_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("languages", sa.JSON, nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_repos_owner_id", "repos", ["owner_id"])

    op.create_table(
        "repo_files",
        sa.Column("repo_id", sa.String(32), sa.ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("path", sa.String(1000), primary_key=True),
        sa.Column("hash", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False))

    op.create_table(
        "repo_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repo_id", sa.String(32), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("file", sa.String(1000), nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="code"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(40), nullable=False))
    op.create_index("ix_repo_chunks_repo_ord", "repo_chunks", ["repo_id", "ord"])
    op.create_index("ix_repo_chunks_text_hash", "repo_chunks", ["text_hash"])

    op.create_table(
        "repo_artifacts",
        sa.Column("repo_id", sa.String(32), sa.ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))

    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"))

    # pgvector table (Postgres only); skipped with a warning if the extension can't be enabled
    from app.db import ensure_vector_table
    ensure_vector_table(op.get_bind(), EMBEDDING_DIM)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS chunk_embeddings")
    for t in ("usage_counters", "repo_artifacts", "repo_chunks", "repo_files", "repos"):
        op.drop_table(t)
