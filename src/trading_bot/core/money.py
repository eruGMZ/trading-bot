"""Financial precision and decimal quantization utilities.

Enforces Decimal-only arithmetic across crypto amounts, fiat currencies,
fees, and percentages to avoid IEEE-754 binary floating-point errors.
"""

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from typing import Final

BTC_QUANTUM: Final[Decimal] = Decimal("0.00000001")
FIAT_QUANTUM: Final[Decimal] = Decimal("0.01")
PERCENT_QUANTUM: Final[Decimal] = Decimal("0.01")


def to_decimal(val: str | int | float | Decimal) -> Decimal:
    """Safely convert numeric types, integers, and strings to exact Decimal.

    For floats, str(val) is used to avoid IEEE-754 binary representation artifacts.

    Args:
        val: Input number as str, int, float, or Decimal.

    Returns:
        Exact Decimal representation.

    Raises:
        ValueError: If input cannot be converted to Decimal.
    """
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (str, int)):
        return Decimal(str(val).strip())
    if isinstance(val, float):
        return Decimal(str(val))
    raise TypeError(f"Unsupported type for Decimal conversion: {type(val).__name__}")


def quantize_btc(val: Decimal | str | int | float) -> Decimal:
    """Quantize BTC amount to 8 decimal places using ROUND_DOWN.

    Never rounds up to prevent placing orders exceeding available balance.
    """
    dec = to_decimal(val)
    return dec.quantize(BTC_QUANTUM, rounding=ROUND_DOWN)


def format_btc(val: Decimal | str | int | float) -> str:
    """Format BTC amount as an exact 8-decimal string."""
    return f"{quantize_btc(val):.8f}"


def quantize_fiat(val: Decimal | str | int | float) -> Decimal:
    """Quantize fiat currency (e.g. MXN) to 2 decimal places using ROUND_HALF_EVEN."""
    dec = to_decimal(val)
    return dec.quantize(FIAT_QUANTUM, rounding=ROUND_HALF_EVEN)


def quantize_mxn(val: Decimal | str | int | float) -> Decimal:
    """Alias for quantize_fiat for MXN currency."""
    return quantize_fiat(val)


def format_mxn(val: Decimal | str | int | float) -> str:
    """Format MXN currency as a 2-decimal string."""
    return f"{quantize_mxn(val):.2f}"


def quantize_percent(val: Decimal | str | int | float) -> Decimal:
    """Quantize percentage to 2 decimal places using ROUND_HALF_EVEN."""
    dec = to_decimal(val)
    return dec.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_EVEN)
