""" Main entry point for the FastAPI application, including startup and shutdown events, middleware, and API routes."""
import asyncio
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import endpoints
from app.core.config import settings
from app.services.cache_service import connect_redis, disconnect_redis # Only need connect/disconnect
from app.middleware.rate_limit import RateLimitMiddleware # Custom rate limit middleware

# Import background service functions
from app.services.ingestion_service import start_ingestion_loop
from app.services.aggregation_service import start_aggregation_loop, run_data_retention_job

app = FastAPI(
    title="Token Pricing API",
    description="Local real-time and historical cryptocurrency price data.",
    version="1.0.0",
)

# CORS Middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply custom rate limiting middleware (uses in-memory cache now)
app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.RATE_LIMIT_PER_MINUTE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    await connect_redis()
    symbols_to_ingest = ["bitcoin", "ethereum", "ripple", "solana", "cardano", "dogecoin"]
    ingestion_task = asyncio.create_task(start_ingestion_loop(interval_minutes=5, symbols=symbols_to_ingest))
    aggregation_task = asyncio.create_task(start_aggregation_loop(interval_minutes=60))
    retention_task = asyncio.create_task(run_data_retention_job())
    print("Application startup complete.")

    yield  # Application runs during this time

    # Shutdown actions
    await disconnect_redis()
    print("Application shutdown complete.")

app = FastAPI(
    title="Token Pricing API",
    description="Local real-time and historical cryptocurrency price data.",
    version="1.0.0",
    lifespan=lifespan,
)

# Global Exception Handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handle request validation errors globally."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Include API endpoints
app.include_router(endpoints.router, prefix="/api/v1", tags=["Token Prices", "Authentication"])

@app.get("/")
async def root():
    """Root endpoint to check if the API is running."""
    return {"message": "Welcome to the Token Pricing API. Check /docs for API documentation."}