"""Unit tests for ProcessTickUseCase market cycle orchestration."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository
from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.process_tick import ProcessTickUseCase
from trading_bot.config.settings import BotSettings
from trading_bot.domain.models import Quote
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort
from trading_bot.ports.signal_provider import SignalProviderPort


class MockExchange(ExchangePort):
    def __init__(
        self,
        last_price: Decimal = Decimal("1000000"),
        spread_pct: Decimal = Decimal("0.001"),
        btc_balance: Decimal = Decimal("0"),
    ) -> None:
        self.last_price = last_price
        self.spread_pct = spread_pct
        self.btc_balance = btc_balance
        self.orders: list[dict[str, Any]] = []

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        half_spread = self.last_price * (self.spread_pct / Decimal("2"))
        return Quote(
            symbol=book,
            last=self.last_price,
            bid=self.last_price - half_spread,
            ask=self.last_price + half_spread,
            spread_pct=self.spread_pct,
            timestamp=datetime.now(),
        )

    def get_available_balance(self, asset: str) -> Decimal:
        return self.btc_balance

    def place_order(
        self,
        book: str,
        side: str,
        amount_btc: Decimal | None = None,
        amount_mxn: Decimal | None = None,
    ) -> str:
        self.orders.append({
            "book": book,
            "side": side,
            "amount_btc": amount_btc,
            "amount_mxn": amount_mxn,
        })
        return f"mock_order_{len(self.orders)}"


class MockNotifier(NotifierPort):
    def __init__(self) -> None:
        self.notifications: list[str] = []

    def notify(self, message: str) -> None:
        self.notifications.append(message)

    def send_message(self, chat_id: int | str, text: str) -> None:
        self.notifications.append(f"[{chat_id}] {text}")

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        return []


class MockSignalProvider(SignalProviderPort):
    def __init__(self, rsi: Decimal | None = None, timestamp: float = 1000.0) -> None:
        self.rsi = rsi
        self.timestamp = timestamp

    def get_latest_rsi(self) -> tuple[Decimal, float] | None:
        if self.rsi is None:
            return None
        return (self.rsi, self.timestamp)


TickHarness = tuple[
    StateManager,
    MockExchange,
    MockNotifier,
    SqliteTradeRepository,
    MockSignalProvider,
    BotSettings,
    ProcessTickUseCase,
]


@pytest.fixture
def tick_harness(tmp_path: Path) -> TickHarness:
    state_file = tmp_path / "state.json"
    db_file = tmp_path / "trades.db"
    store = JsonStateStore(state_file, default_mode="dry_run")
    state_mgr = StateManager(store, mode="dry_run", initial_capital=Decimal("5000.00"))
    exchange = MockExchange(last_price=Decimal("1000000.00"), spread_pct=Decimal("0.001"))
    notifier = MockNotifier()
    repo = SqliteTradeRepository(db_file)
    repo.init_db()
    signal_provider = MockSignalProvider(rsi=Decimal("50.0"))
    settings = BotSettings(
        bot_mode="dry_run",
        capital_ref_mxn=Decimal("5000.00"),
        rsi_buy=Decimal("30.0"),
        rsi_sell=Decimal("70.0"),
        stop_loss_pct=Decimal("0.02"),      # 2% stop-loss
        drawdown_kill_pct=Decimal("0.05"),  # 5% drawdown kill switch
        max_spread_pct=Decimal("0.005"),    # 0.5% max spread
        daily_report_hour=21,
    )

    use_case = ProcessTickUseCase(
        state_mgr=state_mgr,
        exchange=exchange,
        notifier=notifier,
        trade_repo=repo,
        signal_provider=signal_provider,
        settings=settings,
    )

    return (
        state_mgr,
        exchange,
        notifier,
        repo,
        signal_provider,
        settings,
        use_case,
    )


def test_process_tick_idle_when_halted(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    state_mgr.halt("Manual maintenance")

    use_case.execute()

    assert len(exchange.orders) == 0
    assert state_mgr.snapshot().last_tick_ok is None


def test_process_tick_records_last_tick_ok(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    fixed_time = datetime(2026, 11, 9, 14, 0, 0)

    use_case.execute(now=fixed_time)

    assert state_mgr.snapshot().last_tick_ok == fixed_time
    assert len(exchange.orders) == 0


def test_process_tick_daily_report_trigger(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    evening_time = datetime(2026, 11, 9, 21, 30, 0)

    use_case.execute(now=evening_time)

    assert state_mgr.snapshot().last_daily_report_date == "2026-11-09"
    assert any("Reporte del día" in m for m in notifier.notifications)


def test_process_tick_buy_signal_execution(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    signal_provider.rsi = Decimal("25.0")  # Below rsi_buy (30.0) -> Buy
    now = datetime(2026, 11, 9, 12, 0, 0)

    use_case.execute(now=now)

    snap = state_mgr.snapshot()
    assert snap.position is not None
    assert snap.position.entry_price == Decimal("1000000.00")
    assert len(exchange.orders) == 1
    assert exchange.orders[0]["side"] == "buy"
    assert exchange.orders[0]["amount_mxn"] > Decimal("0")
    assert any("COMPRA BTC" in m for m in notifier.notifications)

    # Check trade logged to SQLite repository
    metrics = repo.get_metrics()
    assert metrics.total == 0  # Not closed yet


def test_process_tick_buy_blocked_by_wide_spread(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    signal_provider.rsi = Decimal("25.0")
    exchange.spread_pct = Decimal("0.01")  # 1.0% > max_spread_pct (0.5%)

    use_case.execute(now=datetime(2026, 11, 9, 12, 0, 0))

    assert state_mgr.snapshot().position is None
    assert len(exchange.orders) == 0


def test_process_tick_trailing_stop_exit(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    # Open initial position at 1,000,000
    state_mgr.open_position(Decimal("1000000.00"), Decimal("1000.00"))

    # Tick 1: Price climbs to 1,100,000 (trailing watermark updates)
    exchange.last_price = Decimal("1100000.00")
    use_case.execute(now=datetime(2026, 11, 9, 12, 0, 0))
    assert state_mgr.snapshot().position.high_since_entry == Decimal("1100000.00")  # type: ignore[union-attr]

    # Tick 2: Price drops to 1,070,000 (2.7% drop > 2.0% stop_loss_pct) -> triggers trailing stop!
    exchange.last_price = Decimal("1070000.00")
    use_case.execute(now=datetime(2026, 11, 9, 12, 1, 0))

    assert state_mgr.snapshot().position is None
    assert len(exchange.orders) == 1
    assert exchange.orders[0]["side"] == "sell"
    assert any("TRAILING STOP" in m for m in notifier.notifications)

    metrics = repo.get_metrics()
    assert metrics.total == 1
    assert metrics.win_rate == Decimal("100.00")


def test_process_tick_kill_switch_on_drawdown(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    # Peak equity set to 5000 MXN. Current PnL drops to -300 MXN -> 6% drawdown > 5% limit
    state_mgr.update_peak_equity(Decimal("5000.00"))
    state_mgr.set(pnl_total=Decimal("-300.00"))
    state_mgr.open_position(Decimal("1000000.00"), Decimal("1000.00"))

    use_case.execute(now=datetime(2026, 11, 9, 12, 0, 0))

    snap = state_mgr.snapshot()
    assert snap.position is None
    assert snap.running is False
    assert "kill switch" in str(snap.halt_reason)
    assert any("KILL SWITCH" in m for m in notifier.notifications)
    assert len(exchange.orders) == 1
    assert exchange.orders[0]["side"] == "sell"


def test_process_tick_rsi_sell_exit(tick_harness: TickHarness) -> None:
    state_mgr, exchange, notifier, repo, signal_provider, settings, use_case = tick_harness
    state_mgr.open_position(Decimal("1000000.00"), Decimal("1000.00"))
    signal_provider.rsi = Decimal("75.0")  # Overbought (> 70)
    exchange.last_price = Decimal("1050000.00")

    use_case.execute(now=datetime(2026, 11, 9, 12, 0, 0))

    snap = state_mgr.snapshot()
    assert snap.position is None
    assert snap.running is True
    assert any("VENTA BTC" in m for m in notifier.notifications)
    assert len(exchange.orders) == 1
    assert exchange.orders[0]["side"] == "sell"

    metrics = repo.get_metrics()
    assert metrics.total == 1
