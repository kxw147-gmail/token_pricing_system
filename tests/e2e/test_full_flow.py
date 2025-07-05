import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base, get_db
from app.main import app
from app.core.config import settings
from datetime import datetime, timedelta, timezone
import time

TEST_DB_PATH = "./test_full_flow_services.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Remove old test DB if exists
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        
@pytest.fixture(autouse=True)
def reset_db():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
@pytest.fixture
def db_session():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client(db_session, monkeypatch):
    # Override get_db to use our test session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db

    # Patch settings for test isolation
    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 5)
    with TestClient(app) as c:
        yield c



def test_full_service_flow(client):
    username = "flow_user"
    password = "flow_password123"
    token_symbol = "bitcoin"

    # 1. Register
    resp = client.post("/api/v1/register", json={"username": username, "password": password})
    assert resp.status_code == 201
    assert resp.json()["username"] == username

    # 2. Login
    resp = client.post("/api/v1/token", data={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Get user profile
    resp = client.get("/api/v1/users/me/", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == username

    # 4. Trigger prefetch (manual ingestion)
    resp = client.post(f"/api/v1/prices/prefetch/{token_symbol}", headers=headers)
    assert resp.status_code == 202

    # 5. Wait for ingestion (poll for up to 10 seconds)
    for _ in range(10):
        resp = client.get(f"/api/v1/prices/latest/{token_symbol}?granularity=5min", headers=headers)
        if resp.status_code == 200:
            break
        time.sleep(1)
    else:
        assert False, f"Latest price for {token_symbol} not found after waiting"

    data = resp.json()
    assert data["token_symbol"] == token_symbol.upper()
    assert data["price"] > 0

    # 6. Query historical prices
    now = datetime.now(timezone.utc)
    end_time = now.isoformat(timespec='seconds') + "Z"
    start_time = (now - timedelta(hours=1)).isoformat(timespec='seconds') + "Z"
    resp = client.get(
        f"/api/v1/prices/{token_symbol}?granularity=5min&start_time={start_time}&end_time={end_time}",
        headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert resp.json()[0]["token_symbol"] == token_symbol.upper()

    # 7. Rate limit enforcement
    for i in range(settings.RATE_LIMIT_PER_MINUTE):
        r = client.get("/api/v1/users/me/", headers=headers)
        assert r.status_code == 200
    r = client.get("/api/v1/users/me/", headers=headers)
    assert r.status_code == 429
    assert "Rate limit exceeded" in r.json()["detail"]