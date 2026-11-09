"""Signal provider port interface."""

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class SignalProviderPort(Protocol):
    """Port interface for reading current technical indicator signals."""

    def get_latest_rsi(self) -> tuple[Decimal, float] | None:
        """Return the most recent valid (rsi_value, timestamp_epoch) or None if stale/invalid."""
        ...
