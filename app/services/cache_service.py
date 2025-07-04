import json
from typing import Optional
from app.core.config import settings
from datetime import datetime, timedelta
import asyncio

# Simple in-memory cache with TTL
_cache = {} # key: (value, expiry_timestamp)

async def _cache_cleanup_loop(interval_seconds: int = 60):
    """Background task to periodically clean expired items from the cache."""
    while True:
        await asyncio.sleep(interval_seconds)
        now = datetime.now()
        keys_to_delete = [key for key, (value, expiry) in _cache.items() if expiry < now]
        for key in keys_to_delete:
            del _cache[key]
        # print(f"Cache cleanup: Removed {len(keys_to_delete)} expired items.")

async def connect_redis():
    """Initializes the in-memory cache and starts cleanup."""
    # For in-memory cache, connection is implicit.
    # Start background cleanup task.
    asyncio.create_task(_cache_cleanup_loop())
    print("In-memory cache initialized.")

async def disconnect_redis():
    """No explicit disconnection for in-memory cache."""
    pass

async def set_cache(key: str, value: dict, expire: int = 300):
    """Sets a value in in-memory cache with an expiry."""
    expiry_time = datetime.now() + timedelta(seconds=expire)
    _cache[key] = (value, expiry_time)

async def get_cache(key: str) -> Optional[dict]:
    """Gets a value from in-memory cache, returning None if expired or not found."""
    if key in _cache:
        value, expiry_time = _cache[key]
        if expiry_time > datetime.now():
            return value
        else:
            # Item expired, remove it proactively
            del _cache[key]
    return None

async def invalidate_cache(key: str):
    """Invalidates a specific cache key from in-memory cache."""
    if key in _cache:
        del _cache[key]