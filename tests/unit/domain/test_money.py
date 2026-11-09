"""Unit tests for exact decimal money helpers and quantization."""

from decimal import Decimal

import pytest

from trading_bot.core.money import (
    format_btc,
    format_mxn,
    quantize_btc,
    quantize_fiat,
    quantize_mxn,
    quantize_percent,
    to_decimal,
)


def test_to_decimal_conversions() -> None:
    """Verify to_decimal converts str, int, float, and Decimal correctly."""
    assert to_decimal(Decimal("100.5")) == Decimal("100.5")
    assert to_decimal("250.75") == Decimal("250.75")
    assert to_decimal(500) == Decimal("500")
    assert to_decimal(0.0078) == Decimal("0.0078")


def test_to_decimal_invalid_inputs() -> None:
    """Verify invalid strings or types raise appropriate errors."""
    with pytest.raises((ValueError, ArithmeticError)):
        to_decimal("not-a-number")

    with pytest.raises(TypeError):
        to_decimal([100])  # type: ignore[arg-type]


def test_quantize_btc_truncates_never_rounds_up() -> None:
    """Verify BTC quantization strictly rounds down to 8 decimal places."""
    assert quantize_btc("0.123456789") == Decimal("0.12345678")
    assert quantize_btc(Decimal("0.1234567899")) == Decimal("0.12345678")
    assert quantize_btc(0) == Decimal("0.00000000")
    assert quantize_btc("0.0000000049") == Decimal("0.00000000")
    assert quantize_btc("0.0000000099") == Decimal("0.00000000")


def test_format_btc() -> None:
    """Verify string formatting of BTC amounts."""
    assert format_btc("0.123456789") == "0.12345678"
    assert format_btc(0) == "0.00000000"
    assert format_btc("1.5") == "1.50000000"


def test_quantize_mxn_and_fiat() -> None:
    """Verify fiat quantization applies ROUND_HALF_EVEN to 2 decimals."""
    # Round half to even
    assert quantize_fiat("10.555") == Decimal("10.56")
    assert quantize_fiat("10.545") == Decimal("10.54")
    assert quantize_mxn("100.254") == Decimal("100.25")
    assert quantize_mxn("100.256") == Decimal("100.26")


def test_format_mxn() -> None:
    """Verify string formatting of MXN currency."""
    assert format_mxn("500") == "500.00"
    assert format_mxn("1234.567") == "1234.57"


def test_quantize_percent() -> None:
    """Verify percentage quantization applies ROUND_HALF_EVEN to 2 decimal places."""
    assert quantize_percent("2.345") == Decimal("2.34")  # 4 is even -> rounds to 2.34
    assert quantize_percent("2.355") == Decimal("2.36")  # 5 is odd -> rounds to 2.36
    assert quantize_percent("2.346") == Decimal("2.35")
