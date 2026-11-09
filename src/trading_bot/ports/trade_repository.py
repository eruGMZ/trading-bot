"""Trade history and accounting repository port interface."""

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from trading_bot.domain.models import TradeMetrics


@runtime_checkable
class TradeRepositoryPort(Protocol):
    """Port interface for trade history audit logs and accounting metrics."""

    def init_db(self) -> None:
        """Initialize the storage schema if not present."""
        ...

    def log_open(
        self,
        price: Decimal,
        amount_btc: Decimal,
        amount_mxn: Decimal,
        reason: str,
        mode: str,
        book: str = "btc_mxn",
    ) -> None:
        """Record the opening of a position."""
        ...

    def log_close(
        self,
        event: str,
        entry_price: Decimal,
        exit_price: Decimal,
        amount_btc: Decimal,
        pnl_mxn: Decimal,
        pnl_pct: Decimal,
        reason: str,
        mode: str,
        book: str = "btc_mxn",
    ) -> None:
        """Record the closing or stop of a position."""
        ...

    def get_metrics(self) -> TradeMetrics | dict[str, Any]:
        """Compute performance metrics from historical closed operations."""
        ...
