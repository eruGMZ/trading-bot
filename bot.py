"""Bot de trading BTC/MXN — orquestador principal.

Responsabilidades de este módulo:
  - Arranque, reconciliación y logging.
  - main_loop(): tick cada 60 s usando risk.py para decisiones.
  - telegram_listener(): recibe comandos usando commands.py.

Las reglas de negocio viven en risk.py.
El estado thread-safe vive en state.py (BotState).
Los comandos de Telegram viven en commands.py.
El registro de operaciones vive en trade_log.py.
"""

import logging
import threading
import time
from datetime import date, datetime

import risk
import trade_log
from commands import handle_command
from config import (
    BITSO_API_KEY,
    BITSO_API_SECRET,
    BOT_MODE,
    CAPITAL_REF_MXN,
    DAILY_REPORT_HOUR,
    DRAWDOWN_KILL_PCT,
    IS_DRY_RUN,
    LOG_FILE,
    LOOP_SECONDS,
    DAILY_LOSS_PCT,
    MAX_LOSSES_DAY,
    MAX_SPREAD_PCT,
    MAX_TRADE_MXN,
    MAX_TRADES_DAY,
    MIN_HOURS_BETWEEN_TRADES,
    MODE_TAG,
    RECONCILE_DUST_MXN,
    RISK_PCT_PER_TRADE,
    RSI_BUY,
    RSI_SELL,
    STATE_FILE,
    STOP_LOSS_PCT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TRADE_LOG_FILE,
)
from exchange import (
    bitso_get_available,
    bitso_get_quote,
    bitso_place_order,
    format_btc,
    bitso_get_balance,
)
from logsafety import RedactFilter
from signals import read_cached_rsi
from state import BotState
from telegram_client import (
    get_updates,
    is_authorized_chat,
    send_message,
    telegram_is_configured,
    telegram_notify,
)

log = logging.getLogger(__name__)

BOOK = "btc_mxn"
# Bitso puede cobrar comisión en BTC: lo recibido puede ser ~0.8% menor que lo estimado.
RECONCILE_TOLERANCE = 0.98

# Instancia global — se asigna en __main__ y en setUp de los tests.
bot_state: BotState = None  # type: ignore[assignment]


# ── Infraestructura ───────────────────────────────────────────────────────────

def _setup_logging():
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactFilter([TELEGRAM_BOT_TOKEN, BITSO_API_KEY, BITSO_API_SECRET]))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _notify(message):
    telegram_notify(message)
    log.info(message)


def _current_equity():
    """Equity estimado: capital de referencia + PnL acumulado."""
    return CAPITAL_REF_MXN + bot_state.get("pnl_total", 0.0)


# ── Reconciliación al arrancar ────────────────────────────────────────────────

def _reconcile_on_start():
    pos = bot_state.get("position")
    stored_mode = bot_state.get("mode")

    if pos and stored_mode != BOT_MODE:
        bot_state.halt(
            f"posición abierta en modo {stored_mode!r}, pero el bot arranca en {BOT_MODE!r}"
        )
        return

    if IS_DRY_RUN:
        bot_state.set(mode=BOT_MODE)
        return

    try:
        btc = bitso_get_available("btc")
        price = bitso_get_quote(BOOK)["last"]
    except Exception as e:
        bot_state.halt(f"no se pudo consultar Bitso al arrancar: {e}")
        return

    if pos is None:
        if btc * price >= RECONCILE_DUST_MXN:
            bot_state.halt(f"hay {btc:.8f} BTC en Bitso sin posición registrada")
            return
    elif btc < pos["amount_btc"] * RECONCILE_TOLERANCE:
        bot_state.halt(
            f"posición registrada de {pos['amount_btc']:.8f} BTC, "
            f"pero Bitso solo tiene {btc:.8f} BTC"
        )
        return

    bot_state.set(mode=BOT_MODE)
    log.info("Reconciliación OK — BTC disponible en Bitso: %.8f", btc)


# ── Venta ─────────────────────────────────────────────────────────────────────

def _execute_sell(price, reason):
    """Ejecuta la venta de la posición completa.

    Returns:
        (sold_btc, pnl_mxn, pnl_pct) o None si no había posición.
    """
    pos = bot_state.get("position")
    if not pos:
        return None

    try:
        qty = pos["amount_btc"]
        if not IS_DRY_RUN:
            qty = min(qty, bitso_get_available("btc"))
        sold = float(format_btc(qty))
        if sold <= 0:
            raise RuntimeError("no hay BTC disponible para vender")
        bitso_place_order(BOOK, "sell", amount_btc=sold)
    except Exception as e:
        _notify(f"{MODE_TAG}⚠️ Venta fallida ({reason}): {e}")
        log.error("Venta fallida (%s): %s", reason, e)
        raise

    pnl_mxn, pnl_pct = bot_state.close_position(price, sold)
    return sold, pnl_mxn, pnl_pct


# ── Kill switch ───────────────────────────────────────────────────────────────

def _check_kill_switch(price):
    """Evalúa el drawdown global. Si supera el límite, cierra y bloquea.

    Returns True si el kill switch se disparó.
    """
    equity = _current_equity()
    peak = bot_state.get("peak_equity", CAPITAL_REF_MXN)

    if not risk.drawdown_exceeded(equity, peak, DRAWDOWN_KILL_PCT):
        return False

    drawdown_pct = (peak - equity) / peak * 100
    pos = bot_state.get("position")
    if pos:
        try:
            result = _execute_sell(price, "kill_switch")
            if result:
                sold, pnl_mxn, pnl_pct = result
                trade_log.log_close(
                    TRADE_LOG_FILE, "kill_switch",
                    pos["entry_price"], price, sold, pnl_mxn, pnl_pct,
                    "kill_switch", BOT_MODE,
                )
        except Exception:
            pass  # El halt se ejecuta igual; el error ya se logueó

    reason = f"kill switch — drawdown {drawdown_pct:.1f}% supera el límite {DRAWDOWN_KILL_PCT*100:.0f}%"
    bot_state.halt(reason)
    _notify(f"{MODE_TAG}⛔ KILL SWITCH activado — drawdown {drawdown_pct:.1f}%")
    return True


# ── Reporte diario ────────────────────────────────────────────────────────────

def _send_daily_report(today):
    snap = bot_state.snapshot()
    trades = snap.get("trades_today", 0)
    pnl    = snap.get("pnl_today", 0.0)
    losses = snap.get("losses_today", 0)
    bot_state.mark_daily_report_sent(today)
    _notify(
        f"📊 Reporte del día ({BOT_MODE}):\n"
        f"Trades: {trades}\n"
        f"PnL: {pnl:+.0f} MXN\n"
        f"Ganancias: {trades - losses} | Pérdidas: {losses}"
    )


# ── Tick del loop principal ───────────────────────────────────────────────────

def _tick():
    """Una iteración del loop: lee señales, evalúa riesgo, ejecuta si procede."""
    bot_state.roll_day()
    today = date.today().isoformat()
    snap = bot_state.snapshot()

    if not snap.get("running"):
        return

    if datetime.now().hour >= DAILY_REPORT_HOUR and snap.get("last_daily_report_date") != today:
        _send_daily_report(today)

    quote = bitso_get_quote(BOOK)
    price = quote["last"]
    rsi   = read_cached_rsi()
    pos   = bot_state.get("position")

    # ── Kill switch (prioridad máxima) ─────────────────────────────────────
    if _check_kill_switch(price):
        return

    # ── Stop-loss ──────────────────────────────────────────────────────────
    if pos and risk.needs_stop_loss(pos["entry_price"], price, STOP_LOSS_PCT):
        result = _execute_sell(price, "stop_loss")
        if result:
            sold, pnl_mxn, pnl_pct = result
            trade_log.log_close(
                TRADE_LOG_FILE, "stop_loss",
                pos["entry_price"], price, sold, pnl_mxn, pnl_pct,
                "stop_loss", BOT_MODE,
            )
            _notify(f"{MODE_TAG}⚠️ STOP-LOSS activado @ {price:,.0f} — Pérdida: {pnl_mxn:.0f} MXN")
        return

    # ── Venta por RSI ──────────────────────────────────────────────────────
    if pos and risk.signal_sell(rsi, RSI_SELL):
        result = _execute_sell(price, "rsi_sell")
        if result:
            sold, pnl_mxn, pnl_pct = result
            trade_log.log_close(
                TRADE_LOG_FILE, "close",
                pos["entry_price"], price, sold, pnl_mxn, pnl_pct,
                "rsi_sell", BOT_MODE,
            )
            _notify(
                f"{MODE_TAG}🔴 VENTA BTC {sold:.8f} @ {price:,.0f} — "
                f"PnL {pnl_mxn:+.0f} MXN ({pnl_pct:+.1f}%)"
            )
            # Actualiza el equity máximo si cerramos con ganancia.
            bot_state.update_peak_equity(_current_equity())
        return

    # ── Compra por RSI ─────────────────────────────────────────────────────
    if not pos and risk.signal_buy(rsi, RSI_BUY):
        # Filtro de spread: no entrar en mercados con baja liquidez.
        if risk.spread_too_wide(quote["spread_pct"], MAX_SPREAD_PCT):
            log.info(
                "Compra bloqueada: spread %.3f%% > límite %.3f%%",
                quote["spread_pct"] * 100, MAX_SPREAD_PCT * 100,
            )
            return

        ok, reason = risk.can_trade(bot_state.snapshot())
        if not ok:
            log.info("Señal de compra ignorada: %s", reason)
            return

        trade_mxn = risk.position_size_mxn(CAPITAL_REF_MXN, RISK_PCT_PER_TRADE, STOP_LOSS_PCT, MAX_TRADE_MXN)
        bitso_place_order(BOOK, "buy", amount_mxn=trade_mxn)
        bot_state.open_position(price, trade_mxn)
        trade_log.log_open(
            TRADE_LOG_FILE, price, trade_mxn / price, trade_mxn,
            "rsi_buy", BOT_MODE,
        )
        _notify(
            f"{MODE_TAG}🟢 COMPRA BTC {trade_mxn:.0f} MXN "
            f"@ {price:,.0f} — RSI {rsi:.0f}"
        )


# ── Loops ─────────────────────────────────────────────────────────────────────

def main_loop():
    log.info("main_loop iniciado — modo: %s", BOT_MODE)
    while True:
        try:
            _tick()
        except Exception as e:
            log.error("Error en main_loop: %s", e)
        time.sleep(LOOP_SECONDS)


def telegram_listener():
    if not telegram_is_configured():
        log.warning("TELEGRAM_BOT_TOKEN no configurado — listener deshabilitado")
        return
    if not TELEGRAM_CHAT_ID:
        log.warning("TELEGRAM_CHAT_ID no configurado — comandos deshabilitados")
        return
    log.info("telegram_listener iniciado")
    while True:
        try:
            for upd in get_updates(bot_state.last_update_id + 1):
                bot_state.bump_update_id(upd["update_id"])
                msg     = upd.get("message", {})
                text    = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if not text or chat_id is None:
                    continue
                if not is_authorized_chat(chat_id, TELEGRAM_CHAT_ID):
                    log.warning("Comando ignorado de chat no autorizado: %s", chat_id)
                    continue
                log.info("Comando recibido: %s", text)
                reply = handle_command(text, bot_state)
                try:
                    send_message(chat_id, reply)
                except Exception as e:
                    log.error("Error respondiendo comando: %s", e)
        except Exception as e:
            log.error("Error en telegram_listener: %s", e)
        time.sleep(3)


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    _setup_logging()
    mode_label = "🧪 DRY-RUN (simulación)" if IS_DRY_RUN else "💰 OPERACIONAL (capital real)"
    log.info("Bot arrancando — modo: %s", BOT_MODE)
    print(f"Bot iniciado — modo: {mode_label}")

    bot_state = BotState(
        STATE_FILE, BOT_MODE,
        max_trades=MAX_TRADES_DAY,
        max_losses=MAX_LOSSES_DAY,
        min_hours=MIN_HOURS_BETWEEN_TRADES,
        capital_ref=CAPITAL_REF_MXN,
        daily_loss_pct=DAILY_LOSS_PCT,
    )
    trade_log.init_db(TRADE_LOG_FILE)
    _reconcile_on_start()

    t1 = threading.Thread(target=main_loop, daemon=True)
    t2 = threading.Thread(target=telegram_listener, daemon=True)
    t1.start()
    t2.start()

    telegram_notify(f"🤖 Bot iniciado — modo: {mode_label}")
    t1.join()
