"""Unit tests for pure RSI indicator validation and signal generation."""

from decimal import Decimal

from trading_bot.domain.signals import (
    SignalAction,
    evaluate_rsi_signal,
    is_overbought,
    is_oversold,
    validate_rsi,
)


def test_validate_rsi_valid_values() -> None:
    """Verify validate_rsi accepts numeric values within [0, 100]."""
    assert validate_rsi(Decimal("29.86")) == Decimal("29.86")
    assert validate_rsi("50.0") == Decimal("50.0")
    assert validate_rsi(0) == Decimal("0")
    assert validate_rsi(100) == Decimal("100")
    assert validate_rsi(Decimal("100.00")) == Decimal("100.00")


def test_validate_rsi_invalid_and_out_of_bounds() -> None:
    """Verify validate_rsi rejects out-of-bounds, non-numeric, or non-finite inputs."""
    assert validate_rsi(None) is None
    assert validate_rsi(True) is None
    assert validate_rsi(False) is None
    assert validate_rsi("-0.01") is None
    assert validate_rsi("100.01") is None
    assert validate_rsi("not-a-number") is None
    assert validate_rsi(float("nan")) is None
    assert validate_rsi(float("inf")) is None


def test_is_oversold() -> None:
    """Verify oversold check strictly triggers below buy threshold."""
    assert is_oversold(Decimal("29.99"), Decimal("30")) is True
    assert is_oversold(Decimal("30.00"), Decimal("30")) is False
    assert is_oversold(Decimal("35.00"), Decimal("30")) is False
    assert is_oversold(None, Decimal("30")) is False


def test_is_overbought() -> None:
    """Verify overbought check strictly triggers above sell threshold."""
    assert is_overbought(Decimal("70.01"), Decimal("70")) is True
    assert is_overbought(Decimal("70.00"), Decimal("70")) is False
    assert is_overbought(Decimal("65.00"), Decimal("70")) is False
    assert is_overbought(None, Decimal("70")) is False


def test_evaluate_rsi_signal() -> None:
    """Verify evaluate_rsi_signal maps RSI to correct SignalAction."""
    buy_threshold = Decimal("30")
    sell_threshold = Decimal("70")

    assert evaluate_rsi_signal(Decimal("25"), buy_threshold, sell_threshold) == SignalAction.BUY
    assert evaluate_rsi_signal(Decimal("75"), buy_threshold, sell_threshold) == SignalAction.SELL
    assert evaluate_rsi_signal(Decimal("50"), buy_threshold, sell_threshold) == SignalAction.HOLD
    assert evaluate_rsi_signal(None, buy_threshold, sell_threshold) == SignalAction.HOLD
