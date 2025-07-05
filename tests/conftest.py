"""Fixture for creating mocked logging, database session and Redis cache."""
import pytest
import logging
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add the project root directory to the Python path to resolve 'app' module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import Base, get_db
from app.main import app # Import the FastAPI app
from app.core.config import settings
from app.services.cache_service import connect_redis, disconnect_redis, _cache


# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(autouse=True)
def setup_test_logging(monkeypatch):
    """
    Fixture to suppress application-level logging during tests.
    This prevents cluttering test output with INFO/DEBUG logs by setting
    app-specific loggers to a high level, without interfering with pytest's
    internal logging capture.
    """

    # Find all loggers used by the application
    app_loggers = [name for name in logging.root.manager.loggerDict if name.startswith('app')]
    original_levels = {name: logging.getLogger(name).level for name in app_loggers}

    yield

    # Restore original logging configuration after tests
    for name, level in original_levels.items():
        logging.getLogger(name).setLevel(level)

@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="client")
def client_fixture(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async def mock_connect_redis():
        _cache.clear()
    
    async def mock_disconnect_redis():
        pass

    monkeypatch.setattr("app.services.cache_service.connect_redis", mock_connect_redis)
    monkeypatch.setattr("app.services.cache_service.disconnect_redis", mock_disconnect_redis)

    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 1)

    with TestClient(app) as test_client:
        yield test_client