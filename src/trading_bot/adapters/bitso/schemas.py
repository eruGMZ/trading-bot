"""Pydantic schemas for validating and parsing Bitso REST API responses."""

from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class BitsoErrorPayload(BaseModel):
    """Bitso error detail schema."""

    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    message: str | None = None


class BitsoTickerPayload(BaseModel):
    """Validated ticker payload from Bitso /v3/ticker endpoint."""

    model_config = ConfigDict(extra="ignore")

    book: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    created_at: str | None = None
    spread_pct: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="after")
    def _calculate_spread(self) -> "BitsoTickerPayload":
        if self.ask > Decimal("0"):
            spread = (self.ask - self.bid) / self.ask
            object.__setattr__(self, "spread_pct", spread)
        else:
            object.__setattr__(self, "spread_pct", Decimal("0"))
        return self


class BitsoBalanceItem(BaseModel):
    """Single currency balance item."""

    model_config = ConfigDict(extra="ignore")

    currency: str
    available: Decimal
    locked: Decimal = Decimal("0")
    total: Decimal | None = None


class BitsoBalancePayload(BaseModel):
    """Payload returned by /v3/balance endpoint."""

    model_config = ConfigDict(extra="ignore")

    balances: list[BitsoBalanceItem]


class BitsoOrderPayload(BaseModel):
    """Payload returned upon placing an order."""

    model_config = ConfigDict(extra="ignore")

    oid: str


class BitsoApiResponse(BaseModel, Generic[T]):
    """Generic envelope for Bitso REST responses."""

    model_config = ConfigDict(extra="ignore")

    success: bool
    payload: T | None = None
    error: BitsoErrorPayload | None = None
