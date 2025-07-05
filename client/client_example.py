import requests
import uuid
from datetime import datetime, timedelta, timezone

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_USERNAME = f"testuser_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "testpassword"


def run_test_client():
    """Runs a series of requests to test the API endpoints."""
    session = requests.Session()

    # --- 1. Register a new user ---
    print(f"--- Registering user: {TEST_USERNAME} ---")
    try:
        r = session.post(f"{BASE_URL}/register", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
        r.raise_for_status()
        print("Register:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Registration failed: {e}")
        return

    # --- 2. Login to get a token ---
    print("\n--- Logging in ---")
    try:
        r = session.post(f"{BASE_URL}/token", data={"username": TEST_USERNAME, "password": TEST_PASSWORD})
        r.raise_for_status()
        response_json = r.json()
        print("Login:", r.status_code, response_json)
        token = response_json.get("access_token")
        if not token:
            print("Login failed: No access token in response.")
            return
        session.headers.update({"Authorization": f"Bearer {token}"})
    except requests.exceptions.RequestException as e:
        print(f"Login failed: {e}")
        return

    # --- 3. Get current user details ---
    print("\n--- Getting current user ('/users/me/') ---")
    try:
        r = session.get(f"{BASE_URL}/users/me/")
        r.raise_for_status()
        print("Me:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Get current user failed: {e}")
        return

    # --- 4. Query historical prices ---
    print("\n--- Querying historical prices for 'bitcoin' ---")
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=1)).isoformat()
    end_time = now.isoformat()
    params = {
        "granularity": "5min",
        "start_time": start_time,
        "end_time": end_time
    }
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params)
        r.raise_for_status()
        print("Historical Prices:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Querying historical prices failed: {e}")
        # Continue to next tests

    # --- 5. Get latest price ---
    print("\n--- Getting latest price for 'bitcoin' ---")
    try:
        r = session.get(f"{BASE_URL}/prices/latest/bitcoin", params={"granularity": "5min"})
        r.raise_for_status()
        print("Latest Price:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Getting latest price failed: {e}")
        # Continue to next tests

    # --- 6. Trigger prefetch ---
    print("\n--- Triggering prefetch for 'ethereum' ---")
    try:
        r = session.post(f"{BASE_URL}/prices/prefetch/ethereum")
        r.raise_for_status()
        print("Prefetch:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Triggering prefetch failed: {e}")


if __name__ == "__main__":
    run_test_client()