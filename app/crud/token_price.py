from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import text, func, distinct
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.token_price import TokenPrice
from app.schemas.token_price import TokenPriceCreate

def create_token_price(db: Session, token_price: TokenPriceCreate):
    db_token_price = TokenPrice(**token_price.model_dump())
    db.add(db_token_price)
    db.commit()
    db.refresh(db_token_price)
    return db_token_price

def get_token_price(db: Session, token_price_id: int):
    return db.query(TokenPrice).filter(TokenPrice.id == token_price_id).first()

def get_token_prices(
    db: Session,
    token_symbol: str,
    granularity: str,
    start_time: datetime,
    end_time: datetime,
    skip: int = 0,
    limit: int = 100
) -> List[TokenPrice]:
    return db.query(TokenPrice).filter(
        TokenPrice.token_symbol == token_symbol,
        TokenPrice.granularity == granularity,
        TokenPrice.timestamp >= start_time,
        TokenPrice.timestamp <= end_time
    ).order_by(TokenPrice.timestamp).offset(skip).limit(limit).all()

def get_latest_token_price(db: Session, token_symbol: str, granularity: str):
    return db.query(TokenPrice).filter(
        TokenPrice.token_symbol == token_symbol,
        TokenPrice.granularity == granularity
    ).order_by(TokenPrice.timestamp.desc()).first()

def get_all_token_symbols(db: Session) -> List[str]:
    return [s[0] for s in db.query(distinct(TokenPrice.token_symbol)).all()]

# Aggregation functions (for SQLite, using standard SQL date functions)
def get_hourly_aggregates(db: Session, start_time: datetime, end_time: datetime):
    # Standard SQL aggregation for hourly. Note: SQLite does not have a direct equivalent to `time_bucket`.
    # We use `strftime` for grouping.
    # For `price_last` and `price_first` for SQLite, true last/first in group is complex.
    # We will use `AVG` for simplicity, or specific subqueries for more accurate OHLCV.
    return db.query(
        TokenPrice.token_symbol,
        func.strftime('%Y-%m-%d %H:00:00', TokenPrice.timestamp).label('timestamp_hour_str'),
        func.avg(TokenPrice.price).label('price_avg'), # Using average as a simple representation
        func.max(TokenPrice.price).label('price_high'), # Max price in the hour
        func.min(TokenPrice.price).label('price_low'), # Min price in the hour
        func.count().label('num_data_points')
    ).filter(
        TokenPrice.granularity == '5min',
        TokenPrice.timestamp >= start_time,
        TokenPrice.timestamp < end_time
    ).group_by(
        TokenPrice.token_symbol,
        func.strftime('%Y-%m-%d %H:00:00', TokenPrice.timestamp)
    ).order_by(
        TokenPrice.token_symbol, 'timestamp_hour_str'
    ).all()

def get_daily_aggregates(db: Session, start_time: datetime, end_time: datetime):
    # Standard SQL aggregation for daily.
    return db.query(
        TokenPrice.token_symbol,
        func.strftime('%Y-%m-%d 00:00:00', TokenPrice.timestamp).label('timestamp_day_str'),
        func.avg(TokenPrice.price).label('price_avg'),
        func.max(TokenPrice.price).label('price_high'),
        func.min(TokenPrice.price).label('price_low'),
        func.count().label('num_data_points')
    ).filter(
        TokenPrice.granularity == '5min', # or '1h' if you store hourly aggregates
        TokenPrice.timestamp >= start_time,
        TokenPrice.timestamp < end_time
    ).group_by(
        TokenPrice.token_symbol,
        func.strftime('%Y-%m-%d 00:00:00', TokenPrice.timestamp)
    ).order_by(
        TokenPrice.token_symbol, 'timestamp_day_str'
    ).all()