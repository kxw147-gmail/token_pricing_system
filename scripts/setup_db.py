import sys
import os
from sqlalchemy import text

# Add parent directory to path to allow imports from `app`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import engine, Base
from app.models.token_price import TokenPrice # Import models to create tables
from app.models.user import User

def create_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

# No TimescaleDB specific functions needed for SQLite
# Data retention will be handled by a Python job

if __name__ == "__main__":
    create_tables()
    print("SQLite database setup complete in local_prices.db")