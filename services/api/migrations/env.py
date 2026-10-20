"""Alembic environment — runs against the app's own engine (DATABASE_URL or local SQLite)."""
from alembic import context

from app import db as dbmod
from app import dbmodels  # noqa: F401 — register tables on Base.metadata

config = context.config
target_metadata = dbmod.Base.metadata


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with dbmod.engine.connect() as conn:
        _run(conn)
        conn.commit()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
