"""
Trade request/response schemas.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class BuyRequest(BaseModel):
    company_id: uuid.UUID
    amount: float = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class SellRequest(BaseModel):
    company_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    amount: float | None = Field(default=None, gt=0)
    shares: float | None = Field(default=None, gt=0)
    sell_all: bool = False

    @model_validator(mode="after")
    def exactly_one_mode(self) -> "SellRequest":
        modes_selected = sum([
            self.amount is not None,
            self.shares is not None,
            self.sell_all,
        ])
        if modes_selected != 1:
            raise ValueError(
                "Specify exactly one of: amount, shares, sell_all"
            )
        return self


class TradeOut(BaseModel):
    trade_id: uuid.UUID
    company_id: uuid.UUID
    type: str
    currency_amount: float
    shares: float
    execution_price: float
    status: str
    rejection_reason: str
    timestamp: datetime
    idempotency_key: str

    model_config = {"from_attributes": True}


class PriceHistoryPoint(BaseModel):
    price: float
    sequence_number: int
    timestamp: datetime
