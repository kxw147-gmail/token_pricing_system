"""Module providing settings for the application."""

from typing import Optional

from pydantic.v1 import BaseSettings

class Settings(BaseSettings):
    """Class representing settings for the application."""
    class Config:
        """Configuration for the settings class."""
        env_file = '.env'
        extra = 'ignore'

    DATABASE_URL: str
    COINGECKO_API_KEY: Optional[str] = None # API key for CoinGecko
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3" # Default API URL
    COINGECKO_TOKEN_LIST_URL: str = "https://api.coingecko.com/api/v3/coins/list" # Default token list
    COINGECKO_PRICE_URL: str = "https://api.coingecko.com/api/v3/simple/price" # Default price endpoint
    COINGECKO_HISTORICAL_PRICE_URL: str = "https://api.coingecko.com/api/v3/coins/{id}/market_chart/range" # Default historical price endpoint
    COINGECKO_AGGREGATED_PRICE_URL: str = "https://api.coingecko.com/api/v3/coins/{id}/market_chart" # Default aggregated price endpoint
    COINGECKO_AGGREGATED_PRICE_HOURLY_URL: str = "https://api.coingecko.com/api/v3/coins/{id}/market_chart?vs_currencies=usd&days=1&interval=hourly" # Default hourly aggregated price endpoint
    COINGECKO_AGGREGATED_PRICE_DAILY_URL: str = "https://api.coingecko.com/api/v3/coins/{id}/market_chart?vs_currencies=usd&days=30&interval=daily" # Default daily aggregated price endpoint
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60
    DATA_RETENTION_RAW_DAYS: int = 30 # Retain raw data for 30 days in DB
    DATA_RETENTION_AGG_DAYS: int = 365 * 5 # Retain aggregated data for 5 years in DB

settings = Settings()
