"""Baseline: accounts, BYOK credentials, user study.

These tables existed before migrations were introduced (created by create_all), so
each is created only if missing — the same migration works on fresh and existing DBs.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _now():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("name", sa.String(120), nullable=False, server_default=""),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
            _now())
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if "provider_keys" not in existing:
        op.create_table(
            "provider_keys",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(120), nullable=False, server_default=""),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("model", sa.String(120), nullable=False, server_default=""),
            sa.Column("key_enc", sa.Text, nullable=False),
            _now())
        op.create_index("ix_provider_keys_user_id", "provider_keys", ["user_id"])
        op.create_index("ix_provider_keys_provider", "provider_keys", ["provider"])
    if "custom_endpoints" not in existing:
        op.create_table(
            "custom_endpoints",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False, server_default=""),
            sa.Column("base_url", sa.String(500), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False, server_default="openai-compatible"),
            sa.Column("model", sa.String(120), nullable=False, server_default=""),
            sa.Column("api_key_enc", sa.Text, nullable=False, server_default=""),
            _now())
        op.create_index("ix_custom_endpoints_user_id", "custom_endpoints", ["user_id"])
    if "study_results" not in existing:
        op.create_table(
            "study_results",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("recorded_by", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("participant", sa.String(60), nullable=False),
            sa.Column("group", sa.String(16), nullable=False),
            sa.Column("task", sa.String(32), nullable=False),
            sa.Column("repo", sa.String(200), nullable=False, server_default=""),
            sa.Column("seconds", sa.Float, nullable=False),
            sa.Column("score", sa.Float, nullable=False, server_default="0"),
            sa.Column("max_score", sa.Float, nullable=False, server_default="1"),
            sa.Column("useful", sa.Integer, nullable=False, server_default="0"),
            sa.Column("trustworthy", sa.Integer, nullable=False, server_default="0"),
            sa.Column("reuse", sa.Integer, nullable=False, server_default="0"),
            sa.Column("notes", sa.Text, nullable=False, server_default=""),
            _now())
        op.create_index("ix_study_results_recorded_by", "study_results", ["recorded_by"])
        op.create_index("ix_study_results_group", "study_results", ["group"])
        op.create_index("ix_study_results_task", "study_results", ["task"])


def downgrade() -> None:
    for t in ("study_results", "custom_endpoints", "provider_keys", "users"):
        op.drop_table(t)
