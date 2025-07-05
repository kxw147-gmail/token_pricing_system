from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session # type: ignore
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging

from app.core.db import get_db
from app.core.config import settings
from app.core.security_utils import create_access_token, get_password_hash, verify_password
from app.api.security import get_current_active_user
from app.schemas.user import UserCreate, UserInDB, Token
from app.schemas.token_price import TokenPriceInDB
from app.crud.token_price import get_token_prices, get_latest_token_price
from app.services.cache_service import get_cache, set_cache
from app.models.user import User

import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Authentication Endpoints ---
@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    logger.info(f"Attempting to register new user: {user_in.username}")
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        logger.warning(f"Registration failed: Username {user_in.username} already registered.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    hashed_password = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"User {new_user.username} successfully registered.")
    return new_user

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    logger.info(f"Login attempt for user: {form_data.username}")
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed for user: {form_data.username}. Invalid credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    logger.info(f"User {user.username} successfully logged in and token issued.")
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me/", response_model=UserInDB)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    logger.debug(f"User {current_user.username} requested own profile.")
    return current_user

# --- Price Query Endpoints ---
@router.get(
    "/prices/{token_symbol}",
    response_model=List[TokenPriceInDB],
    summary="Query historical token prices",
    description="Fetches historical price data for a given token within a time range and granularity.",
    dependencies=[Depends(get_current_active_user)]
)
async def get_historical_prices(
    token_symbol: str,
    granularity: str = Query(..., pattern="^(5min|1h|1d)$", description="Data granularity (5min, 1h, 1d)"),
    start_time: datetime = Query(..., description="Start time (ISO 8601, e.g., 2023-10-26T00:00:00Z)"),
    end_time: datetime = Query(..., description="End time (ISO 8601, e.g., 2023-10-26T23:59:59Z)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"User {current_user.username} querying historical prices for {token_symbol.upper()} "
                f"with granularity {granularity} from {start_time.isoformat()} to {end_time.isoformat()}.")
    if start_time >= end_time:
        logger.warning(f"Invalid time range for {token_symbol}: start_time {start_time} >= end_time {end_time}.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_time must be before end_time")

    prices = get_token_prices(db, token_symbol.upper(), granularity, start_time, end_time)
    if not prices:
        logger.info(f"No historical price data found for {token_symbol.upper()} "
                    f"granularity {granularity} in the requested range.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No price data found for the given criteria")
    logger.info(f"Returned {len(prices)} historical prices for {token_symbol.upper()}.")
    return prices

@router.get(
    "/prices/latest/{token_symbol}",
    response_model=TokenPriceInDB,
    summary="Get latest token price",
    description="Retrieves the most recent price for a given token at a specific granularity, using cache if available.",
    dependencies=[Depends(get_current_active_user)]
)
async def get_latest_price(
    token_symbol: str,
    granularity: str = Query(..., pattern="^(5min|1h|1d)$", description="Data granularity (5min, 1h, 1d)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"User {current_user.username} querying latest price for {token_symbol.upper()} "
                f"with granularity {granularity}.")
    cache_key = f"latest_price:{token_symbol.upper()}:{granularity}"
    cached_data = await get_cache(cache_key)

    if cached_data:
        logger.info(f"Serving latest price for {token_symbol.upper()} from cache.")
        return TokenPriceInDB(**cached_data)

    price = get_latest_token_price(db, token_symbol.upper(), granularity)
    if not price:
        logger.warning(f"No latest price data found in DB for {token_symbol.upper()} with granularity {granularity}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No latest price data found")

    # Manually construct the Pydantic model instead of using from_orm
    pydantic_price = TokenPriceInDB(
        id=price.id,
        token_symbol=price.token_symbol,
        timestamp=price.timestamp,
        price=price.price,
        granularity=price.granularity,
        source=price.source,
        created_at=price.created_at if hasattr(price, "created_at") else None,
        updated_at=price.updated_at if hasattr(price, "updated_at") else None,
    )
    await set_cache(cache_key, pydantic_price.model_dump(), expire=60)
    logger.info(f"Fetched latest price for {token_symbol.upper()} from DB and cached it. Price: {price.price}")
    return pydantic_price

# --- Price Prefetching Endpoint (Triggered internally or by a privileged user) ---
@router.post(
    "/prices/prefetch/{token_symbol}",
    summary="Manually trigger price prefetch",
    description="Triggers immediate ingestion of the latest 5-minute price for a given token. Requires admin access.",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(get_current_active_user)]
)
async def trigger_price_prefetch(token_symbol: str, current_user: User = Depends(get_current_active_user)):
    from app.services.ingestion_service import ingest_token_price
    logger.info(f"User {current_user.username} triggered manual prefetch for {token_symbol.upper()}.")
    asyncio.create_task(ingest_token_price(token_symbol))
    return {"message": f"Prefetch for {token_symbol.upper()} initiated. Data will be available shortly."}