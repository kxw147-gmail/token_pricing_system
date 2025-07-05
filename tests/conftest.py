import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base, get_db
from app.main import app # Import the FastAPI app
from app.core.config import settings
from app.services.cache_service import connect_redis, disconnect_redis, _cache
import time
import logging

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(autouse=True)
def setup_test_logging(monkeypatch):
    """
    Fixture to configure logging for tests.
    Sets logging to CRITICAL to suppress most output during tests,
    but still captures it if needed for debugging test failures.
    """
    # Create an in-memory handler to capture logs
    test_log_handler = logging.StreamHandler()
    test_log_handler.setLevel(logging.DEBUG)
    
    # Temporarily set the root logger level to CRITICAL for tests
    # This prevents excessive logging output during test runs, but allows
    # specific log messages to be captured if needed.
    root_logger = logging.getLogger()
    original_level = root_logger.level
    original_handlers = root_logger.handlers[:] # Copy existing handlers
    
    # Clear existing handlers and add our test handler
    root_logger.handlers = []
    root_logger.addHandler(test_log_handler)
    root_logger.setLevel(logging.CRITICAL) # Suppress most logs

    # Ensure app's logger also respects this
    for name in logging.root.manager.loggerDict:
        if name.startswith('app'): # Target only app's loggers
            logging.getLogger(name).setLevel(logging.CRITICAL)
            logging.getLogger(name).propagate = True # Ensure logs propagate to root

    yield

    # Restore original logging configuration after tests
    root_logger.setLevel(original_level)
    root_logger.handlers = original_handlers
    for name in logging.root.manager.loggerDict:
        if name.startswith('app'):
            logging.getLogger(name).propagate = False # Reset propagation
            logging.getLogger(name).setLevel(logging.NOTSET) # Reset level

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