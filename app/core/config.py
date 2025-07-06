"""Module providing settings for the application"""
from typing import Optional, List, Union
from pydantic.v1 import BaseSettings, validator 

class Settings(BaseSettings):
    """Class representing settings for the application"""
    class Config:
        env_file = '.env'
        extra = 'ignore'

    DATABASE_URL: str = "sqlite:///./local_prices.db"
    COINGECKO_API_KEY: Optional[str] = None 
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    COINGECKO_TOKEN_LIST_URL: str = "https://api.coingecko.com/api/v3/coins/list"
    COINGECKO_PRICE_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    JWT_SECRET_KEY: str = "764c21e97b924a8e9314990336ad308ab206bd0d264216d437b0daa7d3830784"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60
    DATA_RETENTION_RAW_DAYS: int = 30
    DATA_RETENTION_HOURLY_DAYS: int = 90
    DATA_RETENTION_DAILY_DAYS: int = 1825  # Keep daily aggregates for 5 years
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "app.log"

    @validator("DEFAULT_SYMBOLS", check_fields=False, pre=True)
    def split_default_symbols(cls, v: Union[str, List[str]])  -> List[str]:
        """Allow DEFAULT_SYMBOLS to be a comma-separated string in env vars."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

settings = Settings()