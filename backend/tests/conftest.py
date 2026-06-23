import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AGENT_LLM_API_KEY", "test-agent-key")

from app.db import Base, get_session
from app.main import app
import app.models as models  # noqa: F401


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()
    try:
        yield session, TestingSession
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    session, _ = db_session

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        from fastapi.testclient import TestClient

        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
