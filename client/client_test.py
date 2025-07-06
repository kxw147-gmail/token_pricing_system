import requests
import uuid
from datetime import datetime, timedelta, timezone

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_USERNAME = f"testuser_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "testpassword"


def run_test_client():
    """Runs e2e tests against the API endpoints as a client."""
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

    # --- 7. Rate limit test ---
    print("\n--- Testing rate limiting on '/users/me/' ---")
    rate_limit = 60  # Adjust if your server uses a different limit
    hit_429 = False
    for i in range(rate_limit + 2):
        r = session.get(f"{BASE_URL}/users/me/")
        print(f"Request {i+1}: status {r.status_code}")
        if r.status_code == 429:
            print(f"Rate limit hit at request {i+1}: {r.json()}")
            hit_429 = True
            break
    if not hit_429:
        print("Did not hit rate limit after expected number of requests.")

    # --- 8. Query historical prices for 'bitcoin' (hourly) ---
    print("\n--- Querying historical prices for 'bitcoin' (hourly) ---")
    params_hourly = {
        "granularity": "1h",
        "start_time": (now - timedelta(days=2)).isoformat(),
        "end_time": now.isoformat()
    }
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params_hourly)
        r.raise_for_status()
        print("Hourly Prices:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Querying hourly prices failed: {e}")

    # --- 9. Query historical prices for 'bitcoin' (daily) ---
    print("\n--- Querying historical prices for 'bitcoin' (daily) ---")
    params_daily = {
        "granularity": "1d",
        "start_time": (now - timedelta(days=10)).isoformat(),
        "end_time": now.isoformat()
    }
    try:
        r = session.get(f"{BASE_URL}/prices/bitcoin", params=params_daily)
        r.raise_for_status()
        print("Daily Prices:", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Querying daily prices failed: {e}")

    # --- 10. Query historical prices spanning 5min, hourly, daily (all combinations) ---
    print("\n--- Querying historical prices spanning 5min, hourly, daily (all combinations) ---")
    granularities = ["5min", "1h", "1d"]
    spans = [
        ("5min", timedelta(hours=1)),
        ("1h", timedelta(days=2)),
        ("1d", timedelta(days=10)),
        # Cross-boundary: 5min granularity over 2 days, hourly over 10 days, etc.
        ("5min", timedelta(days=2)),
        ("1h", timedelta(days=10)),
        ("1d", timedelta(days=30)),
    ]
    for gran, span in spans:
        params = {
            "granularity": gran,
            "start_time": (now - span).isoformat(),
            "end_time": now.isoformat()
        }
        print(f"\nQuerying {gran} prices over {span}:")
        try:
            r = session.get(f"{BASE_URL}/prices/bitcoin", params=params)
            r.raise_for_status()
            print(f"{gran} Prices:", r.status_code, r.json())
        except requests.exceptions.RequestException as e:
            print(f"Querying {gran} prices over {span} failed: {e}")

    # --- 11. Query price to test cache hit (should be cached) ---
    print("\n--- Querying latest price for 'bitcoin' (should hit cache) ---")
    try:
        r1 = session.get(f"{BASE_URL}/prices/latest/bitcoin", params={"granularity": "5min"})
        r1.raise_for_status()
        print("First fetch (may be remote):", r1.status_code, r1.json())
        r2 = session.get(f"{BASE_URL}/prices/latest/bitcoin", params={"granularity": "5min"})
        r2.raise_for_status()
        print("Second fetch (should be cache):", r2.status_code, r2.json())
    except requests.exceptions.RequestException as e:
        print(f"Cache test failed: {e}")

    # --- 12. Query price to force remote API call (simulate by querying a new token) ---
    print("\n--- Querying latest price for 'newtoken' (should trigger remote API call) ---")
    try:
        r = session.get(f"{BASE_URL}/prices/latest/newtoken", params={"granularity": "5min"})
        print("Remote fetch (new token):", r.status_code, r.json())
    except requests.exceptions.RequestException as e:
        print(f"Remote API call test failed: {e}")



if __name__ == "__main__":
    run_test_client()