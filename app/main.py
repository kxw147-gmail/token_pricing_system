from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
import asyncio

from app.api import endpoints
from app.core.config import settings
from app.core.db import Base, engine # Import Base and engine to ensure tables are registered
from app.services.cache_service import connect_redis, disconnect_redis # Only need connect/disconnect
from app.middlewares.rate_limit import RateLimitMiddleware # Custom rate limit middleware

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


@app.on_event("startup")
async def startup_event():
    # Initialize in-memory cache
    await connect_redis() # This now initializes the in-memory cache cleanup task

    # Start background ingestion and aggregation tasks
    # These tasks will use the shared SQLAlchemy engine and in-memory cache
    # Example symbols to ingest - customize as needed
    symbols_to_ingest = ["bitcoin", "ethereum", "ripple", "solana", "cardano", "dogecoin"]
    asyncio.create_task(start_ingestion_loop(interval_minutes=5, symbols=symbols_to_ingest))
    asyncio.create_task(start_aggregation_loop(interval_minutes=60))
    # Start data retention job to prune old raw data
    asyncio.create_task(run_data_retention_job())


    print("Application startup complete.")


@app.on_event("shutdown")
async def shutdown_event():
    # No explicit disconnection for in-memory cache
    await disconnect_redis()
    print("Application shutdown complete.")

# Global Exception Handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Include API endpoints
app.include_router(endpoints.router, prefix="/api/v1", tags=["Token Prices", "Authentication"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Token Pricing API. Check /docs for API documentation."}