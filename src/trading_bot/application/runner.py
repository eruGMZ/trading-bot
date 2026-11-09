"""Application composition root and cooperative lifecycle runner."""

import contextlib
import logging
import signal
import threading
from datetime import datetime
from types import FrameType

from trading_bot.adapters.bitso.client import LiveBitsoAdapter
from trading_bot.adapters.bitso.paper import PaperTradingAdapter
from trading_bot.adapters.indicators.cached_rsi import CachedRsiSignalProvider
from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository
from trading_bot.adapters.telegram.client import TelegramAdapter
from trading_bot.adapters.telegram.dispatcher import TelegramCommandDispatcher
from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.process_tick import ProcessTickUseCase
from trading_bot.application.use_cases.reconcile import reconcile_on_startup
from trading_bot.config.settings import BotSettings
from trading_bot.core.logging import configure_logging
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort
from trading_bot.ports.signal_provider import SignalProviderPort
from trading_bot.ports.trade_repository import TradeRepositoryPort

log = logging.getLogger(__name__)


class TradingBotRunner:
    """Cooperative lifecycle manager and multi-threaded daemon orchestrator."""

    def __init__(
        self,
        settings: BotSettings,
        state_mgr: StateManager,
        exchange: ExchangePort,
        notifier: NotifierPort,
        trade_repo: TradeRepositoryPort,
        signal_provider: SignalProviderPort,
        tick_use_case: ProcessTickUseCase,
        telegram_dispatcher: TelegramCommandDispatcher,
    ) -> None:
        self._settings = settings
        self._state_mgr = state_mgr
        self._exchange = exchange
        self._notifier = notifier
        self._trade_repo = trade_repo
        self._signal_provider = signal_provider
        self._tick_use_case = tick_use_case
        self._telegram_dispatcher = telegram_dispatcher

        self._shutdown_event = threading.Event()
        self._last_connection_alert: datetime | None = None
        self._threads: list[threading.Thread] = []

    @property
    def shutdown_event(self) -> threading.Event:
        """Cooperative shutdown event handle."""
        return self._shutdown_event

    def request_shutdown(self) -> None:
        """Signal all cooperative loops to terminate."""
        if not self._shutdown_event.is_set():
            log.info("Shutdown requested. Signaling background threads...")
            self._shutdown_event.set()

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        """OS signal handler for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        log.info("Received OS signal %s. Initiating graceful stop...", sig_name)
        self.request_shutdown()

    def check_connection(self, now: datetime | None = None) -> None:
        """Send warning notification if market data updates stop arriving."""
        current_dt = now or datetime.now()
        last_ok = self._state_mgr.snapshot().last_tick_ok
        if last_ok is None:
            return

        if isinstance(last_ok, datetime):
            last_ok_dt = last_ok
        else:
            try:
                last_ok_dt = datetime.fromisoformat(last_ok)
            except ValueError:
                return

        age_min = (current_dt - last_ok_dt).total_seconds() / 60.0
        if age_min < self._settings.connection_timeout_min:
            self._last_connection_alert = None
            return

        if self._last_connection_alert is not None:
            elapsed = (current_dt - self._last_connection_alert).total_seconds() / 60.0
            if elapsed < self._settings.connection_timeout_min:
                return

        self._last_connection_alert = current_dt
        pos = self._state_mgr.snapshot().position
        pos_tag = " — ⚠️ ACTIVE POSITION OPEN" if pos else ""
        msg = f"⚠️ No market data received for {age_min:.0f} min{pos_tag}. Check connectivity."
        log.warning(msg)
        try:
            self._notifier.notify(f"{self._settings.mode_tag}{msg}")
        except Exception as err:
            log.error("Failed to send connection alert to notifier: %s", err)

    def _market_loop(self) -> None:
        """Execute tick use-case periodically until shutdown event is set."""
        log.info(
            "Market loop started (interval: %ds, mode: %s)",
            self._settings.loop_seconds,
            self._settings.bot_mode,
        )
        while not self._shutdown_event.is_set():
            try:
                self._tick_use_case.execute()
            except Exception as err:
                log.error("Unhandled error in market loop tick: %s", err, exc_info=True)

            self.check_connection()
            self._shutdown_event.wait(timeout=float(self._settings.loop_seconds))
        log.info("Market loop terminated")

    def _telegram_loop(self) -> None:
        """Poll and route Telegram commands until shutdown event is set."""
        log.info("Telegram listener loop started")
        while not self._shutdown_event.is_set():
            try:
                last_id = self._state_mgr.snapshot().last_update_id
                updates = self._notifier.get_updates(offset=last_id + 1)
                for upd in updates:
                    upd_id = upd.get("update_id")
                    if isinstance(upd_id, int):
                        self._state_mgr.bump_update_id(upd_id)

                    msg = upd.get("message")
                    if not isinstance(msg, dict):
                        continue

                    text = msg.get("text")
                    chat = msg.get("chat")
                    chat_id = chat.get("id") if isinstance(chat, dict) else None
                    if not text or chat_id is None:
                        continue

                    if not self._telegram_dispatcher.is_authorized(chat_id):
                        log.warning("Ignoring command from unauthorized chat: %s", chat_id)
                        continue

                    log.info("Telegram command received: %s", text)
                    reply = self._telegram_dispatcher.dispatch(
                        text=text,
                        state_snapshot=self._state_mgr.snapshot(),
                        state_controller=self._state_mgr,
                        exchange=self._exchange,
                        trade_repo=self._trade_repo,
                    )
                    self._notifier.send_message(chat_id, reply)
            except Exception as err:
                log.error("Unhandled error in Telegram listener loop: %s", err)

            self._shutdown_event.wait(timeout=3.0)
        log.info("Telegram listener loop terminated")

    def run(self) -> bool:
        """Start lifecycle: validate reconciliation, start workers, and wait for shutdown.

        Returns:
            True if run completed normally, False if halted on startup reconciliation.
        """
        mode_label = (
            "🧪 DRY-RUN (simulation)"
            if self._settings.is_dry_run
            else "💰 OPERATIONAL (live capital)"
        )
        log.info("Starting trading bot daemon — mode: %s", mode_label)

        # 1. Startup reconciliation
        reconciled = reconcile_on_startup(
            state_mgr=self._state_mgr,
            exchange=self._exchange,
            settings=self._settings,
            notifier=self._notifier,
        )
        if not reconciled:
            log.critical("Startup reconciliation failed. Bot halted.")
            return False

        # 2. Register cooperative OS signal handlers
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError) as err:
            log.warning("Could not attach OS signal handlers (non-main thread?): %s", err)

        # 3. Spawn managed worker threads
        t_market = threading.Thread(
            target=self._market_loop,
            name="MarketLoopThread",
            daemon=False,
        )
        self._threads.append(t_market)
        t_market.start()

        # Only spawn Telegram listener if bot token is configured
        has_telegram = bool(self._settings.telegram_bot_token.get_secret_value())
        if has_telegram:
            t_telegram = threading.Thread(
                target=self._telegram_loop,
                name="TelegramListenerThread",
                daemon=False,
            )
            self._threads.append(t_telegram)
            t_telegram.start()
        else:
            log.info("Telegram bot token not configured; skipping listener thread")

        # 4. Notify startup
        try:
            self._notifier.notify(f"🤖 Bot started — mode: {mode_label}")
        except Exception as err:
            log.warning("Could not send startup notification: %s", err)

        # 5. Block main thread until shutdown is triggered
        while not self._shutdown_event.is_set():
            self._shutdown_event.wait(timeout=1.0)

        # 6. Join worker threads with timeout
        log.info("Waiting for worker threads to stop...")
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=10.0)
                if thread.is_alive():
                    log.warning("Thread %s did not terminate within timeout", thread.name)

        with contextlib.suppress(Exception):
            self._notifier.notify(f"{self._settings.mode_tag}🛑 Bot stopped gracefully")

        log.info("Trading bot shut down cleanly")
        return True


def build_runner(settings: BotSettings | None = None) -> TradingBotRunner:
    """Composition root: construct all dependencies and wire the lifecycle runner."""
    cfg = settings or BotSettings()
    log_path = cfg.log_file or (cfg.base_dir / "bot.log")
    state_path = cfg.state_file or (cfg.base_dir / "state.json")
    trade_path = cfg.trade_log_file or (cfg.base_dir / "trades.db")
    cache_path = cfg.cache_file or (cfg.base_dir / "rsi_cache.json")

    configure_logging(
        log_file=log_path,
        secrets=[cfg.bitso_api_key, cfg.bitso_api_secret, cfg.telegram_bot_token],
    )

    state_store = JsonStateStore(state_path)
    state_mgr = StateManager(
        store=state_store,
        mode=cfg.bot_mode,
        initial_capital=cfg.capital_ref_mxn,
    )

    trade_repo = SqliteTradeRepository(trade_path)
    trade_repo.init_db()

    live_bitso: ExchangePort | None = None
    has_api_keys = bool(
        cfg.bitso_api_key.get_secret_value() and cfg.bitso_api_secret.get_secret_value()
    )
    if has_api_keys:
        live_bitso = LiveBitsoAdapter(
            api_key=cfg.bitso_api_key,
            api_secret=cfg.bitso_api_secret,
        )

    exchange: ExchangePort
    if cfg.is_dry_run:
        exchange = PaperTradingAdapter(quote_provider=live_bitso)
    else:
        if live_bitso is None:
            raise ValueError("Operational mode requires BITSO_API_KEY and BITSO_API_SECRET")
        exchange = live_bitso

    notifier = TelegramAdapter(
        token=cfg.telegram_bot_token,
        chat_id=cfg.telegram_chat_id,
    )
    signal_provider = CachedRsiSignalProvider(
        cache_file=cache_path,
        max_age_seconds=cfg.cache_max_age_seconds,
    )

    tick_use_case = ProcessTickUseCase(
        state_mgr=state_mgr,
        exchange=exchange,
        notifier=notifier,
        trade_repo=trade_repo,
        signal_provider=signal_provider,
        settings=cfg,
    )

    telegram_dispatcher = TelegramCommandDispatcher(
        allowed_chat_id=cfg.telegram_chat_id,
        capital_ref_mxn=cfg.capital_ref_mxn,
        daily_loss_pct=cfg.daily_loss_pct,
        is_dry_run=cfg.is_dry_run,
        mode_label=cfg.bot_mode,
    )

    return TradingBotRunner(
        settings=cfg,
        state_mgr=state_mgr,
        exchange=exchange,
        notifier=notifier,
        trade_repo=trade_repo,
        signal_provider=signal_provider,
        tick_use_case=tick_use_case,
        telegram_dispatcher=telegram_dispatcher,
    )


def main() -> int:
    """CLI script entrypoint for trading-bot."""
    try:
        runner = build_runner()
        ok = runner.run()
        return 0 if ok else 1
    except KeyboardInterrupt:
        log.info("Interrupted by user. Stopping...")
        return 0
    except Exception as err:
        log.critical("Fatal crash during bot execution: %s", err, exc_info=True)
        return 1
