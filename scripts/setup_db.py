import sys
import os
import logging

# Add parent directory to path to allow imports from `app`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import engine, Base
from app.models.token_price import TokenPrice
from app.models.user import User
from app.core.logging_config import setup_logging # NEW IMPORT

# Set up logging for the script
setup_logging()
logger = logging.getLogger(__name__)


def create_tables():
    logger.info("Starting database table creation.")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.critical(f"Failed to create database tables: {e}", exc_info=True)
        sys.exit(1) # Exit if table creation fails


if __name__ == "__main__":
    create_tables()
    logger.info("SQLite database setup script completed.")