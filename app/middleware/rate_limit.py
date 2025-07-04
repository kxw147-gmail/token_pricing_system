from fastapi import Request, Response, HTTPException, status
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse # type: ignore
from app.core.config import settings
from app.core.security_utils import decode_access_token
import time
from app.services.cache_service import _cache # Import the in-memory cache directly

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = 60):
        super().__init__(app)
        self.limit_per_minute = limit_per_minute

    async def dispatch(self, request: Request, call_next):
        # Only apply to authenticated routes (or specific paths)
        # This is a simplification; a more robust solution would inspect route handlers
        # and only apply if authentication dependency is present.
        # For this example, it applies if Authorization header exists.
        if "Authorization" not in request.headers:
            return await call_next(request)

        auth_header = request.headers["Authorization"]
        if not auth_header.startswith("Bearer "):
            return await call_next(request) # Or raise error if strict

        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if not payload or not payload.get("sub"):
            return await call_next(request) # JWT invalid, let security dependency handle

        user_id = payload["sub"] # Using username as user_id for simplicity

        # In-memory rate limiting logic
        key = f"rate_limit:{user_id}"
        now = time.time()
        
        # Filter out requests older than 1 minute (60 seconds)
        # _cache[key] stores a list of timestamps of requests made by this user
        _cache[key] = [t for t in _cache.get(key, []) if now - t < 60]
        _cache[key].append(now)
        count = len(_cache[key])
        
        if count > self.limit_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded. Please try again after {int(60 - (now - _cache[key][0]))} seconds."}
            )
        response = await call_next(request)
        return response