"""GitHub sign-in: link a user to their GitHub account.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("github_id", sa.String(32), nullable=True))
        b.add_column(sa.Column("github_login", sa.String(64), nullable=True))
        b.create_unique_constraint("uq_users_github_id", ["github_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_github_id", type_="unique")
        b.drop_column("github_login")
        b.drop_column("github_id")
