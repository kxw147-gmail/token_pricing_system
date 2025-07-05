from fastapi import Request, Response, HTTPException, status
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.security_utils import decode_access_token
import time
from app.services.cache_service import _cache
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = 60):
        super().__init__(app)
        self.limit_per_minute = limit_per_minute
        logger.info(f"RateLimitMiddleware initialized with limit: {limit_per_minute} requests/minute.")

    async def dispatch(self, request: Request, call_next):
        if "Authorization" not in request.headers:
            logger.debug(f"Request to {request.url.path} without Authorization header. Skipping rate limit.")
            return await call_next(request)

        auth_header = request.headers["Authorization"]
        if not auth_header.startswith("Bearer "):
            logger.warning(f"Malformed Authorization header for {request.url.path}.")
            return await call_next(request)

        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if not payload or not payload.get("sub"):
            logger.warning(f"Invalid or missing user in JWT for {request.url.path}. Skipping rate limit and letting security handle.")
            return await call_next(request)

        user_id = payload["sub"]

        key = f"rate_limit:{user_id}"
        now = time.time()
        
        # Filter out requests older than 1 minute (60 seconds)
        _cache[key] = [t for t in _cache.get(key, []) if now - t < 60]
        _cache[key].append(now)
        count = len(_cache[key])
        
        if count > self.limit_per_minute:
            time_remaining = int(60 - (now - _cache[key][0]))
            logger.warning(f"Rate limit exceeded for user: {user_id}. Count: {count}, Limit: {self.limit_per_minute}. Blocking request to {request.url.path}.")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded. Please try again after {time_remaining} seconds."}
            )
        
        logger.debug(f"User {user_id} request to {request.url.path}. Current requests in last minute: {count}/{self.limit_per_minute}.")
        response = await call_next(request)
        return response