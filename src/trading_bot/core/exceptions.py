"""Domain, exchange, and application exception hierarchy."""


class TradingBotError(Exception):
    """Base exception for all trading bot errors."""


class DomainError(TradingBotError):
    """Base exception for business logic and domain rule violations."""


class RiskError(DomainError):
    """Raised when an action violates risk limits or portfolio constraints."""


class StateError(DomainError):
    """Raised when state transitions or invariants are violated."""


class ExchangeError(TradingBotError):
    """Raised when exchange communication, authentication, or order execution fails."""


class ReconciliationError(TradingBotError):
    """Raised when exchange balances or positions do not match internal state."""
