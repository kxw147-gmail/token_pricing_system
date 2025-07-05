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