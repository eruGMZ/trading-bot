"""Pydantic DTOs for validating and parsing Bitso REST API responses."""

from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class BitsoErrorDTO(BaseModel):
    """Bitso error detail DTO."""

    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    message: str | None = None


class BitsoTickerDTO(BaseModel):
    """Validated ticker DTO from Bitso /v3/ticker endpoint."""

    model_config = ConfigDict(extra="ignore")

    book: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    created_at: str | None = None
    spread_pct: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="after")
    def _calculate_spread(self) -> "BitsoTickerDTO":
        if self.ask > Decimal("0"):
            spread = (self.ask - self.bid) / self.ask
            object.__setattr__(self, "spread_pct", spread)
        else:
            object.__setattr__(self, "spread_pct", Decimal("0"))
        return self


class BitsoBalanceItemDTO(BaseModel):
    """Single currency balance item DTO."""

    model_config = ConfigDict(extra="ignore")

    currency: str
    available: Decimal
    locked: Decimal = Decimal("0")
    total: Decimal | None = None


class BitsoBalanceDTO(BaseModel):
    """Payload DTO returned by /v3/balance endpoint."""

    model_config = ConfigDict(extra="ignore")

    balances: list[BitsoBalanceItemDTO]


class BitsoOrderDTO(BaseModel):
    """Payload DTO returned upon placing an order."""

    model_config = ConfigDict(extra="ignore")

    oid: str


class BitsoApiResponseDTO(BaseModel, Generic[T]):
    """Generic envelope DTO for Bitso REST responses."""

    model_config = ConfigDict(extra="ignore")

    success: bool
    payload: T | None = None
    error: BitsoErrorDTO | None = None
