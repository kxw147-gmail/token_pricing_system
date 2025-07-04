"""This module defines the API endpoints for user authentication and token price queries."""
from datetime import datetime, timedelta
from typing import List
import asyncio # For background task
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session # type: ignore
from app.core.db import get_db
from app.core.config import settings
from app.core.security_utils import create_access_token, get_password_hash, verify_password
from app.api.security import get_current_active_user
from app.schemas.user import UserCreate, UserInDB, Token
from app.schemas.token_price import TokenPriceInDB
from app.crud.token_price import get_token_prices, get_latest_token_price
from app.services.cache_service import get_cache, set_cache # For prefetch/caching
from app.models.user import User
from app.services.ingestion_service import ingest_token_price

router = APIRouter()

# --- Authentication Endpoints ---
@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """_summary_

    Args:
        user_in (UserCreate): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    hashed_password = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """_summary_

    Args:
        form_data (OAuth2PasswordRequestForm, optional): _description_. Defaults to Depends().
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me/", response_model=UserInDB)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """_summary_

    Args:
        current_user (User, optional): _description_. Defaults to Depends(get_current_active_user).

    Returns:
        _type_: _description_
    """
    return current_user

# --- Price Query Endpoints ---
@router.get(
    "/prices/{token_symbol}",
    response_model=List[TokenPriceInDB],
    summary="Query historical token prices",
    description="Fetches historical price data for a given token within a time range and granularity.",
    dependencies=[Depends(get_current_active_user)] # Protect endpoint
)
async def get_historical_prices(
    token_symbol: str,
    granularity: str = Query(..., pattern="^(5min|1h|1d)$", description="Data granularity (5min, 1h, 1d)"),
    start_time: datetime = Query(..., description="Start time (ISO 8601, e.g., 2023-10-26T00:00:00Z)"),
    end_time: datetime = Query(..., description="End time (ISO 8601, e.g., 2023-10-26T23:59:59Z)"),
    db: Session = Depends(get_db)
):
    """_summary_"""    
    if start_time >= end_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_time must be before end_time")

    prices = get_token_prices(db, token_symbol.upper(), granularity, start_time, end_time)
    if not prices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No price data found for the given criteria")
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
    db: Session = Depends(get_db)
):
    """_summary_"""
    cache_key = f"latest_price:{token_symbol.upper()}:{granularity}"
    cached_data = await get_cache(cache_key)

    if cached_data:
        # print("Serving from cache.")
        return TokenPriceInDB(**cached_data)

    # If not in cache, fetch from DB
    price = get_latest_token_price(db, token_symbol.upper(), granularity)
    if not price:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No latest price data found")

    # Store in cache
    await set_cache(cache_key, price.model_dump(), expire=60) # Cache for 60 seconds
    return price

# --- Price Prefetching Endpoint (Triggered internally or by a privileged user) ---
@router.post(
    "/prices/prefetch/{token_symbol}",
    summary="Manually trigger price prefetch",
    description="Triggers immediate ingestion of the latest 5-minute price for a given token. Requires admin access.",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(get_current_active_user)] # Or a more specific admin role
)
async def trigger_price_prefetch(token_symbol: str):
    """Run ingestion in the background without blocking the API response"""
    asyncio.create_task(ingest_token_price(token_symbol))
    return {"message": f"Prefetch for {token_symbol} initiated. Data will be available shortly."}