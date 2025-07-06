"""
This service provides an automated, on-demand job to backfill historical
token price data.
"""
import asyncio
import logging
from sqlalchemy.orm import Session
import httpx
from app.core.db import get_db
from datetime import datetime, timezone
from app.core.config import settings
from app.models.token_price import TokenPrice  # avoid circular import
from sqlalchemy.exc import IntegrityError
from app.crud.token_price import bulk_create_token_prices as bulk_insert_token_prices



logger = logging.getLogger(__name__)

async def auto_backfill_job(symbols=None):
    """
    A background job that runs to backfill historical data for the given token symbols.
    If symbols is None, it will backfill all tokens currently tracked in the system.
    """
    logger.info("Starting automatic historical data backfill job...")
    db: Session = next(get_db())
    
    try:
        if symbols is None:
            from app.crud.token_price import get_all_token_symbols
            token_symbols = get_all_token_symbols(db)
        else:
            token_symbols = symbols

        if not token_symbols:
            logger.info("No tokens found to backfill. Exiting job.")
            return

        logger.info(f"Found tokens to backfill: {token_symbols}")
        for symbol in token_symbols:
            try:
                logger.info(f"Starting backfill for token: {symbol}")
                # The backfill function is async and handles fetching and storing data.
                await backfill_historical_data(symbol, db)
                logger.info(f"Successfully completed backfill for token: {symbol}")
            except Exception as e:
                logger.error(f"Error during backfill for token {symbol}: {e}", exc_info=True)
            # Add a small delay between tokens to be considerate to the external API.
            await asyncio.sleep(10)
    except Exception as e:
        logger.error(f"An unexpected error occurred in the main backfill job: {e}", exc_info=True)
    finally:
        db.close()
    logger.info("Automatic historical data backfill job finished.")

async def run_auto_backfill_loop(initial_delay_seconds: int = 60, run_interval_hours: int = 24, symbols=None):
    """Runs the backfill job periodically in a loop."""
    await asyncio.sleep(initial_delay_seconds)
    while True:
        await auto_backfill_job(symbols)
        logger.info(f"Auto-backfill loop finished. Sleeping for {run_interval_hours} hours.")
        await asyncio.sleep(run_interval_hours * 3600)  # Sleep for the specified interval


async def backfill_historical_data(symbol: str, db):
    """
    Fetches up to 6 months of daily historical prices for the given symbol from CoinGecko,
    and stores them in the database using bulk insert for efficiency.
    """
    logger.info(f"Backfilling historical data for {symbol} from CoinGecko...")
    coingecko_id = symbol.lower()
    url = f"{settings.COINGECKO_API_URL}/coins/{coingecko_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "180",  # up to 6 months
        "interval": "daily"
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch data from CoinGecko for {symbol}: {e}")
        return

    prices = data.get("prices", [])
    if not prices:
        logger.warning(f"No price data returned from CoinGecko for {symbol}")
        return
    logger.info(f"Fetched {len(prices)} price points for {symbol} from CoinGecko.")

    token_price_objs = []
    for price_point in prices:
        ts_ms, price = price_point
        timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        token_price = TokenPrice(
            token_symbol=symbol.upper(),
            timestamp=timestamp,
            price=price,
            granularity="1d",
            source="coingecko"
        )
        token_price_objs.append(token_price)

    if not token_price_objs:
        logger.info(f"No new token price objects to insert for {symbol}.")
        return

    try:
        inserted = bulk_insert_token_prices(db, token_price_objs)
        logger.info(f"Backfill complete for {symbol}: {inserted} daily prices inserted (bulk).")
    except IntegrityError:
        db.rollback()
        logger.warning(f"Some prices for {symbol} already existed. Bulk insert skipped duplicates.")
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk insert error for {symbol}: {e}")