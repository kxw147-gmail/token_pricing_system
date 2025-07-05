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
# CoinGecko API URL and endpoint
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_PRICE_ENDPOINT = "/simple/price"

# Rate limit for CoinGecko API (adjust as per CoinGecko's limits)
# Free tier might be ~10-50 calls/minute, paid tiers much higher.
# Using a conservative 10 calls per minute (1 call every 6 seconds)
rate_limiter = AsyncLimiter(1, 6) # 1 call every 6 seconds

@retry(wait=wait_fixed(5), stop=stop_after_attempt(3), retry=retry_if_exception_type(httpx.RequestError))
async def fetch_price_from_coingecko(token_symbol: str, vs_currency: str = "usd"):
    """Fetches real-time price from CoinGecko API"""
    params = {
        "ids": token_symbol,
        "vs_currencies": vs_currency,
        "x_cg_demo_api_key": settings.COINGECKO_API_KEY # Use if you have a key
    }
    async with httpx.AsyncClient(base_url=COINGECKO_BASE_URL, timeout=10) as client:
        try:
            async with rate_limiter: # Apply rate limiting to external API calls
                response = await client.get(COINGECKO_PRICE_ENDPOINT, params=params)
                response.raise_for_status() # Raises HTTPStatusError for bad responses (4xx or 5xx)
                data = response.json()
                price = data.get(token_symbol, {}).get(vs_currency)
                if price is None:
                    raise ValueError(f"Price for {token_symbol} not found in CoinGecko response: {data}")
                return price
        except httpx.HTTPStatusError as e:
            print(f"HTTP error fetching price for {token_symbol}: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            print(f"Network error fetching price for {token_symbol}: {e}")
            raise
        except ValueError as e:
            print(f"Data parsing error for {token_symbol}: {e}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred for {token_symbol}: {e}")
            raise

async def ingest_token_price(token_symbol: str, vs_currency: str = "usd"):
    """Fetches and stores a single token's 5-minute price data."""
    db: Session = SessionLocal()
    try:
        current_price = await fetch_price_from_coingecko(token_symbol, vs_currency)
        now_utc = datetime.now(timezone.utc)
        # Snap to nearest 5-minute interval for consistency
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
        print(f"Ingested {price_data.token_symbol} price {price_data.price} at {price_data.timestamp} (5min)")
    except Exception as e:
        print(f"Failed to ingest price for {token_symbol}: {e}")
    finally:
        db.close()

async def start_ingestion_loop(interval_minutes: int = 5, symbols: List[str] = ["bitcoin", "ethereum"]):
    """Continuously ingests prices for specified symbols."""
    print(f"Starting ingestion loop for {symbols} every {interval_minutes} minutes...")
    while True:
        current_time = datetime.now(timezone.utc)
        print(f"Ingesting at: {current_time}")
        tasks = [ingest_token_price(symbol) for symbol in symbols]
        await asyncio.gather(*tasks)

        # Calculate time to next interval
        next_run_time = current_time + timedelta(minutes=interval_minutes)
        next_run_time = next_run_time - timedelta(minutes=next_run_time.minute % interval_minutes,
                                                   seconds=next_run_time.second,
                                                   microseconds=next_run_time.microsecond)
        sleep_duration = (next_run_time - datetime.now(timezone.utc)).total_seconds()
        if sleep_duration < 0: # If we somehow missed the window, schedule for next interval
            sleep_duration = interval_minutes * 60 + sleep_duration
            if sleep_duration < 0: sleep_duration = 0 # Prevent negative sleep
        print(f"Next ingestion in {sleep_duration:.2f} seconds...")
        await asyncio.sleep(sleep_duration)