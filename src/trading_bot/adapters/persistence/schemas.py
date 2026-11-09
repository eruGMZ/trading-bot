"""Pydantic schemas for state persistence and serialization boundaries."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PositionDiskSchema(BaseModel):
    """Disk serialization schema for an open position."""

    model_config = ConfigDict(extra="ignore")

    entry_price: Decimal
    amount_btc: Decimal
    entry_time: str
    high_since_entry: Decimal


class StateDiskSchema(BaseModel):
    """Disk serialization schema for bot state.json file."""

    model_config = ConfigDict(extra="ignore")

    running: bool = True
    halt_reason: str | None = None
    mode: str = "dry_run"
    day: str = Field(description="ISO date string YYYY-MM-DD of the trading day")
    position: PositionDiskSchema | None = None
    trades_today: int = 0
    losses_today: int = 0
    pnl_today: Decimal = Decimal("0")
    pnl_total: Decimal = Decimal("0")
    peak_equity: Decimal | None = None
    last_trade_time: str | None = None
    last_update_id: int = 0
    last_daily_report_date: str | None = None
    last_tick_ok: str | None = None
