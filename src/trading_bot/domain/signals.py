"""Pure technical indicator signal evaluation.

Operates deterministically on Decimal values without performing I/O or caching.
"""

from decimal import Decimal
from enum import StrEnum

from trading_bot.core.money import to_decimal


class SignalAction(StrEnum):
    """Trading action derived from indicator signal evaluation."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def validate_rsi(val: Decimal | float | int | str | None) -> Decimal | None:
    """Validate that RSI is a finite Decimal within the bounds [0, 100].

    Args:
        val: Input RSI value.

    Returns:
        Valid Decimal in [0, 100] or None if invalid or out of range.
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        dec = to_decimal(val)
        if dec.is_nan() or dec.is_infinite():
            return None
        if Decimal("0") <= dec <= Decimal("100"):
            return dec
        return None
    except (ValueError, TypeError, ArithmeticError):
        return None


def is_oversold(rsi: Decimal | None, rsi_buy: Decimal) -> bool:
    """Return True if RSI is strictly below the buy threshold (oversold)."""
    return rsi is not None and rsi < rsi_buy


def is_overbought(rsi: Decimal | None, rsi_sell: Decimal) -> bool:
    """Return True if RSI is strictly above the sell threshold (overbought)."""
    return rsi is not None and rsi > rsi_sell


def evaluate_rsi_signal(
    rsi: Decimal | None,
    rsi_buy: Decimal,
    rsi_sell: Decimal,
) -> SignalAction:
    """Evaluate RSI against buy and sell thresholds.

    Args:
        rsi: Current relative strength index value.
        rsi_buy: Threshold below which a BUY is triggered.
        rsi_sell: Threshold above which a SELL is triggered.

    Returns:
        SignalAction indicating BUY, SELL, or HOLD.
    """
    if rsi is None:
        return SignalAction.HOLD
    if is_oversold(rsi, rsi_buy):
        return SignalAction.BUY
    if is_overbought(rsi, rsi_sell):
        return SignalAction.SELL
    return SignalAction.HOLD
