"""This module contains integration tests for the API endpoints of the token pricing system."""
from datetime import datetime, timedelta, timezone
import time # For rate limit test
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session # type: ignore
from app.models.user import User
from app.core.security_utils import get_password_hash
from app.schemas.token_price import TokenPriceCreate

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

    start_time = (now - timedelta(minutes=30)).isoformat(timespec='seconds') + "Z"
    end_time = (now + timedelta(minutes=5)).isoformat(timespec='seconds') + "Z"

    response = client.get(
        f"/api/v1/prices/TEST?granularity=5min&start_time={start_time}&end_time={end_time}",
        headers={"Authorization": f"Bearer {token}"}
    )
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
    create_token_price(db_session, price_data)

    response1 = client.get(
        "/api/v1/prices/latest/LATEST?granularity=5min",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 200
    assert response1.json()["price"] == 500.0

    # For a true cache test, you'd observe that the second request is faster
    # or mock the cache service to verify it hit the cache.
    # Here, we just ensure it returns correctly twice.
    response2 = client.get(
        "/api/v1/prices/latest/LATEST?granularity=5min",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 200
    assert response2.json()["price"] == 500.0


def test_rate_limiting(client: TestClient, db_session: Session):
    user = create_test_user(db_session, "rate_limiter_user", "password123")
    token = get_auth_token(client, "rate_limiter_user", "password123")

    headers = {"Authorization": f"Bearer {token}"}
    
    # Make requests up to the limit
    for i in range(settings.RATE_LIMIT_PER_MINUTE):
        response = client.get(
            "/api/v1/users/me/", # A simple authenticated endpoint
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200 for request {i+1}, got {response.status_code}"
    
    # Make one more request, which should be rate limited
    response = client.get(
        "/api/v1/users/me/", # A simple authenticated endpoint
        headers=headers
    )
    assert response.status_code == 429, f"Expected 429 for request {settings.RATE_LIMIT_PER_MINUTE + 1}, got {response.status_code}"
    assert "Rate limit exceeded" in response.json()["detail"]

    # Wait for the rate limit to expire (or part of it) and try again
    time.sleep(61) # Sleep for a bit more than a minute

    response_after_wait = client.get(
        "/api/v1/users/me/",
        headers=headers
    )
    assert response_after_wait.status_code == 200, "Expected 200 after rate limit expires"