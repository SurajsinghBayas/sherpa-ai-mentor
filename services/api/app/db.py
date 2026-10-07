"""Database wiring — Neon Postgres in prod, SQLite fallback locally.

Only std SQLAlchemy 2.0 (sync). Same `get_session` dependency is used by
every router, so swapping the URL is all it takes to go from laptop to Neon.
Tables are created on startup via `init_db()`; use Alembic once the schema
starts evolving (see docs/neon_setup.md).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    url = (settings.database_url or "").strip()
    if url:
        return url
    os.makedirs(settings.data_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(settings.data_dir, 'sherpa.db')}"


def _make_engine():
    url = _database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # Neon / Postgres: require SSL, recycle pooled connections.
    if "sslmode" not in url and "neon.tech" in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import dbmodels  # noqa: F401 — register models before create_all
    Base.metadata.create_all(bind=engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
