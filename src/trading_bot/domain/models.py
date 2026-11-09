"""Immutable domain models and value objects.

All entities in the domain layer are represented as frozen dataclasses with slots,
ensuring thread safety, immutability, zero third-party validation overhead,
and strict Decimal precision for all financial figures.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Quote:
    """Market price quote for an asset pair."""

    symbol: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    spread_pct: Decimal
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Position:
    """Active spot trading position."""

    entry_price: Decimal
    amount_btc: Decimal
    entry_time: datetime
    high_since_entry: Decimal


@dataclass(frozen=True, slots=True)
class BotSnapshot:
    """Thread-safe immutable snapshot of the bot operational state."""

    running: bool
    mode: str
    position: Position | None
    pnl_total: Decimal
    pnl_today: Decimal
    trades_today: int
    losses_today: int
    peak_equity: Decimal
    halt_reason: str | None = None
    last_trade_time: datetime | None = None
    last_tick_ok: datetime | None = None
    last_daily_report_date: str | None = None
    last_update_id: int = 0


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Configurable risk and operational limits evaluated by the risk engine."""

    max_trades_day: int = 3
    max_losses_day: int = 2
    capital_ref_mxn: Decimal = Decimal("5000")
    daily_loss_pct: Decimal = Decimal("0.03")
    min_hours_between_trades: Decimal = Decimal("1")
    trading_hours: str = ""


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Persistent audit entry representing an open, close, or stop event."""

    ts: datetime
    event: str
    price: Decimal
    amount_btc: Decimal
    book: str = "btc_mxn"
    id: int | None = None
    amount_mxn: Decimal | None = None
    pnl_mxn: Decimal | None = None
    pnl_pct: Decimal | None = None
    entry_price: Decimal | None = None
    reason: str = ""
    mode: str = "dry_run"


@dataclass(frozen=True, slots=True)
class TradeMetrics:
    """Summary metrics calculated from historical closed trades."""

    total: int
    win_rate: Decimal
    expectancy: Decimal
    profit_factor: Decimal
    max_drawdown_mxn: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
