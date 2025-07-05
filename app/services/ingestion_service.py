import httpx
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session # type: ignore
from app.crud.token_price import create_token_price
from app.schemas.token_price import TokenPriceCreate
from app.core.config import settings
from app.core.db import SessionLocal
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type
#from asyncio_rate_limit import RateLimiter # For rate limiting external API calls
from aiolimiter import AsyncLimiter
from typing import List
import logging

logger = logging.getLogger(__name__)

# CoinGecko API URL and endpoint
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_PRICE_ENDPOINT = "/simple/price"

# Rate limit for CoinGecko API (adjust as per CoinGecko's limits)
# Free tier might be ~10-50 calls/minute, paid tiers much higher.
# Using a conservative 10 calls per minute (1 call every 6 seconds)
rate_limiter = AsyncLimiter(1, 6) # 1 call every 6 seconds

@retry(wait=wait_fixed(5), stop=stop_after_attempt(3), retry=retry_if_exception_type(httpx.RequestError))
async def fetch_price_from_coingecko(token_symbol: str, vs_currency: str = "usd"):
    """Fetches real-time price from CoinGecko API."""
    params = {
        "ids": token_symbol,
        "vs_currencies": vs_currency,
        "x_cg_demo_api_key": settings.COINGECKO_API_KEY
    }
    async with httpx.AsyncClient(base_url=COINGECKO_BASE_URL, timeout=10) as client:
        try:
            async with rate_limiter:
                logger.info(f"Attempting to fetch price for {token_symbol} from CoinGecko.")
                response = await client.get(COINGECKO_PRICE_ENDPOINT, params=params)
                response.raise_for_status()
                data = response.json()
                price = data.get(token_symbol, {}).get(vs_currency)
                if price is None:
                    raise ValueError(f"Price for {token_symbol} not found in CoinGecko response: {data}")
                logger.info(f"Successfully fetched price for {token_symbol}: {price}")
                return price
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching price for {token_symbol}: Status {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error fetching price for {token_symbol}: {e}")
            raise
        except ValueError as e:
            logger.error(f"Data parsing error for {token_symbol} from CoinGecko: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred while fetching price for {token_symbol}.")
            raise

async def ingest_token_price(token_symbol: str, vs_currency: str = "usd"):
    """
    Fetches and stores a single token's 5-minute price data.
    """
    db: Session = SessionLocal()
    try:
        current_price = await fetch_price_from_coingecko(token_symbol, vs_currency)
        now_utc = datetime.now(timezone.utc)
        rounded_timestamp = now_utc - timedelta(minutes=now_utc.minute % 5,
                                               seconds=now_utc.second,
                                               microseconds=now_utc.microsecond)

        price_data = TokenPriceCreate(
            token_symbol=token_symbol.upper(),
            timestamp=rounded_timestamp,
            price=current_price,
            granularity='5min',
            source='coingecko'
        )
        create_token_price(db, price_data)
        logger.info(f"Ingested {price_data.token_symbol} price {price_data.price} at {price_data.timestamp} (granularity: {price_data.granularity})")
    except Exception as e:
        logger.error(f"Failed to ingest price for {token_symbol}: {e}")
    finally:
        db.close()

async def start_ingestion_loop(interval_minutes: int = 5, symbols: List[str] = ["bitcoin", "ethereum"]):
    """
    Continuously ingests prices for specified symbols.
    """
    logger.info(f"Starting ingestion loop for {symbols} every {interval_minutes} minutes...")
    while True:
        current_time = datetime.now(timezone.utc)
        logger.info(f"Initiating ingestion for {symbols} at {current_time}.")
        tasks = [ingest_token_price(symbol) for symbol in symbols]
        await asyncio.gather(*tasks)

        next_run_time = current_time + timedelta(minutes=interval_minutes)
        next_run_time = next_run_time - timedelta(minutes=next_run_time.minute % interval_minutes,
                                                   seconds=next_run_time.second,
                                                   microseconds=next_run_time.microsecond)
        sleep_duration = (next_run_time - datetime.now(timezone.utc)).total_seconds()
        if sleep_duration < 0:
            logger.warning(f"Ingestion cycle took longer than interval. Adjusting next run time.")
            sleep_duration = interval_minutes * 60 + sleep_duration
            if sleep_duration < 0: sleep_duration = 0
        
        logger.info(f"Next ingestion for {symbols} scheduled in {sleep_duration:.2f} seconds.")
        await asyncio.sleep(sleep_duration)
14. app/services/aggregation_service.py (Added logger statements)

Python

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session # type: ignore
from app.crud.token_price import create_token_price, get_hourly_aggregates, get_daily_aggregates
from app.schemas.token_price import TokenPriceCreate
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.token_price import TokenPrice
import logging

logger = logging.getLogger(__name__)

async def run_hourly_aggregation():
    """
    Aggregates 5-minute data into hourly data for the last completed hour.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=1)

        logger.info(f"Running hourly aggregation for {start_time.isoformat()} to {end_time.isoformat()} UTC.")

        hourly_data_points = get_hourly_aggregates(db, start_time, end_time)
        if not hourly_data_points:
            logger.info(f"No 5min data found for hourly aggregation in {start_time} to {end_time}.")
            return

        for dp in hourly_data_points:
            hourly_price = TokenPriceCreate(
                token_symbol=dp.token_symbol,
                timestamp=datetime.strptime(dp.timestamp_hour_str, '%Y-%m-%d %H:00:00').replace(tzinfo=timezone.utc),
                price=dp.price_avg,
                granularity='1h',
                source='agg_hourly'
            )
            try:
                create_token_price(db, hourly_price)
                logger.debug(f"Aggregated hourly for {hourly_price.token_symbol} at {hourly_price.timestamp.isoformat()}.")
            except Exception as e:
                if "uq_token_granularity_timestamp" in str(e):
                    logger.debug(f"Hourly aggregate for {hourly_price.token_symbol} at {hourly_price.timestamp.isoformat()} already exists. Skipping.")
                else:
                    logger.error(f"Error saving hourly aggregate for {dp.token_symbol}: {e}", exc_info=True)
        db.commit()
        logger.info(f"Hourly aggregation for {start_time.isoformat()} to {end_time.isoformat()} completed. Processed {len(hourly_data_points)} symbols.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during hourly aggregation: {e}", exc_info=True)
    finally:
        db.close()


async def run_daily_aggregation():
    """
    Aggregates hourly data (or 5-min if hourly not present) into daily data for the last completed day.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=1)

        logger.info(f"Running daily aggregation for {start_time.isoformat()} to {end_time.isoformat()} UTC.")

        daily_data_points = get_daily_aggregates(db, start_time, end_time)
        if not daily_data_points:
            logger.info(f"No 5min data found for daily aggregation in {start_time} to {end_time}.")
            return

        for dp in daily_data_points:
            daily_price = TokenPriceCreate(
                token_symbol=dp.token_symbol,
                timestamp=datetime.strptime(dp.timestamp_day_str, '%Y-%m-%d 00:00:00').replace(tzinfo=timezone.utc),
                price=dp.price_avg,
                granularity='1d',
                source='agg_daily'
            )
            try:
                create_token_price(db, daily_price)
                logger.debug(f"Aggregated daily for {daily_price.token_symbol} at {daily_price.timestamp.isoformat()}.")
            except Exception as e:
                if "uq_token_granularity_timestamp" in str(e):
                    logger.debug(f"Daily aggregate for {daily_price.token_symbol} at {daily_price.timestamp.isoformat()} already exists. Skipping.")
                else:
                    logger.error(f"Error saving daily aggregate for {dp.token_symbol}: {e}", exc_info=True)
        db.commit()
        logger.info(f"Daily aggregation for {start_time.isoformat()} to {end_time.isoformat()} completed. Processed {len(daily_data_points)} symbols.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during daily aggregation: {e}", exc_info=True)
    finally:
        db.close()

async def start_aggregation_loop(interval_minutes: int = 60):
    """
    Continuously runs aggregations.
    Hourly aggregation runs every hour.
    Daily aggregation runs once a day (e.g., at midnight UTC).
    """
    logger.info(f"Starting aggregation loop every {interval_minutes} minutes...")
    while True:
        now = datetime.now(timezone.utc)

        await run_hourly_aggregation()

        if now.hour == 0 and now.minute >= 5 and now.minute < 10:
            logger.info("Time to run daily aggregation based on time condition.")
            await run_daily_aggregation()

        next_run_time = now + timedelta(minutes=interval_minutes)
        next_run_time = next_run_time.replace(minute=(next_run_time.minute // interval_minutes) * interval_minutes,
                                               second=0,
                                               microsecond=0)
        sleep_duration = (next_run_time - datetime.now(timezone.utc)).total_seconds()
        if sleep_duration < 0:
            logger.warning("Aggregation cycle took longer than interval. Adjusting next run time.")
            sleep_duration = interval_minutes * 60 + sleep_duration
            if sleep_duration < 0: sleep_duration = 0

        logger.info(f"Next aggregation check in {sleep_duration:.2f} seconds.")
        await asyncio.sleep(sleep_duration)

async def run_data_retention_job():
    """Periodically deletes old 5-min granularity data."""
    logger.info("Starting data retention job loop.")
    while True:
        db: Session = SessionLocal()
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.DATA_RETENTION_RAW_DAYS)
            
            deleted_count = db.query(TokenPrice).filter(
                TokenPrice.timestamp < cutoff_date,
                TokenPrice.granularity == '5min'
            ).delete(synchronize_session=False)
            db.commit()
            if deleted_count > 0:
                logger.info(f"Data retention: Deleted {deleted_count} old '5min' price entries older than {cutoff_date.isoformat()}.")
            else:
                logger.debug(f"Data retention: No old '5min' price entries to delete older than {cutoff_date.isoformat()}.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error during data retention job: {e}", exc_info=True)
        finally:
            db.close()
        
        # This job is not time-critical, so a longer sleep is fine.
        sleep_duration = 6 * 3600 # Run every 6 hours
        logger.info(f"Next data retention run in {sleep_duration / 3600:.2f} hours.")
        await asyncio.sleep(sleep_duration)
15. app/middlewares/rate_limit.py (Added logger statements)

Python

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