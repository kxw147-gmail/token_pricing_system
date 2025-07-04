import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session # type: ignore
from app.crud.token_price import create_token_price, get_hourly_aggregates, get_daily_aggregates
from app.schemas.token_price import TokenPriceCreate
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.token_price import TokenPrice # Needed for retention

async def run_hourly_aggregation():
    """
    Aggregates 5-minute data into hourly data for the last completed hour.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Aggregate for the previous hour
        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=1)

        print(f"Running hourly aggregation for {start_time} to {end_time}...")

        hourly_data_points = get_hourly_aggregates(db, start_time, end_time)
        for dp in hourly_data_points:
            hourly_price = TokenPriceCreate(
                token_symbol=dp.token_symbol,
                # Convert string timestamp back to datetime for schema
                timestamp=datetime.strptime(dp.timestamp_hour_str, '%Y-%m-%d %H:00:00').replace(tzinfo=timezone.utc),
                price=dp.price_avg, # Using average price for hourly aggregate
                granularity='1h',
                source='agg_hourly'
            )
            try:
                create_token_price(db, hourly_price)
                # print(f"Aggregated hourly for {hourly_price.token_symbol} at {hourly_price.timestamp}")
            except Exception as e:
                # Handle UniqueConstraintError if aggregation already ran for this hour
                if "uq_token_granularity_timestamp" in str(e):
                    # print(f"Hourly aggregate for {hourly_price.token_symbol} at {hourly_price.timestamp} already exists. Skipping.")
                    pass
                else:
                    print(f"Error saving hourly aggregate for {dp.token_symbol}: {e}")
        db.commit() # Commit all new aggregations
        print(f"Hourly aggregation for {start_time} to {end_time} completed.")
    except Exception as e:
        print(f"Error during hourly aggregation: {e}")
    finally:
        db.close()


async def run_daily_aggregation():
    """
    Aggregates hourly data (or 5-min if hourly not present) into daily data for the last completed day.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Aggregate for the previous day
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=1)

        print(f"Running daily aggregation for {start_time} to {end_time}...")

        daily_data_points = get_daily_aggregates(db, start_time, end_time)

        for dp in daily_data_points:
            daily_price = TokenPriceCreate(
                token_symbol=dp.token_symbol,
                # Convert string timestamp back to datetime for schema
                timestamp=datetime.strptime(dp.timestamp_day_str, '%Y-%m-%d 00:00:00').replace(tzinfo=timezone.utc),
                price=dp.price_avg, # Using average price for daily aggregate
                granularity='1d',
                source='agg_daily'
            )
            try:
                create_token_price(db, daily_price)
                # print(f"Aggregated daily for {daily_price.token_symbol} at {daily_price.timestamp}")
            except Exception as e:
                if "uq_token_granularity_timestamp" in str(e):
                    # print(f"Daily aggregate for {daily_price.token_symbol} at {daily_price.timestamp} already exists. Skipping.")
                    pass
                else:
                    print(f"Error saving daily aggregate for {dp.token_symbol}: {e}")
        db.commit()
        print(f"Daily aggregation for {start_time} to {end_time} completed.")
    except Exception as e:
        print(f"Error during daily aggregation: {e}")
    finally:
        db.close()

async def start_aggregation_loop(interval_minutes: int = 60):
    """
    Continuously runs aggregations.
    Hourly aggregation runs every hour.
    Daily aggregation runs once a day (e.g., at midnight UTC).
    """
    print(f"Starting aggregation loop every {interval_minutes} minutes...")
    while True:
        now = datetime.now(timezone.utc)

        # Run hourly aggregation
        await run_hourly_aggregation()

        # Run daily aggregation once a day (e.g., around midnight UTC, slightly offset)
        if now.hour == 0 and now.minute >= 5 and now.minute < 10: # Run between 00:05 and 00:10 UTC
            print("Time to run daily aggregation...")
            await run_daily_aggregation()

        # Calculate time to next interval
        next_run_time = now + timedelta(minutes=interval_minutes)
        next_run_time = next_run_time.replace(minute=(next_run_time.minute // interval_minutes) * interval_minutes,
                                               second=0,
                                               microsecond=0)
        sleep_duration = (next_run_time - datetime.now(timezone.utc)).total_seconds()
        if sleep_duration < 0: sleep_duration = interval_minutes * 60 + sleep_duration
        if sleep_duration < 0: sleep_duration = 0 # Fallback for negative sleep

        print(f"Next aggregation check in {sleep_duration:.2f} seconds...")
        await asyncio.sleep(sleep_duration)

async def run_data_retention_job():
    """Periodically deletes old 5-min granularity data (Python-managed for SQLite)."""
    # This task will run every 6 hours
    while True:
        db: Session = SessionLocal()
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.DATA_RETENTION_RAW_DAYS)
            
            deleted_count = db.query(TokenPrice).filter(
                TokenPrice.timestamp < cutoff_date,
                TokenPrice.granularity == '5min'
            ).delete(synchronize_session=False)
            db.commit()
            print(f"Data retention: Deleted {deleted_count} old '5min' price entries older than {cutoff_date.isoformat()}.")
        except Exception as e:
            db.rollback()
            print(f"Error during data retention job: {e}")
        finally:
            db.close()
        
        await asyncio.sleep(6 * 3600) # Run every 6 hours (6 * 3600 seconds)