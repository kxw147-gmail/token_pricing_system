from typing import Optional
from app.core.config import settings
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)

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
        if keys_to_delete:
            logger.debug(f"Cache cleanup: Removed {len(keys_to_delete)} expired items.")

async def connect_redis():
    """Initializes the in-memory cache and starts cleanup."""
    asyncio.create_task(_cache_cleanup_loop())
    logger.info("In-memory cache initialized and cleanup task started.")

async def disconnect_redis():
    """No explicit disconnection for in-memory cache."""
    logger.info("In-memory cache disconnection (no action needed for in-memory).")

async def set_cache(key: str, value: dict, expire: int = 300):
    """Sets a value in in-memory cache with an expiry."""
    expiry_time = datetime.now() + timedelta(seconds=expire)
    _cache[key] = (value, expiry_time)
    logger.debug(f"Cache set for key: {key}, expires at: {expiry_time}")

async def get_cache(key: str) -> Optional[dict]:
    """Gets a value from in-memory cache, returning None if expired or not found."""
    if key in _cache:
        value, expiry_time = _cache[key]
        if expiry_time > datetime.now():
            logger.debug(f"Cache hit for key: {key}")
            return value
        else:
            del _cache[key]
            logger.debug(f"Cache expired for key: {key}")
    logger.debug(f"Cache miss for key: {key}")
    return None

async def invalidate_cache(key: str):
    """Invalidates a specific cache key from in-memory cache."""
    if key in _cache:
        del _cache[key]
        logger.info(f"Cache invalidated for key: {key}")