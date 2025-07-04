from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class TokenPriceBase(BaseModel):
    token_symbol: str = Field(..., example="BTC")
    timestamp: datetime = Field(..., example="2023-10-26T10:00:00Z")
    price: float = Field(..., example=35000.50)
    granularity: Literal["5min", "1h", "1d"] = Field(..., example="5min")
    source: str = Field(default="coingecko", example="coingecko")

class TokenPriceCreate(TokenPriceBase):
    pass

class TokenPriceInDB(TokenPriceBase):
    id: int

    class Config:
        from_attributes = True