from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session # type: ignore
from app.core.db import get_db
from app.models.user import User
from app.schemas.user import TokenData
from app.core.security_utils import decode_access_token
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        logger.warning("Token decoding failed. Invalid credentials.")
        raise credentials_exception
    username: str = payload.get("sub")
    if username is None:
        logger.warning("Token payload missing 'sub' claim. Invalid credentials.")
        raise credentials_exception
    token_data = TokenData(username=username)
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        logger.warning(f"User {username} from token not found in database.")
        raise credentials_exception
    logger.debug(f"User {username} successfully authenticated.")
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        logger.warning(f"Inactive user {current_user.username} attempted to access restricted resource.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    logger.debug(f"Active user {current_user.username} authorized.")
    return current_user