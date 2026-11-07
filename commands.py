"""Manejadores de comandos de Telegram, desacoplados del loop principal.

Reciben un BotState y devuelven el texto de respuesta como str.
No envían mensajes ellos mismos: eso lo hace el caller.
"""
import logging

from config import BOT_MODE, CAPITAL_REF_MXN, DAILY_LOSS_PCT, IS_DRY_RUN
from exchange import bitso_get_balance

log = logging.getLogger(__name__)


def handle_command(text, bot_state):
    """Procesa un comando y devuelve el texto de respuesta."""
    parts = text.strip().lower().split()
    cmd = parts[0] if parts else ""

    if cmd == "/status":
        snap = bot_state.snapshot()
        status_icon = "🧪 DRY-RUN" if IS_DRY_RUN else "💰 OPERACIONAL"
        pos_str = "Abierta" if snap.get("position") else "Sin posición"
        bot_str = "✅ Activo" if snap.get("running") else "🛑 Detenido"

        pnl_today   = snap.get("pnl_today", 0.0)
        pnl_total   = snap.get("pnl_total", 0.0)
        peak_equity = snap.get("peak_equity", CAPITAL_REF_MXN)
        cur_equity  = CAPITAL_REF_MXN + pnl_total
        daily_limit = -(CAPITAL_REF_MXN * DAILY_LOSS_PCT)
        drawdown    = (peak_equity - cur_equity) / peak_equity * 100 if peak_equity > 0 else 0.0

        reply = (
            f"{status_icon} — {bot_str}\n"
            f"{snap.get('trades_today', 0)} trades hoy, PnL hoy: {pnl_today:+.0f} MXN\n"
            f"Posición: {pos_str}\n"
            f"Equity: {cur_equity:,.0f} MXN | Máx: {peak_equity:,.0f} MXN\n"
            f"Drawdown: {drawdown:.1f}% | Límite pérdida día: {daily_limit:.0f} MXN"
        )
        halt = snap.get("halt_reason")
        if halt:
            reply += f"\n⛔ Bloqueado: {halt}"
        return reply

    if cmd == "/balance":
        if IS_DRY_RUN:
            return "🧪 DRY-RUN — balance real no disponible en simulación"
        try:
            data = bitso_get_balance()
            balances = {b["currency"]: b["available"] for b in data["payload"]["balances"]}
            return (
                f"💰 Balance:\n"
                f"MXN: {float(balances.get('mxn', 0)):,.2f}\n"
                f"BTC: {float(balances.get('btc', 0)):.8f}"
            )
        except Exception as e:
            return f"Error obteniendo balance: {e}"

    if cmd == "/stop":
        bot_state.set(running=False)
        log.info("Bot detenido por comando Telegram")
        return "🛑 Bot detenido. Usa /start para reactivar."

    if cmd == "/start":
        halt = bot_state.get("halt_reason")
        if halt:
            return (
                f"⛔ No puedo reactivar: bot bloqueado ({halt}).\n"
                "Revisa Bitso y borra halt_reason de state.json."
            )
        bot_state.set(running=True)
        log.info("Bot reactivado por comando Telegram")
        return f"▶️ Bot reactivado — modo: {BOT_MODE}"

    if cmd == "/pnl":
        snap = bot_state.snapshot()
        pnl_today = snap.get("pnl_today", 0.0)
        pnl_total = snap.get("pnl_total", 0.0)
        cur_equity = CAPITAL_REF_MXN + pnl_total
        return (
            f"📈 PnL hoy: {pnl_today:+.0f} MXN ({snap.get('trades_today', 0)} trades)\n"
            f"PnL total (sesión): {pnl_total:+.0f} MXN\n"
            f"Equity actual: {cur_equity:,.0f} MXN"
        )

    return "Comandos: /status /balance /stop /start /pnl"
