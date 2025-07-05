""" Main entry point for the FastAPI application, including startup and shutdown events, middleware, and API routes."""
import asyncio
import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.api import endpoints
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.db import Base, engine
from app.services.cache_service import connect_redis, disconnect_redis # Only need connect/disconnect
from app.middleware.rate_limit import RateLimitMiddleware # Custom rate limit middleware

# Import background service functions
from app.services.ingestion_service import start_ingestion_loop
from app.services.aggregation_service import start_aggregation_loop, run_data_retention_job

# Set up logging first
setup_logging()
logger = logging.getLogger(__name__)

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
    logger.info("Application startup initiated.")
    # Ensure database tables exist
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured to exist.")
    except Exception as e:
        logger.critical(f"Failed to connect to database or create tables: {e}", exc_info=True)
        # Depending on criticality, you might want to exit here or just log
        raise
    await connect_redis()
    symbols_to_ingest = ["bitcoin", "ethereum", "ripple", "solana", "cardano", "dogecoin"]
    
    logger.info("Starting background tasks (ingestion, aggregation, retention).")
    asyncio.create_task(start_ingestion_loop(interval_minutes=5, symbols=symbols_to_ingest))
    asyncio.create_task(start_aggregation_loop(interval_minutes=60))
    asyncio.create_task(run_data_retention_job())
    print("Application startup complete.")
    logger.info("Background tasks (ingestion, aggregation, retention) started.")
    logger.info("Application startup complete.")
    yield  # Application runs during this time
   
    # Shutdown actions
    await disconnect_redis()
    print("Application shutdown complete.")
    logger.info("Application shutdown complete.")
app = FastAPI(
    title="Token Pricing API",
    description="Local real-time and historical cryptocurrency price data.",
    version="1.0.0",
    lifespan=lifespan,
)


# Global Exception Handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"Request validation error for {request.method} {request.url.path}: {exc.errors()}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )
    
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle request validation errors globally."""
    if exc.status_code >= 500:
        logger.error(f"HTTP Exception (Server Error) at {request.method} {request.url.path}: {exc.detail}", exc_info=True)
    elif exc.status_code >= 400:
        logger.warning(f"HTTP Exception (Client Error) at {request.method} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
    
# Include API endpoints
app.include_router(endpoints.router, prefix="/api/v1", tags=["Token Prices", "Authentication"])

@app.get("/")
async def root():
    """Root endpoint to check if the API is running."""
    logger.debug("Root endpoint accessed.")
    return {"message": "Welcome to the Token Pricing API. Check /docs for API documentation."}