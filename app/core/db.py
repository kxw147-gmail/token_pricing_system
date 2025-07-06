""" Database connection and session management for the application."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
print(f"Connecting to database at {settings.DATABASE_URL}")
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency that provides a database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() # Ensure the session is closed after use