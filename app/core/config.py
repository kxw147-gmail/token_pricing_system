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
    COINGECKO_API_KEY: Optional[str] = None
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60
    DATA_RETENTION_RAW_DAYS: int = 30 # Retain raw data for 30 days in DB
    DATA_RETENTION_AGG_DAYS: int = 365 * 5 # Retain aggregated data for 5 years in DB

settings = Settings()
