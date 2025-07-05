"""This module contains integration tests for the API endpoints of the token pricing system."""
from datetime import datetime, timedelta, timezone
import time # For rate limit test
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session # type: ignore
from app.models.user import User
from app.core.security_utils import get_password_hash
from app.schemas.token_price import TokenPriceCreate
from app.middleware import rate_limit

# Import settings for RATE_LIMIT_PER_MINUTE
from app.core.config import settings

def create_test_user(db: Session, username: str, password: str):
    """Helper function to create a test user in the database."""
    hashed_password = get_password_hash(password)
    user = User(username=username, hashed_password=hashed_password, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_auth_token(client: TestClient, username, password):
    """Helper function to get an authentication token for a user."""
    response = client.post(
        "/api/v1/token",
        data={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

def test_register_user(client: TestClient, db_session: Session):
    """Test user registration endpoint."""
    user_data = {"username": "testuser_reg", "password": "password123"}
    response = client.post("/api/v1/register", json=user_data)
    assert response.status_code == 201
    assert response.json()["username"] == "testuser_reg"
    assert "hashed_password" in response.json()

def test_login_and_get_me(client: TestClient, db_session: Session):
    """Test user login and fetching user details."""
    create_test_user(db_session, "testuser_login", "password123")
    token = get_auth_token(client, "testuser_login", "password123")

    response = client.get(
        "/api/v1/users/me/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser_login"

def test_get_historical_prices(client: TestClient, db_session: Session):
    user = create_test_user(db_session, "testuser_hist", "password123")
    token = get_auth_token(client, "testuser_hist", "password123")

    # Add some test data
    now = datetime.now(timezone.utc)
    for i in range(5):
        price_data = TokenPriceCreate(
            token_symbol="TEST",
            timestamp=now - timedelta(minutes=i * 5),
            price=100.0 + i,
            granularity="5min",
            source="test"
        )
        # Manually create using DB session to bypass API for data setup
        from app.crud.token_price import create_token_price
        create_token_price(db_session, price_data)

    start_time = (now - timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time = (now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
   
    
    response = client.get(
        f"/api/v1/prices/TEST?granularity=5min&start_time={start_time}&end_time={end_time}",
        headers={"Authorization": f"Bearer {token}"}
    )
    print("RESPONSE:", response.status_code, response.json())  # For debugging
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["token_symbol"] == "TEST"

def test_get_latest_price_cached(client: TestClient, db_session: Session):
    user = create_test_user(db_session, "testuser_latest", "password123")
    token = get_auth_token(client, "testuser_latest", "password123")

    # Add a latest price
    latest_time = datetime.now(timezone.utc)
    price_data = TokenPriceCreate(
        token_symbol="LATEST",
        timestamp=latest_time,
        price=500.0,
        granularity="5min",
        source="test"
    )
    from app.crud.token_price import create_token_price
    created = create_token_price(db_session, price_data)
    assert created.token_symbol == "LATEST"
    assert created.price == 500.0

    response1 = client.get(
        "/api/v1/prices/latest/LATEST?granularity=5min",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 200
    assert response1.json()["price"] == 500.0

    response2 = client.get(
        "/api/v1/prices/latest/LATEST?granularity=5min",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 200
    assert response2.json()["price"] == 500.0


# Test rate limiting middleware moving to a client test
""" def test_rate_limiting(client: TestClient, db_session: Session, monkeypatch):
    user = create_test_user(db_session, "rate_limit_user", "password123")
    token = get_auth_token(client, "rate_limit_user", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(settings.RATE_LIMIT_PER_MINUTE):
        response = client.get("/api/v1/users/me/", headers=headers)
        assert response.status_code == 200

    response = client.get("/api/v1/users/me/", headers=headers)
    assert response.status_code == 429 """