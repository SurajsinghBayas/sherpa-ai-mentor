"""Passwordless sign-in: email one-time codes and Google accounts.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email_verified", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("google_sub", sa.String(64), nullable=True))
        b.create_unique_constraint("uq_users_google_sub", ["google_sub"])
    op.create_table(
        "email_otps",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.Float, nullable=False))
    op.create_index("ix_email_otps_email", "email_otps", ["email"])


def downgrade() -> None:
    op.drop_table("email_otps")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_google_sub", type_="unique")
        b.drop_column("google_sub")
        b.drop_column("email_verified")
