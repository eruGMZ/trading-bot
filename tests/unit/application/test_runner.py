"""Unit tests for TradingBotRunner lifecycle, orchestration, and graceful shutdown."""

import threading
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository
from trading_bot.adapters.telegram.dispatcher import TelegramCommandDispatcher
from trading_bot.application.runner import TradingBotRunner, build_runner
from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.process_tick import ProcessTickUseCase
from trading_bot.config.settings import BotSettings
from trading_bot.domain.models import Quote
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort
from trading_bot.ports.signal_provider import SignalProviderPort


class StubExchange(ExchangePort):
    def __init__(self, btc_balance: Decimal = Decimal("0")) -> None:
        self.btc_balance = btc_balance

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        return Quote(
            symbol=book,
            last=Decimal("1000000"),
            bid=Decimal("999900"),
            ask=Decimal("1000100"),
            spread_pct=Decimal("0.0002"),
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
        return "stub_order_id"


class StubNotifier(NotifierPort):
    def __init__(self, updates: list[dict[str, Any]] | None = None) -> None:
        self.notifications: list[str] = []
        self.sent_messages: list[tuple[int | str, str]] = []
        self._updates = updates or []

    def notify(self, message: str) -> None:
        self.notifications.append(message)

    def send_message(self, chat_id: int | str, text: str) -> None:
        self.sent_messages.append((chat_id, text))

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        return self._updates


class StubSignalProvider(SignalProviderPort):
    def get_latest_rsi(self) -> tuple[Decimal, float] | None:
        return (Decimal("50.0"), 12345.0)


def create_test_runner(
    tmp_path: Path,
    updates: list[dict[str, Any]] | None = None,
    bot_mode: str = "dry_run",
) -> tuple[TradingBotRunner, StateManager, StubExchange, StubNotifier]:
    state_file = tmp_path / "state.json"
    db_file = tmp_path / "trades.db"
    store = JsonStateStore(state_file, default_mode=bot_mode)
    state_mgr = StateManager(store, mode=bot_mode)
    exchange = StubExchange()
    notifier = StubNotifier(updates=updates)
    repo = SqliteTradeRepository(db_file)
    repo.init_db()
    signal_provider = StubSignalProvider()

    settings = BotSettings(
        bot_mode=bot_mode,
        state_file=state_file,
        trade_log_file=db_file,
        telegram_chat_id="12345",
        connection_timeout_min=5,
        loop_seconds=1,
    )

    tick_use_case = ProcessTickUseCase(
        state_mgr=state_mgr,
        exchange=exchange,
        notifier=notifier,
        trade_repo=repo,
        signal_provider=signal_provider,
        settings=settings,
    )

    telegram_dispatcher = TelegramCommandDispatcher(
        allowed_chat_id="12345",
        capital_ref_mxn=settings.capital_ref_mxn,
        daily_loss_pct=settings.daily_loss_pct,
        is_dry_run=settings.is_dry_run,
        mode_label=settings.bot_mode,
    )

    runner = TradingBotRunner(
        settings=settings,
        state_mgr=state_mgr,
        exchange=exchange,
        notifier=notifier,
        trade_repo=repo,
        signal_provider=signal_provider,
        tick_use_case=tick_use_case,
        telegram_dispatcher=telegram_dispatcher,
    )

    return runner, state_mgr, exchange, notifier


def test_runner_check_connection_alerting(tmp_path: Path) -> None:
    runner, state_mgr, _, notifier = create_test_runner(tmp_path)
    now = datetime(2026, 11, 9, 12, 10, 0)

    # 1. No last_tick_ok -> no alert
    runner.check_connection(now=now)
    assert len(notifier.notifications) == 0

    # 2. Fresh last_tick_ok (2 min ago) -> no alert
    state_mgr.set(last_tick_ok=(now - timedelta(minutes=2)).isoformat())
    runner.check_connection(now=now)
    assert len(notifier.notifications) == 0

    # 3. Stale last_tick_ok (8 min ago > 5 min threshold) -> sends alert
    state_mgr.set(last_tick_ok=(now - timedelta(minutes=8)).isoformat())
    runner.check_connection(now=now)
    assert len(notifier.notifications) == 1
    assert "No market data received" in notifier.notifications[0]

    # 4. Immediate second check (1 min later) -> suppressed by rate-limit guard
    runner.check_connection(now=now + timedelta(minutes=1))
    assert len(notifier.notifications) == 1

    # 5. Check after rate-limit window expired (6 min later) -> sends second alert
    runner.check_connection(now=now + timedelta(minutes=6))
    assert len(notifier.notifications) == 2


def test_runner_telegram_loop_routes_commands(tmp_path: Path) -> None:
    updates = [
        # Unauthorized update
        {
            "update_id": 101,
            "message": {
                "chat": {"id": 99999},
                "text": "/status",
            },
        },
        # Authorized update
        {
            "update_id": 102,
            "message": {
                "chat": {"id": 12345},
                "text": "/status",
            },
        },
    ]
    runner, state_mgr, _, notifier = create_test_runner(tmp_path, updates=updates)

    # Run one pass of telegram listener loop in thread and stop
    t = threading.Thread(target=runner._telegram_loop)
    t.start()
    # Allow loop to process the updates
    runner.shutdown_event.wait(timeout=0.1)
    runner.request_shutdown()
    t.join(timeout=2.0)

    # Update ID bumped
    assert state_mgr.snapshot().last_update_id == 102
    # Only 1 reply sent to authorized chat
    assert len(notifier.sent_messages) == 1
    assert notifier.sent_messages[0][0] == 12345
    assert "Activo" in notifier.sent_messages[0][1]


def test_runner_run_halts_on_failed_reconciliation(tmp_path: Path) -> None:
    # Set mode mismatch in operational mode with dry_run position
    runner, state_mgr, _, notifier = create_test_runner(tmp_path, bot_mode="operational")
    state_mgr.open_position(Decimal("1000000"), Decimal("1000"))
    # Mode was dry_run during creation, but settings say operational

    # runner.run() must halt without starting background threads
    result = runner.run()
    assert result is False
    assert state_mgr.snapshot().running is False
    assert any("RECONCILIATION HALT" in m for m in notifier.notifications)


def test_runner_run_and_graceful_shutdown(tmp_path: Path) -> None:
    runner, state_mgr, _, notifier = create_test_runner(tmp_path)

    # Run in background thread so we can request shutdown
    run_thread = threading.Thread(target=runner.run)
    run_thread.start()

    # Wait briefly for startup
    runner.shutdown_event.wait(timeout=0.2)
    assert any("Bot started" in m for m in notifier.notifications)

    # Request cooperative shutdown
    runner.request_shutdown()
    run_thread.join(timeout=3.0)

    assert not run_thread.is_alive()
    assert any("Bot stopped gracefully" in m for m in notifier.notifications)


def test_build_runner_composition_root(tmp_path: Path) -> None:
    settings = BotSettings(
        bot_mode="dry_run",
        state_file=tmp_path / "state.json",
        trade_log_file=tmp_path / "trades.db",
        cache_file=tmp_path / "rsi_cache.json",
        log_file=tmp_path / "bot.log",
    )
    runner = build_runner(settings)
    assert isinstance(runner, TradingBotRunner)
    assert runner.shutdown_event.is_set() is False
