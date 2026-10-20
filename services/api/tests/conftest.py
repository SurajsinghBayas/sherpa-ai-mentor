"""Shared fixtures — isolated SQLite + dependency-overridden app client."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """Tests never call a paid model: force the offline composers unless a test opts in."""
    monkeypatch.setenv("LLM_PROVIDER", "none")


@pytest.fixture(autouse=True)
def no_real_email(monkeypatch):
    """.env may hold real SMTP credentials — tests must never send mail."""
    from app.config import settings
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "google_client_id", "test-client.apps.googleusercontent.com")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-hs256-ok")
    import app.db as dbmod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(f"sqlite:///{tmp_path}/t.db",
                        connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=eng, autoflush=False,
                                  expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", eng)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSession)

    import app.main as mainmod
    from app.db import get_session
    mainmod._stores.clear()  # tables are created by the Alembic migrations on startup

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    mainmod.app.dependency_overrides[get_session] = override
    with TestClient(mainmod.app) as c:
        yield c
    mainmod.app.dependency_overrides.clear()
