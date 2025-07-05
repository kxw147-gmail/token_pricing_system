"""Module providing settings for the application"""
from typing import Optional
from pydantic.v1 import BaseSettings

class Settings(BaseSettings):
    """Class representing settings for the application"""
    class Config:
        """Configuration for the settings class."""
        env_file = '.env'
        extra = 'ignore'

    DATABASE_URL: str = "sqlite:///./local_prices.db"  # Local SQLite file database
    COINGECKO_API_KEY: Optional[str] = None # API key for CoinGecko
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3" # Default API URL
    COINGECKO_TOKEN_LIST_URL: str = "https://api.coingecko.com/api/v3/coins/list" # Default token list
    COINGECKO_PRICE_URL: str = "https://api.coingecko.com/api/v3/simple/price" # Default price endpoint
    JWT_SECRET_KEY: str = "764c21e97b924a8e9314990336ad308ab206bd0d264216d437b0daa7d3830784"  # Secret key for JWT encoding/decoding
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60
    DATA_RETENTION_RAW_DAYS: int = 30
    DATA_RETENTION_AGG_DAYS: int = 1825
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "app.log"
    
settings = Settings()