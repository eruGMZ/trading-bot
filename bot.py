"""Bot de trading BTC/MXN en Bitso con señal RSI y control por Telegram."""

import logging
import threading
import time
from datetime import date, datetime

from config import (
    BITSO_API_KEY,
    BITSO_API_SECRET,
    BOT_MODE,
    DAILY_REPORT_HOUR,
    IS_DRY_RUN,
    LOG_FILE,
    LOOP_SECONDS,
    MAX_LOSSES_DAY,
    MAX_TRADES_DAY,
    MIN_HOURS_BETWEEN_TRADES,
    MODE_TAG,
    RECONCILE_DUST_MXN,
    RSI_BUY,
    RSI_SELL,
    STATE_FILE,
    STOP_LOSS_PCT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TRADE_AMOUNT_MXN,
)
from exchange import (
    bitso_get_available,
    bitso_get_balance,
    bitso_get_ticker,
    bitso_place_order,
    format_btc,
)
from logsafety import RedactFilter
from signals import read_cached_rsi
from state_store import load_state, roll_over_day, save_state
from telegram_client import (
    get_updates,
    is_authorized_chat,
    send_message,
    telegram_is_configured,
    telegram_notify,
)

log = logging.getLogger(__name__)

BOOK = "btc_mxn"
# Bitso descuenta la comisión en BTC: lo recibido puede ser ~0.8% menor que lo estimado.
RECONCILE_TOLERANCE = 0.98

state_lock = threading.Lock()
state = None  # se carga con _init_state()


# ── Infraestructura ───────────────────────────────────────────────────────────

def _setup_logging():
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactFilter([TELEGRAM_BOT_TOKEN, BITSO_API_KEY, BITSO_API_SECRET]))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _persist():
    """Guarda el estado en disco. Llamar siempre con state_lock tomado."""
    save_state(STATE_FILE, state)


def _notify(message):
    telegram_notify(message)
    log.info(message)


def _init_state():
    global state
    with state_lock:
        state = load_state(STATE_FILE, BOT_MODE, date.today().isoformat())
        _persist()


def _halt(reason):
    """Bloquea compras y reactivación hasta que alguien revise y limpie halt_reason."""
    with state_lock:
        state["running"] = False
        state["halt_reason"] = reason
        _persist()
    log.error("BOT BLOQUEADO: %s", reason)
    telegram_notify(
        f"{MODE_TAG}⛔ Bot bloqueado: {reason}\n"
        "Revisa Bitso y luego borra halt_reason de state.json antes de usar /start."
    )


def _reconcile_on_start():
    """Compara el estado guardado con el saldo real de Bitso antes de operar."""
    with state_lock:
        pos = state["position"]
        stored_mode = state.get("mode")

    if pos and stored_mode != BOT_MODE:
        _halt(f"posición abierta en modo {stored_mode}, pero el bot arranca en {BOT_MODE}")
        return

    if IS_DRY_RUN:
        with state_lock:
            state["mode"] = BOT_MODE
            _persist()
        return

    try:
        btc = bitso_get_available("btc")
        price = bitso_get_ticker(BOOK)
    except Exception as e:
        _halt(f"no se pudo consultar Bitso al arrancar: {e}")
        return

    if pos is None:
        if btc * price >= RECONCILE_DUST_MXN:
            _halt(f"hay {btc:.8f} BTC en Bitso sin posición registrada")
            return
    elif btc < pos["amount_btc"] * RECONCILE_TOLERANCE:
        _halt(
            f"posición registrada de {pos['amount_btc']:.8f} BTC, "
            f"pero Bitso solo tiene {btc:.8f} BTC"
        )
        return

    with state_lock:
        state["mode"] = BOT_MODE
        _persist()
    log.info("Reconciliación OK — BTC disponible en Bitso: %.8f", btc)


# ── Gestión de riesgo y posición ──────────────────────────────────────────────

def _roll_day():
    today = date.today().isoformat()
    with state_lock:
        if roll_over_day(state, today):
            _persist()
            log.info("Nuevo día %s: contadores diarios reiniciados", today)


def _can_trade():
    with state_lock:
        if state["halt_reason"]:
            return False, f"bot bloqueado: {state['halt_reason']}"
        if not state["running"]:
            return False, "bot detenido"
        if state["position"]:
            return False, "ya hay posición abierta"
        if state["trades_today"] >= MAX_TRADES_DAY:
            return False, "máximo de trades diarios alcanzado"
        if state["losses_today"] >= MAX_LOSSES_DAY:
            return False, "máximo de pérdidas diarias alcanzado"
        last = state["last_trade_time"]

    if last:
        elapsed_h = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
        if elapsed_h < MIN_HOURS_BETWEEN_TRADES:
            return False, f"esperando intervalo mínimo ({elapsed_h:.1f}h < {MIN_HOURS_BETWEEN_TRADES}h)"
    return True, "ok"


def _open_position(price):
    now = datetime.now().isoformat(timespec="seconds")
    with state_lock:
        state["position"] = {
            "entry_price": price,
            "amount_btc": TRADE_AMOUNT_MXN / price,  # estimación; la venta usa el saldo real
            "entry_time": now,
        }
        state["trades_today"] += 1
        state["last_trade_time"] = now
        _persist()


def _close_position(price, sold_btc):
    with state_lock:
        pos = state["position"]
        entry = pos["entry_price"]
        pnl_mxn = (price - entry) * sold_btc
        pnl_pct = (price - entry) / entry * 100
        state["pnl_today"] += pnl_mxn
        state["pnl_total"] += pnl_mxn
        if pnl_mxn < 0:
            state["losses_today"] += 1
        state["position"] = None
        _persist()
    return pnl_mxn, pnl_pct


def _execute_sell(price, reason):
    """Vende la posición completa. Devuelve (btc_vendido, pnl_mxn, pnl_pct)."""
    with state_lock:
        pos = state["position"]
    if not pos:
        return None

    try:
        qty = pos["amount_btc"]
        if not IS_DRY_RUN:
            # Nunca vender más de lo que Bitso tiene realmente disponible.
            qty = min(qty, bitso_get_available("btc"))
        sold = float(format_btc(qty))
        if sold <= 0:
            raise RuntimeError("no hay BTC disponible para vender")
        bitso_place_order(BOOK, "sell", amount_btc=sold)
    except Exception as e:
        telegram_notify(f"{MODE_TAG}⚠️ Venta fallida ({reason}): {e}")
        log.error("Venta fallida (%s): %s", reason, e)
        raise

    pnl_mxn, pnl_pct = _close_position(price, sold)
    return sold, pnl_mxn, pnl_pct


def _send_daily_report(today):
    with state_lock:
        trades = state["trades_today"]
        pnl = state["pnl_today"]
        losses = state["losses_today"]
        state["last_daily_report_date"] = today
        _persist()
    wins = trades - losses
    telegram_notify(
        f"📊 Reporte del día ({BOT_MODE}):\n"
        f"Trades: {trades}\n"
        f"PnL: {pnl:+.0f} MXN\n"
        f"Ganancias: {wins} | Pérdidas: {losses}"
    )
    log.info("Reporte diario enviado")


# ── Loop principal ─────────────────────────────────────────────────────────────

def _tick():
    _roll_day()
    today = date.today().isoformat()
    with state_lock:
        if not state["running"]:
            return
        last_report = state["last_daily_report_date"]

    if datetime.now().hour >= DAILY_REPORT_HOUR and last_report != today:
        _send_daily_report(today)

    price = bitso_get_ticker(BOOK)
    # La única fuente de RSI activa es el caché escrito por rsi_updater.py.
    rsi = read_cached_rsi()
    with state_lock:
        pos = state["position"]

    if pos:
        entry = pos["entry_price"]
        drop_pct = (entry - price) / entry
        if drop_pct >= STOP_LOSS_PCT:
            sold, pnl_mxn, _ = _execute_sell(price, "stop-loss")
            _notify(f"{MODE_TAG}⚠️ STOP-LOSS activado @ {price:,.0f} — Pérdida: {pnl_mxn:.0f} MXN")
            return
        if rsi is not None and rsi > RSI_SELL:
            sold, pnl_mxn, pnl_pct = _execute_sell(price, "RSI alto")
            _notify(
                f"{MODE_TAG}🔴 VENTA BTC {sold:.8f} @ {price:,.0f} — "
                f"PnL {pnl_mxn:+.0f} MXN ({pnl_pct:+.1f}%)"
            )
        return

    if rsi is not None and rsi < RSI_BUY:
        ok, reason = _can_trade()
        if not ok:
            log.info("Señal de compra ignorada: %s", reason)
            return
        bitso_place_order(BOOK, "buy", amount_mxn=TRADE_AMOUNT_MXN)
        _open_position(price)
        _notify(f"{MODE_TAG}🟢 COMPRA BTC {TRADE_AMOUNT_MXN:.0f} MXN @ {price:,.0f} — RSI {rsi:.0f}")


def main_loop():
    log.info("main_loop iniciado — modo: %s", BOT_MODE)
    while True:
        try:
            _tick()
        except Exception as e:
            log.error("Error en main_loop: %s", e)
        time.sleep(LOOP_SECONDS)


# ── Telegram entrada (comandos) ────────────────────────────────────────────────

def _handle_command(text):
    parts = text.strip().lower().split()
    cmd = parts[0] if parts else ""

    if cmd == "/status":
        with state_lock:
            trades = state["trades_today"]
            pnl = state["pnl_today"]
            pos = state["position"]
            running = state["running"]
            halt = state["halt_reason"]
        status_icon = "🧪 DRY-RUN" if IS_DRY_RUN else "💰 OPERACIONAL"
        pos_str = "Abierta" if pos else "Sin posición"
        bot_str = "✅ Activo" if running else "🛑 Detenido"
        reply = (
            f"{status_icon} — {bot_str}\n"
            f"{trades} trades hoy, PnL hoy: {pnl:+.0f} MXN\n"
            f"Posición: {pos_str}"
        )
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
                f"💰 Balance:\nMXN: {float(balances.get('mxn', 0)):,.2f}\n"
                f"BTC: {float(balances.get('btc', 0)):.8f}"
            )
        except Exception as e:
            return f"Error obteniendo balance: {e}"

    if cmd == "/stop":
        with state_lock:
            state["running"] = False
            _persist()
        log.info("Bot detenido por comando Telegram")
        return "🛑 Bot detenido. Usa /start para reactivar."

    if cmd == "/start":
        with state_lock:
            if state["halt_reason"]:
                return (
                    f"⛔ No puedo reactivar: bot bloqueado ({state['halt_reason']}).\n"
                    "Revisa Bitso y borra halt_reason de state.json."
                )
            state["running"] = True
            _persist()
        log.info("Bot reactivado por comando Telegram")
        return f"▶️ Bot reactivado — modo: {BOT_MODE}"

    if cmd == "/pnl":
        with state_lock:
            pnl_today = state["pnl_today"]
            pnl_total = state["pnl_total"]
            trades = state["trades_today"]
        return (
            f"📈 PnL hoy: {pnl_today:+.0f} MXN ({trades} trades)\n"
            f"PnL total (sesión): {pnl_total:+.0f} MXN"
        )

    return "Comandos: /status /balance /stop /start /pnl"


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
            with state_lock:
                offset = state["last_update_id"] + 1
            for upd in get_updates(offset):
                with state_lock:
                    state["last_update_id"] = upd["update_id"]
                    _persist()
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if not text or chat_id is None:
                    continue
                if not is_authorized_chat(chat_id, TELEGRAM_CHAT_ID):
                    # No se responde: no se confirma nada a un chat desconocido.
                    log.warning("Comando ignorado de chat no autorizado: %s", chat_id)
                    continue
                log.info("Comando recibido: %s", text)
                reply = _handle_command(text)
                try:
                    send_message(chat_id, reply)
                except Exception as e:
                    log.error("Error respondiendo comando: %s", e)
        except Exception as e:
            log.error("Error en telegram_listener: %s", e)
        time.sleep(3)


# ── Punto de entrada ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    _setup_logging()
    _init_state()
    mode_label = "🧪 DRY-RUN (simulación)" if IS_DRY_RUN else "💰 OPERACIONAL (capital real)"
    log.info("Bot arrancando — modo: %s", BOT_MODE)
    print(f"Bot iniciado — modo: {mode_label}")

    _reconcile_on_start()

    t1 = threading.Thread(target=main_loop, daemon=True)
    t2 = threading.Thread(target=telegram_listener, daemon=True)
    t1.start()
    t2.start()

    telegram_notify(f"🤖 Bot iniciado — modo: {mode_label}")

    t1.join()
