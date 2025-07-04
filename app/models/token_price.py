from sqlalchemy import Column, DateTime, Float, String, Integer, UniqueConstraint
from app.core.db import Base
from datetime import datetime

class TokenPrice(Base):
    __tablename__ = "token_prices"

    id = Column(Integer, primary_key=True, index=True)
    token_symbol = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    price = Column(Float, nullable=False)
    granularity = Column(String, nullable=False) # e.g., '5min', '1h', '1d'
    source = Column(String, default="coingecko") # e.g., 'coingecko', 'agg_hourly', 'agg_daily'

    __table_args__ = (
        UniqueConstraint('token_symbol', 'timestamp', 'granularity', name='uq_token_granularity_timestamp'),
    )

    def __repr__(self):
        return f"<TokenPrice(symbol='{self.token_symbol}', timestamp='{self.timestamp}', price={self.price}, granularity='{self.granularity}')>"