"""Unit tests for balance reconciliation use cases."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.reconcile import reconcile_daily, reconcile_on_startup
from trading_bot.config.settings import BotSettings
from trading_bot.core.exceptions import ExchangeError
from trading_bot.domain.models import Quote
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort


class DummyExchange(ExchangePort):
    def __init__(
        self,
        btc_balance: Decimal = Decimal("0"),
        last_price: Decimal = Decimal("1000000"),
        should_fail: bool = False,
    ) -> None:
        self.btc_balance = btc_balance
        self.last_price = last_price
        self.should_fail = should_fail

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        if self.should_fail:
            raise ExchangeError("Simulated exchange outage")
        return Quote(
            symbol=book,
            last=self.last_price,
            bid=self.last_price - Decimal("100"),
            ask=self.last_price + Decimal("100"),
            spread_pct=Decimal("0.0002"),
            timestamp=datetime.now(),
        )

    def get_available_balance(self, asset: str) -> Decimal:
        if self.should_fail:
            raise ExchangeError("Simulated balance failure")
        return self.btc_balance

    def place_order(
        self,
        book: str,
        side: str,
        amount_btc: Decimal | None = None,
        amount_mxn: Decimal | None = None,
    ) -> str:
        return "order_123"


class DummyNotifier(NotifierPort):
    def __init__(self) -> None:
        self.notifications: list[str] = []

    def notify(self, message: str) -> None:
        self.notifications.append(message)

    def send_message(self, chat_id: int | str, text: str) -> None:
        self.notifications.append(f"[{chat_id}] {text}")

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        return []


def test_reconcile_on_startup_dry_run_skips(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="dry_run")
    mgr = StateManager(store, mode="dry_run")
    settings = BotSettings(bot_mode="dry_run")
    exchange = DummyExchange(btc_balance=Decimal("1.5"))  # Would fail if live
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is True
    assert mgr.snapshot().running is True
    assert mgr.snapshot().halt_reason is None


def test_reconcile_on_startup_mode_mismatch_halts(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="dry_run")
    mgr = StateManager(store, mode="dry_run")
    # Position opened in dry_run
    mgr.open_position(price=Decimal("1000000"), amount_mxn=Decimal("1000"))

    # Starting bot in operational mode
    settings = BotSettings(bot_mode="operational")
    exchange = DummyExchange()
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is False
    assert mgr.snapshot().running is False
    assert "position opened in mode 'dry_run'" in str(mgr.snapshot().halt_reason)
    assert len(notifier.notifications) == 1
    assert "RECONCILIATION HALT" in notifier.notifications[0]


def test_reconcile_on_startup_exchange_error_halts(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="operational")
    mgr = StateManager(store, mode="operational")
    settings = BotSettings(bot_mode="operational")
    exchange = DummyExchange(should_fail=True)
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is False
    assert mgr.snapshot().running is False
    assert "failed to query exchange" in str(mgr.snapshot().halt_reason)


def test_reconcile_on_startup_unexpected_dust_halts(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="operational")
    mgr = StateManager(store, mode="operational")
    settings = BotSettings(bot_mode="operational", reconcile_dust_mxn=Decimal("50"))
    # No position in state, but 0.001 BTC (~1000 MXN) on exchange
    exchange = DummyExchange(btc_balance=Decimal("0.00100000"), last_price=Decimal("1000000"))
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is False
    assert mgr.snapshot().running is False
    assert "without an active position recorded" in str(mgr.snapshot().halt_reason)


def test_reconcile_on_startup_minor_dust_allowed(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="operational")
    mgr = StateManager(store, mode="operational")
    settings = BotSettings(bot_mode="operational", reconcile_dust_mxn=Decimal("50"))
    # 0.00001 BTC * 1,000,000 = 10 MXN (< 50 MXN dust limit)
    exchange = DummyExchange(btc_balance=Decimal("0.00001000"), last_price=Decimal("1000000"))
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is True
    assert mgr.snapshot().running is True


def test_reconcile_on_startup_missing_position_btc_halts(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="operational")
    mgr = StateManager(store, mode="operational")
    # State expects 0.00100000 BTC
    mgr.open_position(price=Decimal("1000000"), amount_mxn=Decimal("1000"))
    settings = BotSettings(bot_mode="operational")
    # Exchange only has 0.0005 BTC (< 98% of expected)
    exchange = DummyExchange(btc_balance=Decimal("0.00050000"), last_price=Decimal("1000000"))
    notifier = DummyNotifier()

    result = reconcile_on_startup(mgr, exchange, settings, notifier)
    assert result is False
    assert mgr.snapshot().running is False
    assert "recorded position of 0.00100000 BTC" in str(mgr.snapshot().halt_reason)


def test_reconcile_daily_lifecycle(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path / "state.json", default_mode="operational")
    mgr = StateManager(store, mode="operational")
    settings = BotSettings(bot_mode="operational", reconcile_dust_mxn=Decimal("50"))
    notifier = DummyNotifier()

    # 1. In dry-run, returns True immediately
    dry_settings = BotSettings(bot_mode="dry_run")
    assert reconcile_daily(mgr, DummyExchange(), dry_settings, notifier) is True

    # 2. Exchange failure returns False without halting
    failing_exchange = DummyExchange(should_fail=True)
    assert reconcile_daily(mgr, failing_exchange, settings, notifier) is False
    assert mgr.snapshot().running is True

    # 3. Small drift within dust limit (< 50 MXN) -> OK
    small_drift_exchange = DummyExchange(
        btc_balance=Decimal("0.00002000"),
        last_price=Decimal("1000000"),
    )
    assert reconcile_daily(mgr, small_drift_exchange, settings, notifier) is True

    # 4. Moderate drift (>= 50 MXN and < 500 MXN) -> alerts but does not halt
    mod_drift_exchange = DummyExchange(
        btc_balance=Decimal("0.00010000"),
        last_price=Decimal("1000000"),
    )
    # 0.0001 BTC * 1,000,000 = 100 MXN (exceeds 50 MXN, but below 10x = 500 MXN)
    assert reconcile_daily(mgr, mod_drift_exchange, settings, notifier) is True
    assert mgr.snapshot().running is True
    assert any("Daily reconciliation discrepancy" in m for m in notifier.notifications)

    # 5. Critical drift (>= 500 MXN) -> alerts AND halts
    crit_drift_exchange = DummyExchange(
        btc_balance=Decimal("0.00100000"),
        last_price=Decimal("1000000"),
    )
    # 0.001 BTC * 1,000,000 = 1000 MXN (>= 500 MXN)
    assert reconcile_daily(mgr, crit_drift_exchange, settings, notifier) is False
    assert mgr.snapshot().running is False
    assert "critical balance discrepancy" in str(mgr.snapshot().halt_reason)
