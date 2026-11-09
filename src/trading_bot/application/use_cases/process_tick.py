"""Process tick use case orchestrating market evaluation, risk, and order flows."""

import logging
from datetime import datetime
from decimal import Decimal

from trading_bot.application.state_manager import StateManager
from trading_bot.application.use_cases.reconcile import reconcile_daily
from trading_bot.config.settings import BotSettings
from trading_bot.core.money import format_btc, format_mxn, quantize_btc
from trading_bot.domain.models import RiskLimits
from trading_bot.domain.risk_engine import (
    can_trade,
    drawdown_exceeded,
    needs_stop_loss,
    position_size_mxn,
    signal_buy,
    signal_sell,
    spread_too_wide,
)
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort
from trading_bot.ports.signal_provider import SignalProviderPort
from trading_bot.ports.trade_repository import TradeRepositoryPort

log = logging.getLogger(__name__)


class ProcessTickUseCase:
    """Orchestrates a single market evaluation and execution cycle."""

    def __init__(
        self,
        state_mgr: StateManager,
        exchange: ExchangePort,
        notifier: NotifierPort,
        trade_repo: TradeRepositoryPort,
        signal_provider: SignalProviderPort,
        settings: BotSettings,
    ) -> None:
        self._state_mgr = state_mgr
        self._exchange = exchange
        self._notifier = notifier
        self._trade_repo = trade_repo
        self._signal_provider = signal_provider
        self._settings = settings

    def execute(self, now: datetime | None = None) -> None:
        """Execute a single market cycle."""
        current_dt = now or datetime.now()
        today_str = current_dt.date().isoformat()

        # 1. Roll calendar day counters if date changed
        self._state_mgr.roll_day(today=today_str)
        snap = self._state_mgr.snapshot()

        if not snap.running or snap.halt_reason:
            return

        # 2. Daily summary and reconciliation trigger
        if (
            current_dt.hour >= self._settings.daily_report_hour
            and snap.last_daily_report_date != today_str
        ):
            self._send_daily_summary(today_str)
            reconcile_daily(self._state_mgr, self._exchange, self._settings, self._notifier)

        # 3. Market data ingestion
        quote = self._exchange.get_quote(self._settings.book)
        price = quote.last
        self._state_mgr.set(last_tick_ok=current_dt.isoformat(timespec="seconds"))

        # 4. Signal ingestion
        rsi_data = self._signal_provider.get_latest_rsi()
        rsi = rsi_data[0] if rsi_data is not None else None

        pos = snap.position

        # ── Branch A: Active Position Management ──────────────────────────────
        if pos is not None:
            # Update high watermark for trailing stop
            self._state_mgr.update_position_high(price)
            snap = self._state_mgr.snapshot()
            pos = snap.position
            if pos is None:
                return

            # Check Kill Switch (Drawdown limit)
            cur_equity = self._settings.capital_ref_mxn + snap.pnl_total
            peak = (
                snap.peak_equity
                if snap.peak_equity > Decimal("0")
                else self._settings.capital_ref_mxn
            )
            if drawdown_exceeded(cur_equity, peak, self._settings.drawdown_kill_pct):
                self._execute_kill_switch(price, pos.amount_btc, pos.entry_price, peak, cur_equity)
                return

            # Check Trailing Stop / Stop-Loss
            high = pos.high_since_entry
            if needs_stop_loss(high, price, self._settings.stop_loss_pct):
                self._execute_stop_exit(price, pos.amount_btc, pos.entry_price, high)
                return

            # Check RSI Sell Signal (Overbought)
            if signal_sell(rsi, self._settings.rsi_sell):
                self._execute_rsi_sell(price, pos.amount_btc, pos.entry_price)
                return

        # ── Branch B: Entry Evaluation ────────────────────────────────────────
        elif signal_buy(rsi, self._settings.rsi_buy):
            self._evaluate_and_buy(price, quote.spread_pct, rsi, current_dt)

    def _send_daily_summary(self, today_str: str) -> None:
        """Send daily trade performance summary to operator."""
        snap = self._state_mgr.snapshot()
        trades = snap.trades_today
        losses = snap.losses_today
        pnl = snap.pnl_today
        self._state_mgr.mark_daily_report_sent(today_str)

        msg = (
            f"📊 Reporte del día ({self._settings.bot_mode}):\n"
            f"Trades: {trades}\n"
            f"PnL: {pnl:+.0f} MXN\n"
            f"Ganancias: {trades - losses} | Pérdidas: {losses}"
        )
        self._notifier.notify(msg)

    def _execute_kill_switch(
        self,
        price: Decimal,
        amount_btc: Decimal,
        entry_price: Decimal,
        peak: Decimal,
        cur_equity: Decimal,
    ) -> None:
        """Execute emergency sell and halt bot due to portfolio drawdown."""
        drawdown_pct = ((peak - cur_equity) / peak) * Decimal("100")
        try:
            self._exchange.place_order(self._settings.book, "sell", amount_btc=amount_btc)
        except Exception as err:
            log.error("Kill-switch sell order failed: %s", err)

        pnl_mxn, pnl_pct = self._state_mgr.close_position(
            price, amount_btc, self._settings.bitso_taker_fee
        )
        self._trade_repo.log_close(
            event="kill_switch",
            entry_price=entry_price,
            exit_price=price,
            amount_btc=amount_btc,
            pnl_mxn=pnl_mxn,
            pnl_pct=pnl_pct,
            reason="kill_switch",
            mode=self._settings.bot_mode,
            book=self._settings.book,
        )

        reason = (
            f"kill switch — drawdown {drawdown_pct:.1f}% "
            f"exceeds limit {self._settings.drawdown_kill_pct * Decimal('100'):.0f}%"
        )
        self._state_mgr.halt(reason)
        self._notifier.notify(
            f"{self._settings.mode_tag}⛔ KILL SWITCH activated — drawdown {drawdown_pct:.1f}%"
        )

    def _execute_stop_exit(
        self,
        price: Decimal,
        amount_btc: Decimal,
        entry_price: Decimal,
        high: Decimal,
    ) -> None:
        """Execute stop-loss or trailing stop order."""
        is_trailing = high > entry_price
        event = "trailing_stop" if is_trailing else "stop_loss"

        self._exchange.place_order(self._settings.book, "sell", amount_btc=amount_btc)
        pnl_mxn, pnl_pct = self._state_mgr.close_position(
            price, amount_btc, self._settings.bitso_taker_fee
        )
        self._trade_repo.log_close(
            event=event,
            entry_price=entry_price,
            exit_price=price,
            amount_btc=amount_btc,
            pnl_mxn=pnl_mxn,
            pnl_pct=pnl_pct,
            reason=event,
            mode=self._settings.bot_mode,
            book=self._settings.book,
        )

        label = "TRAILING STOP" if is_trailing else "STOP-LOSS"
        self._notifier.notify(
            f"{self._settings.mode_tag}⚠️ {label} @ {format_mxn(price)} "
            f"(high {format_mxn(high)}) — PnL {pnl_mxn:+.0f} MXN"
        )

    def _execute_rsi_sell(
        self,
        price: Decimal,
        amount_btc: Decimal,
        entry_price: Decimal,
    ) -> None:
        """Execute normal exit triggered by RSI overbought signal."""
        self._exchange.place_order(self._settings.book, "sell", amount_btc=amount_btc)
        pnl_mxn, pnl_pct = self._state_mgr.close_position(
            price, amount_btc, self._settings.bitso_taker_fee
        )
        self._trade_repo.log_close(
            event="close",
            entry_price=entry_price,
            exit_price=price,
            amount_btc=amount_btc,
            pnl_mxn=pnl_mxn,
            pnl_pct=pnl_pct,
            reason="rsi_sell",
            mode=self._settings.bot_mode,
            book=self._settings.book,
        )

        cur_equity = self._settings.capital_ref_mxn + self._state_mgr.snapshot().pnl_total
        self._state_mgr.update_peak_equity(cur_equity)

        btc_str = format_btc(amount_btc)
        mxn_str = format_mxn(price)
        self._notifier.notify(
            f"{self._settings.mode_tag}🔴 VENTA BTC {btc_str} @ {mxn_str} — "
            f"PnL {pnl_mxn:+.0f} MXN ({pnl_pct:+.1f}%)"
        )

    def _evaluate_and_buy(
        self,
        price: Decimal,
        spread_pct: Decimal,
        rsi: Decimal | None,
        now: datetime,
    ) -> None:
        """Evaluate spread and risk constraints and open position if permitted."""
        if spread_too_wide(spread_pct, self._settings.max_spread_pct):
            log.info(
                "Buy blocked: spread %s > limit %s",
                spread_pct,
                self._settings.max_spread_pct,
            )
            return

        limits = RiskLimits(
            max_trades_day=self._settings.max_trades_day,
            max_losses_day=self._settings.max_losses_day,
            capital_ref_mxn=self._settings.capital_ref_mxn,
            daily_loss_pct=self._settings.daily_loss_pct,
            min_hours_between_trades=self._settings.min_hours_between_trades,
            trading_hours=self._settings.trading_hours,
        )

        snap = self._state_mgr.snapshot()
        ok, reason = can_trade(snap, limits=limits, now=now)
        if not ok:
            log.info("Buy signal ignored by risk rules: %s", reason)
            return

        trade_mxn = position_size_mxn(
            capital_ref=self._settings.capital_ref_mxn,
            risk_pct=self._settings.risk_pct_per_trade,
            stop_loss_pct=self._settings.stop_loss_pct,
            max_mxn=self._settings.max_trade_mxn,
        )

        self._exchange.place_order(self._settings.book, "buy", amount_mxn=trade_mxn)
        self._state_mgr.open_position(price, trade_mxn, entry_time=now)
        purchased_btc = quantize_btc(trade_mxn / price)

        self._trade_repo.log_open(
            price=price,
            amount_btc=purchased_btc,
            amount_mxn=trade_mxn,
            reason="rsi_buy",
            mode=self._settings.bot_mode,
            book=self._settings.book,
        )

        rsi_str = f"{rsi:.0f}" if rsi is not None else "N/A"
        self._notifier.notify(
            f"{self._settings.mode_tag}🟢 COMPRA BTC {format_mxn(trade_mxn)} MXN "
            f"@ {format_mxn(price)} — RSI {rsi_str}"
        )
