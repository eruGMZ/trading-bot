"""Manejadores de comandos de Telegram, desacoplados del loop principal.

Reciben un BotState y devuelven el texto de respuesta como str.
No envían mensajes ellos mismos: eso lo hace el caller.
"""
import logging

from config import BOT_MODE, IS_DRY_RUN
from exchange import bitso_get_balance

log = logging.getLogger(__name__)


def handle_command(text, bot_state):
    """Procesa un comando y devuelve el texto de respuesta.

    Args:
        text: texto del mensaje (p. ej. "/status").
        bot_state: instancia de BotState.

    Returns:
        str con la respuesta a enviar.
    """
    parts = text.strip().lower().split()
    cmd = parts[0] if parts else ""

    if cmd == "/status":
        snap = bot_state.snapshot()
        status_icon = "🧪 DRY-RUN" if IS_DRY_RUN else "💰 OPERACIONAL"
        pos_str = "Abierta" if snap.get("position") else "Sin posición"
        bot_str = "✅ Activo" if snap.get("running") else "🛑 Detenido"
        reply = (
            f"{status_icon} — {bot_str}\n"
            f"{snap.get('trades_today', 0)} trades hoy, "
            f"PnL hoy: {snap.get('pnl_today', 0.0):+.0f} MXN\n"
            f"Posición: {pos_str}"
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
        return (
            f"📈 PnL hoy: {snap.get('pnl_today', 0.0):+.0f} MXN "
            f"({snap.get('trades_today', 0)} trades)\n"
            f"PnL total (sesión): {snap.get('pnl_total', 0.0):+.0f} MXN"
        )

    return "Comandos: /status /balance /stop /start /pnl"
