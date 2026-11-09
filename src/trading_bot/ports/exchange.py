"""Exchange communication port interface."""

from decimal import Decimal
from typing import Protocol, runtime_checkable

from trading_bot.domain.models import Quote


@runtime_checkable
class ExchangePort(Protocol):
    """Port interface for market data querying and order execution."""

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        """Fetch the current market quote for the specified book."""
        ...

    def get_available_balance(self, asset: str) -> Decimal:
        """Fetch the available balance for an asset (e.g. 'btc' or 'mxn')."""
        ...

    def place_order(
        self,
        book: str,
        side: str,
        amount_btc: Decimal | None = None,
        amount_mxn: Decimal | None = None,
    ) -> str:
        """Place a market order and return the order ID string.

        Args:
            book: Market pair identifier (e.g. 'btc_mxn').
            side: 'buy' or 'sell'.
            amount_btc: Quantity of BTC to sell (major asset).
            amount_mxn: Quantity of MXN to spend on buy (minor asset).

        Returns:
            Order ID returned by the exchange or simulator.
        """
        ...
