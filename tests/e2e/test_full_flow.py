# tests/e2e/test_full_flow.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import asyncio
import time

# Import helper functions from test_api.py (or copy them if preferred)
# Assuming test_api.py is in the same folder as test_full_flow.py,
# we can import its helper functions.
from tests.integration.test_api import create_test_user, get_auth_token

# Import actual services to potentially interact with background tasks
from app.services.ingestion_service import ingest_token_price
from app.services.aggregation_service import run_hourly_aggregation, run_daily_aggregation, run_data_retention_job
from app.crud.token_price import get_token_prices, get_latest_token_price

# Use pytest-asyncio for async test functions
pytestmark = pytest.mark.asyncio

async def simulate_background_tasks(db_session, token_symbol="bitcoin", sleep_duration=3):
    """
    Helper to run a short ingestion and aggregation cycle for E2E tests.
    In a real E2E environment, you might let the app run longer or have a more robust polling.
    For this test, we simulate direct calls to the background functions.
    """
    print(f"\nSimulating ingestion for {token_symbol}...")
    await ingest_token_price(token_symbol)
    await asyncio.sleep(sleep_duration) # Give some time for ingestion to complete and DB write

    print("Simulating hourly aggregation...")
    await run_hourly_aggregation()
    await asyncio.sleep(sleep_duration)

    print("Simulating daily aggregation...")
    await run_daily_aggregation()
    await asyncio.sleep(sleep_duration)

    print("Simulating data retention job (briefly)...")
    await run_data_retention_job()
    await asyncio.sleep(sleep_duration)

async def test_full_user_flow(client: TestClient, db_session: Session):
    """
    Tests the full end-to-end flow:
    1. User registration
    2. User login & token retrieval
    3. Accessing a protected endpoint (user profile)
    4. Triggering price prefetch (manual ingestion)
    5. Waiting for ingestion/aggregation to potentially occur (simulated)
    6. Querying latest price
    7. Querying historical prices
    8. Testing rate limit enforcement
    """
    print("\n--- E2E Test: Full User Flow Started ---")

    # 1. Register a new user
    username = "e2e_user"
    password = "e2e_password123"
    print(f"Registering user: {username}")
    register_response = client.post("/api/v1/register", json={"username": username, "password": password})
    assert register_response.status_code == 201
    assert register_response.json()["username"] == username
    print(f"User {username} registered successfully.")

    # 2. Login and get an access token
    print(f"Logging in user: {username}")
    token_response = client.post(
        "/api/v1/token",
        data={"username": username, "password": password}
    )
    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    print("User logged in, token obtained.")

    # 3. Verify the user profile endpoint
    print("Verifying user profile access...")
    profile_response = client.get("/api/v1/users/me/", headers=headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["username"] == username
    print("User profile accessed successfully.")

    # 4. Trigger a manual price prefetch for a token
    #    This will call `ingest_token_price` in the background
    token_symbol = "litecoin"
    print(f"Triggering manual price prefetch for {token_symbol}...")
    prefetch_response = client.post(f"/api/v1/prices/prefetch/{token_symbol}", headers=headers)
    assert prefetch_response.status_code == 202
    assert "initiated" in prefetch_response.json()["message"]
    print(f"Prefetch for {token_symbol} initiated.")

    # 5. Wait for ingestion and aggregation to run a few cycles
    #    In a real app, these are automatic background tasks. For E2E tests
    #    on an ephemeral DB, we might need to explicitly trigger/wait.
    #    We'll simulate by directly calling the service functions
    await simulate_background_tasks(db_session, token_symbol=token_symbol, sleep_duration=0.1) # Short sleep for tests

    # 6. Query the latest price for that token
    print(f"Querying latest price for {token_symbol}...")
    latest_price_response = client.get(f"/api/v1/prices/latest/{token_symbol}?granularity=5min", headers=headers)
    assert latest_price_response.status_code == 200
    assert latest_price_response.json()["token_symbol"] == token_symbol.upper()
    assert latest_price_response.json()["price"] > 0
    print(f"Latest price for {token_symbol}: {latest_price_response.json()['price']}")

    # 7. Query historical prices (e.g., for the last hour)
    now = datetime.now(timezone.utc)
    end_time = now.isoformat(timespec='seconds') + "Z"
    start_time = (now - timedelta(hours=1)).isoformat(timespec='seconds') + "Z"

    print(f"Querying historical prices for {token_symbol} (last hour, 5min granularity)...")
    historical_response = client.get(
        f"/api/v1/prices/{token_symbol}?granularity=5min&start_time={start_time}&end_time={end_time}",
        headers=headers
    )
    assert historical_response.status_code == 200
    assert len(historical_response.json()) >= 1 # Expect at least the ingested point
    assert historical_response.json()[0]["token_symbol"] == token_symbol.upper()
    print(f"Retrieved {len(historical_response.json())} historical data points for {token_symbol}.")

    # 8. Test rate limit enforcement
    print(f"Testing rate limit (max {settings.RATE_LIMIT_PER_MINUTE} req/min)...")
    # Make requests up to the limit
    for i in range(settings.RATE_LIMIT_PER_MINUTE):
        response = client.get("/api/v1/users/me/", headers=headers)
        assert response.status_code == 200, f"Expected 200 for request {i+1}, got {response.status_code}"
    
    # Make one more request, which should be rate limited
    print("Making one more request to trigger rate limit...")
    rate_limited_response = client.get("/api/v1/users/me/", headers=headers)
    assert rate_limited_response.status_code == 429
    assert "Rate limit exceeded" in rate_limited_response.json()["detail"]
    print("Rate limit successfully enforced (status 429).")

    print("\n--- E2E Test: Full User Flow Completed Successfully ---")