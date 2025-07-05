import httpx
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session # type: ignore
from app.crud.token_price import create_token_price
from app.schemas.token_price import TokenPriceCreate
from app.core.config import settings
from app.core.db import SessionLocal
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type
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