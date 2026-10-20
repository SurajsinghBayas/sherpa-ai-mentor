"""Database wiring — AWS RDS Postgres in prod, SQLite fallback locally.

Only std SQLAlchemy 2.0 (sync). Same `get_session` dependency is used by
every router, so swapping the URL is all it takes to go from laptop to RDS.
The schema is managed by Alembic (services/api/migrations); `init_db()` upgrades
to the latest revision on startup, so a fresh RDS database needs no manual step.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, _):
    # SQLite ignores ON DELETE CASCADE unless asked; Postgres always enforces it
    if type(dbapi_conn).__module__.startswith("sqlite3"):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


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
    # Remote Postgres (RDS): require SSL unless the URL says otherwise; recycle pooled connections.
    host = url.split("@")[-1].split("/")[0].split(":")[0]
    if "sslmode" not in url and host not in ("localhost", "127.0.0.1", "db"):
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def init_db() -> None:
    """Apply pending Alembic migrations to the configured database."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # several replicas starting at once must not migrate concurrently
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(724205)")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
