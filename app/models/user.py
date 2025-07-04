"""This module defines the User model for authentication and user management."""
from passlib.context import CryptContext
from sqlalchemy import Column, Integer, String, Boolean
from app.core.db import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    """Model representing a user in the system."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    def verify_password(self, password: str) -> bool:
        """Verify the provided password against the stored hashed password."""
        return pwd_context.verify(password, self.hashed_password)

    def __repr__(self):
        """String representation of the User model."""
        return f"<User(username='{self.username}', is_active={self.is_active})>"