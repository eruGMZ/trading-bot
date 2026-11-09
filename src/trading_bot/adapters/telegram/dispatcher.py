"""Telegram command dispatcher and router."""

from decimal import Decimal
from typing import Any

from trading_bot.core.money import format_btc, format_mxn, to_decimal
from trading_bot.domain.models import BotSnapshot, TradeMetrics
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.trade_repository import TradeRepositoryPort


def is_authorized_chat(chat_id: int | str | None, allowed_chat_id: int | str | None) -> bool:
    """Return True if chat_id matches the allowed configured chat."""
    if allowed_chat_id is None or str(allowed_chat_id).strip() == "":
        return False
    if chat_id is None:
        return False
    return str(chat_id).strip() == str(allowed_chat_id).strip()


class TelegramCommandDispatcher:
    """Routes and executes operator commands received via Telegram."""

    def __init__(
        self,
        allowed_chat_id: int | str,
        capital_ref_mxn: Decimal = Decimal("5000"),
        daily_loss_pct: Decimal = Decimal("0.03"),
        is_dry_run: bool = True,
        mode_label: str = "dry_run",
    ) -> None:
        self._allowed_chat = str(allowed_chat_id).strip()
        self._capital_ref = capital_ref_mxn
        self._daily_loss_pct = daily_loss_pct
        self._is_dry_run = is_dry_run
        self._mode_label = mode_label

    def is_authorized(self, chat_id: int | str | None) -> bool:
        """Check if incoming chat ID is permitted to execute commands."""
        return is_authorized_chat(chat_id, self._allowed_chat)

    def dispatch(
        self,
        text: str,
        state_snapshot: BotSnapshot | dict[str, Any],
        state_controller: Any | None = None,
        exchange: ExchangePort | None = None,
        trade_repo: TradeRepositoryPort | None = None,
    ) -> str:
        """Parse and execute operator command returning response message."""
        parts = text.strip().lower().split()
        cmd = parts[0] if parts else ""

        # Normalize snapshot attributes
        if isinstance(state_snapshot, BotSnapshot):
            running = state_snapshot.running
            has_pos = state_snapshot.position is not None
            trades_today = state_snapshot.trades_today
            pnl_today = state_snapshot.pnl_today
            pnl_total = state_snapshot.pnl_total
            peak_equity = state_snapshot.peak_equity
            halt_reason = state_snapshot.halt_reason
        else:
            running = bool(state_snapshot.get("running", True))
            has_pos = state_snapshot.get("position") is not None
            trades_today = int(state_snapshot.get("trades_today", 0))
            pnl_today = to_decimal(state_snapshot.get("pnl_today", Decimal("0")))
            pnl_total = to_decimal(state_snapshot.get("pnl_total", Decimal("0")))
            peak_equity = to_decimal(state_snapshot.get("peak_equity", self._capital_ref))
            halt_reason = state_snapshot.get("halt_reason")

        if cmd == "/status":
            status_icon = "🧪 DRY-RUN" if self._is_dry_run else "💰 OPERACIONAL"
            bot_str = "✅ Activo" if running else "🛑 Detenido"
            pos_str = "Abierta" if has_pos else "Sin posición"

            cur_equity = self._capital_ref + pnl_total
            daily_limit = -(self._capital_ref * self._daily_loss_pct)
            if peak_equity > Decimal("0"):
                drawdown = ((peak_equity - cur_equity) / peak_equity) * Decimal("100")
            else:
                drawdown = Decimal("0")

            reply = (
                f"{status_icon} — {bot_str}\n"
                f"{trades_today} trades hoy, PnL hoy: {pnl_today:+.0f} MXN\n"
                f"Posición: {pos_str}\n"
                f"Equity: {format_mxn(cur_equity)} MXN | Máx: {format_mxn(peak_equity)} MXN\n"
                f"Drawdown: {drawdown:.1f}% | Límite pérdida día: {format_mxn(daily_limit)} MXN"
            )
            if halt_reason:
                reply += f"\n⛔ Bloqueado: {halt_reason}"
            return reply

        if cmd == "/balance":
            if self._is_dry_run:
                return "🧪 DRY-RUN — balance real no disponible en simulación"
            if exchange is None:
                return "Error: Adaptador de exchange no disponible"
            try:
                mxn_bal = exchange.get_available_balance("mxn")
                btc_bal = exchange.get_available_balance("btc")
                return (
                    f"💰 Balance:\n"
                    f"MXN: {format_mxn(mxn_bal)}\n"
                    f"BTC: {format_btc(btc_bal)}"
                )
            except Exception as err:
                return f"Error obteniendo balance: {err}"

        if cmd == "/stop":
            if state_controller is not None and hasattr(state_controller, "set"):
                state_controller.set(running=False)
            return "🛑 Bot detenido. Usa /start para reactivar."

        if cmd == "/start":
            if halt_reason:
                return (
                    f"⛔ No puedo reactivar: bot bloqueado ({halt_reason}).\n"
                    "Revisa Bitso y borra halt_reason de state.json."
                )
            if state_controller is not None and hasattr(state_controller, "set"):
                state_controller.set(running=True)
            return f"▶️ Bot reactivado — modo: {self._mode_label}"

        if cmd == "/pnl":
            cur_equity = self._capital_ref + pnl_total
            return (
                f"📈 PnL hoy: {pnl_today:+.0f} MXN ({trades_today} trades)\n"
                f"PnL total (sesión): {pnl_total:+.0f} MXN\n"
                f"Equity actual: {format_mxn(cur_equity)} MXN"
            )

        if cmd == "/metrics":
            if trade_repo is None:
                return "📊 Sin repositorio de trades configurado."
            m = trade_repo.get_metrics()
            if isinstance(m, TradeMetrics):
                if m.total == 0:
                    return "📊 Sin operaciones cerradas todavía."
                pf_str = f"{m.profit_factor:.2f}" if m.profit_factor != Decimal("Infinity") else "∞"
                return (
                    f"📊 Métricas ({m.total} trades cerrados):\n"
                    f"Win rate: {m.win_rate:.0f}%\n"
                    f"Expectancy: {m.expectancy:+.1f} MXN/trade\n"
                    f"Profit factor: {pf_str}\n"
                    f"Max drawdown: -{m.max_drawdown_mxn:.0f} MXN\n"
                    f"Bruto ganado: {m.gross_profit:+.0f} MXN\n"
                    f"Bruto perdido: {m.gross_loss:+.0f} MXN"
                )
            return "📊 Sin operaciones cerradas todavía."

        return "Comandos: /status /balance /stop /start /pnl /metrics /help"
