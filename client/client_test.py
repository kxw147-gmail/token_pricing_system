import requests
import uuid
from datetime import datetime, timedelta, timezone
import time

BASE_URL = "http://localhost:8000/api/v1"
TEST_USERNAME = f"testuser_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "testpassword"

def run_test_client():
    """Runs e2e tests against the API endpoints as a client."""
    session = requests.Session()

    # --- 1. Trigger backfill (open access) ---
    print("--- Triggering backfill (default symbols) ---")
    try:
        r = session.post(f"{BASE_URL}/backfill")
        print("Backfill:", r.status_code, r.json())
    except Exception as e:
        print(f"Backfill failed: {e}")

    # --- 2. Register a new user ---
    print(f"\n--- Registering user: {TEST_USERNAME} ---")
    try:
        r = session.post(f"{BASE_URL}/register", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
        print("Register:", r.status_code, r.json())
    except Exception as e:
        print(f"Registration failed: {e}")

    # --- 3. Login to get a token ---
    print("\n--- Logging in ---")
    try:
        r = session.post(f"{BASE_URL}/token", data={"username": TEST_USERNAME, "password": TEST_PASSWORD})
        response_json = r.json()
        print("Login:", r.status_code, response_json)
        token = response_json.get("access_token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
    except Exception as e:
        print(f"Login failed: {e}")

    # --- 4. Get current user details ---
    print("\n--- Getting current user ('/users/me/') ---")
    try:
        r = session.get(f"{BASE_URL}/users/me/")
        print("Me:", r.status_code, r.json())
    except Exception as e:
        print(f"Get current user failed: {e}")
        
    # --- 8. Get latest price (always 5min granularity) ---
    print("\n--- Getting latest price for 'bitcoin' (5min granularity) ---")
    try:
        r = session.get(f"{BASE_URL}/prices/latest/bitcoin")
        print("Latest Price:", r.status_code, r.json())
    except Exception as e:
        print(f"Getting latest price failed: {e}")

    # --- 9. Trigger prefetch for 'ethereum' ---
    print("\n--- Triggering prefetch for 'ethereum' ---")
    try:
        r = session.post(f"{BASE_URL}/prices/prefetch/ethereum")
        print("Prefetch:", r.status_code, r.json())
        # Wait a bit for the prefetch to complete
        time.sleep(10)
        print("\n--- Getting latest price for 'ethereum' (5min granularity) after prefetch ---")
        r2 = session.get(f"{BASE_URL}/prices/latest/ethereum")
        print("Latest Price (after prefetch):", r2.status_code, r2.json())
    except Exception as e:
        print(f"Triggering prefetch or verifying latest price failed: {e}")


    # --- 5. Query historical prices (all granularities) ---
    print("\n--- Querying historical prices for 'bitcoin' (all granularities) ---")
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=40)).isoformat()
    end_time = (now - timedelta(days=10)).isoformat()
    params = {
        "start_time": start_time,
        "end_time": end_time
    }
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params)
        print("Historical Prices (all):", r.status_code, r.json())
    except Exception as e:
        print(f"Querying historical prices (all) failed: {e}")

    # --- 6. Query historical prices (one granularity) ---
    print("\n--- Querying historical prices for 'bitcoin' (1d granularity) ---")
    params_one = {
        "granularity": "1d",
        "start_time": start_time,
        "end_time": end_time
    }
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params_one)
        print("Historical Prices (1d):", r.status_code, r.json())
    except Exception as e:
        print(f"Querying historical prices (1d) failed: {e}")

    # --- 7. Query historical prices (multiple granularities) ---
    print("\n--- Querying historical prices for 'bitcoin' (5min & 1d granularities) ---")
    params_multi = [
        ("granularity", "5min"),
        ("granularity", "1d"),
        ("start_time", start_time),
        ("end_time", end_time)
    ]
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params_multi)
        print("Historical Prices (5min & 1d):", r.status_code, r.json())
    except Exception as e:
        print(f"Querying historical prices (multi) failed: {e}")

  
if __name__ == "__main__":
    run_test_client()