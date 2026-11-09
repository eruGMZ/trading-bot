"""Unit tests for exception hierarchy."""

import pytest

from trading_bot.core.exceptions import (
    DomainError,
    ExchangeError,
    ReconciliationError,
    RiskError,
    StateError,
    TradingBotError,
)


def test_exception_inheritance() -> None:
    """Verify exception hierarchy inheritance and instantiation."""
    base_err = TradingBotError("base failure")
    assert isinstance(base_err, Exception)

    domain_err = DomainError("domain error")
    assert isinstance(domain_err, TradingBotError)

    risk_err = RiskError("risk limit exceeded")
    assert isinstance(risk_err, DomainError)
    assert isinstance(risk_err, TradingBotError)

    state_err = StateError("invalid state")
    assert isinstance(state_err, DomainError)

    exchange_err = ExchangeError("api timeout")
    assert isinstance(exchange_err, TradingBotError)

    recon_err = ReconciliationError("balance discrepancy")
    assert isinstance(recon_err, TradingBotError)


def test_exception_raising() -> None:
    """Verify exceptions can be raised and caught as TradingBotError."""
    with pytest.raises(TradingBotError, match="risk limit exceeded"):
        raise RiskError("risk limit exceeded")
