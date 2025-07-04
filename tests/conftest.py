""" This module contains fixtures for testing the FastAPI application, including database setup and client configuration."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base, get_db
from app.main import app # Import the FastAPI app
from app.core.config import settings
from app.services.cache_service import _cache # Import cache service functions


# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="db_engine")
def db_engine_fixture():
    """Fixture to create a test database engine."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine) # Clean up after tests

@pytest.fixture(name="db_session")
def db_session_fixture(db_engine):
    """Fixture to create a database session for tests."""
    # Create a new session for each test
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db =  test_session_local()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="client")
def client_fixture(db_session, monkeypatch):
    """Fixture to create a FastAPI test client with overridden dependencies."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Mock in-memory cache for tests
    async def mock_connect_redis():
        _cache.clear() # Clear in-memory cache for each test
    
    async def mock_disconnect_redis():
        pass # No explicit disconnect for in-memory cache

    monkeypatch.setattr("app.services.cache_service.connect_redis", mock_connect_redis)
    monkeypatch.setattr("app.services.cache_service.disconnect_redis", mock_disconnect_redis)

    # Override settings for tests
    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 1) # Short expiry for tests

    with TestClient(app) as test_client:
        yield test_client