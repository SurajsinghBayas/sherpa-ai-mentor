"""Skill check: finished quiz attempts per user and repo.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repo_id", sa.String(32), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quiz_id", sa.String(32), nullable=False),
        sa.Column("correct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("areas", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quiz_attempts_user_repo", "quiz_attempts", ["user_id", "repo_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_attempts_user_repo", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
