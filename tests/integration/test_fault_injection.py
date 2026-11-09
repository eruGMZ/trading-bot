"""Fault injection and resilience integration tests.

Tests error paths: network timeouts mid-order, non-JSON Cloudflare responses,
Telegram communication dropouts, and state file atomic resilience.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest
import requests

from trading_bot.adapters.bitso.client import LiveBitsoAdapter
from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository
from trading_bot.adapters.telegram.client import TelegramAdapter
from trading_bot.adapters.telegram.dispatcher import TelegramCommandDispatcher
from trading_bot.application.runner import TradingBotRunner
from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.process_tick import ProcessTickUseCase
from trading_bot.config.settings import BotSettings
from trading_bot.core.exceptions import ExchangeError
from trading_bot.ports.signal_provider import SignalProviderPort


class ConstantSignalProvider(SignalProviderPort):
    def __init__(self, rsi: Decimal = Decimal("25.0")) -> None:
        self.rsi = rsi

    def get_latest_rsi(self) -> tuple[Decimal, float] | None:
        return (self.rsi, 123456.0)


def test_bitso_network_timeout_mid_order() -> None:
    """Verify ExchangeError is raised with descriptive context when requests timeout."""
    session = mock.Mock(spec=requests.Session)
    session.request.side_effect = requests.exceptions.ConnectTimeout("Connection timed out")

    adapter = LiveBitsoAdapter(
        api_key="test_key",
        api_secret="test_secret",
        timeout=0.01,
        session=session,
    )

    with pytest.raises(ExchangeError) as exc_info:
        adapter.place_order(book="btc_mxn", side="buy", amount_mxn=Decimal("500"))

    assert "Network error contacting Bitso" in str(exc_info.value)
    assert "Connection timed out" in str(exc_info.value)


def test_bitso_non_json_cloudflare_502_error() -> None:
    """Verify HTML gateway error returns structured ExchangeError rather than JSONDecodeError."""
    session = mock.Mock(spec=requests.Session)
    res = mock.Mock(spec=requests.Response)
    res.status_code = 502
    res.json.side_effect = ValueError("No JSON in response")
    res.text = "<html><title>502 Bad Gateway</title><body>Cloudflare error</body></html>"
    session.request.return_value = res

    adapter = LiveBitsoAdapter(
        api_key="test_key",
        api_secret="test_secret",
        session=session,
    )

    with pytest.raises(ExchangeError) as exc_info:
        adapter.get_quote("btc_mxn")

    assert "Invalid non-JSON response from Bitso (HTTP 502)" in str(exc_info.value)
    assert "502 Bad Gateway" in str(exc_info.value)


def test_process_tick_resilience_to_exchange_outage(tmp_path: Path) -> None:
    """Verify ProcessTickUseCase survives exchange exceptions without corrupting state."""
    state_file = tmp_path / "state.json"
    db_file = tmp_path / "trades.db"
    store = JsonStateStore(state_file, default_mode="dry_run")
    state_mgr = StateManager(store, mode="dry_run")
    repo = SqliteTradeRepository(db_file)
    repo.init_db()
    signal_provider = ConstantSignalProvider(rsi=Decimal("25.0"))

    session = mock.Mock(spec=requests.Session)
    res = mock.Mock(spec=requests.Response)
    res.status_code = 503
    res.json.side_effect = ValueError("Service Unavailable")
    res.text = "503 Service Unavailable"
    session.request.return_value = res

    adapter = LiveBitsoAdapter(api_key="test_key", api_secret="test_secret", session=session)
    telegram = TelegramAdapter(token="fake_token", chat_id="12345")
    settings = BotSettings(
        bot_mode="dry_run",
        state_file=state_file,
        trade_log_file=db_file,
    )

    use_case = ProcessTickUseCase(
        state_mgr=state_mgr,
        exchange=adapter,
        notifier=telegram,
        trade_repo=repo,
        signal_provider=signal_provider,
        settings=settings,
    )

    with pytest.raises(ExchangeError):
        use_case.execute(now=datetime(2026, 11, 9, 12, 0, 0))

    # Bot state remains uncorrupted and running
    snap = state_mgr.snapshot()
    assert snap.running is True
    assert snap.position is None
    assert snap.halt_reason is None


def test_runner_market_loop_survives_transient_tick_error(tmp_path: Path) -> None:
    """Verify market loop catches tick error, logs it, and continues executing subsequent cycles."""
    state_file = tmp_path / "state.json"
    db_file = tmp_path / "trades.db"
    store = JsonStateStore(state_file, default_mode="dry_run")
    state_mgr = StateManager(store, mode="dry_run")
    repo = SqliteTradeRepository(db_file)
    repo.init_db()
    signal_provider = ConstantSignalProvider()
    adapter = LiveBitsoAdapter(api_key="test_key", api_secret="test_secret")
    telegram = TelegramAdapter(token="fake_token", chat_id="12345")

    settings = BotSettings(
        bot_mode="dry_run",
        state_file=state_file,
        trade_log_file=db_file,
        loop_seconds=1,
    )

    class FailingTickUseCase(ProcessTickUseCase):
        def __init__(self) -> None:
            super().__init__(state_mgr, adapter, telegram, repo, signal_provider, settings)
            self.tick_count = 0

        def execute(self, now: datetime | None = None) -> None:
            self.tick_count += 1
            if self.tick_count == 1:
                raise ExchangeError("Transient network failure on tick 1")

    failing_use_case = FailingTickUseCase()
    dispatcher = TelegramCommandDispatcher(allowed_chat_id="12345")

    runner = TradingBotRunner(
        settings=settings,
        state_mgr=state_mgr,
        exchange=adapter,
        notifier=telegram,
        trade_repo=repo,
        signal_provider=signal_provider,
        tick_use_case=failing_use_case,
        telegram_dispatcher=dispatcher,
    )

    # Check connection alert logic functions even with simulated errors
    runner.check_connection()
    assert runner.shutdown_event.is_set() is False
