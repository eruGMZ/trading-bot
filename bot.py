import time
import logging
import threading
from datetime import datetime, date
from exchange import bitso_get_balance, bitso_get_ticker, bitso_place_order
from signals import read_cached_rsi
from telegram_client import (
    get_updates,
    send_message,
    telegram_is_configured,
    telegram_notify,
)
from config import (
    BOT_MODE,
    IS_DRY_RUN,
    LOG_FILE,
    MAX_LOSSES_DAY,
    MAX_TRADES_DAY,
    MIN_HOURS_BETWEEN_TRADES,
    MODE_TAG,
    RSI_BUY,
    RSI_SELL,
    STOP_LOSS_PCT,
    TRADE_AMOUNT_MXN,
)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

state_lock = threading.Lock()
state = {
    "running": True,
    "mode": BOT_MODE,
    "position": None,
    "trades_today": 0,
    "losses_today": 0,
    "pnl_today": 0.0,
    "pnl_total": 0.0,
    "last_trade_time": None,
    "start_time": datetime.now(),
    "last_update_id": 0,
    "last_daily_report_date": None,
}

# ── Gestión de riesgo ──────────────────────────────────────────────────────────

def _reset_daily_counters():
    with state_lock:
        state["trades_today"] = 0
        state["losses_today"] = 0
        state["pnl_today"] = 0.0


def _can_trade():
    with state_lock:
        if not state["running"]:
            return False, "bot detenido"
        if state["trades_today"] >= MAX_TRADES_DAY:
            return False, "máximo de trades diarios alcanzado"
        if state["losses_today"] >= MAX_LOSSES_DAY:
            return False, "máximo de pérdidas diarias alcanzado"
        last = state["last_trade_time"]
        if last:
            elapsed_h = (datetime.now() - last).total_seconds() / 3600
            if elapsed_h < MIN_HOURS_BETWEEN_TRADES:
                return False, f"esperando intervalo mínimo ({elapsed_h:.1f}h < {MIN_HOURS_BETWEEN_TRADES}h)"
    return True, "ok"


def _open_position(price):
    amount_btc = TRADE_AMOUNT_MXN / price
    with state_lock:
        state["position"] = {
            "entry_price": price,
            "amount_btc": amount_btc,
            "entry_time": datetime.now(),
        }
        state["trades_today"] += 1
        state["last_trade_time"] = datetime.now()


def _close_position(price, reason="venta"):
    with state_lock:
        pos = state["position"]
        if not pos:
            return 0.0, 0.0
        entry = pos["entry_price"]
        amount_btc = pos["amount_btc"]
        pnl_mxn = (price - entry) * amount_btc
        pnl_pct = (price - entry) / entry * 100
        state["pnl_today"] += pnl_mxn
        state["pnl_total"] += pnl_mxn
        if pnl_mxn < 0:
            state["losses_today"] += 1
        state["position"] = None
    return pnl_mxn, pnl_pct


# ── Loop principal ─────────────────────────────────────────────────────────────

def main_loop():
    log.info("main_loop iniciado — modo: %s", BOT_MODE)
    while True:
        with state_lock:
            if not state["running"]:
                time.sleep(5)
                continue

        try:
            # Reset contadores si cambió el día
            today = date.today()
            with state_lock:
                last_report = state.get("last_daily_report_date")

            # Reporte diario a las 23:00
            now = datetime.now()
            if now.hour == 23 and now.minute == 0 and last_report != today:
                with state_lock:
                    trades = state["trades_today"]
                    pnl = state["pnl_today"]
                    losses = state["losses_today"]
                    wins = trades - losses
                    state["last_daily_report_date"] = today
                msg = (
                    f"📊 Reporte del día ({BOT_MODE}):\n"
                    f"Trades: {trades}\n"
                    f"PnL: {pnl:+.0f} MXN\n"
                    f"Ganancias: {wins} | Pérdidas: {losses}"
                )
                telegram_notify(msg)
                log.info("Reporte diario enviado")
                _reset_daily_counters()

            # Leer precio actual
            price = bitso_get_ticker("btc_mxn")

            # La única fuente de RSI activa es el caché escrito por rsi_updater.py.
            rsi = read_cached_rsi()

            with state_lock:
                position = state["position"]

            # ── Stop-loss ──
            if position:
                entry = position["entry_price"]
                drop_pct = (entry - price) / entry
                if drop_pct >= STOP_LOSS_PCT:
                    bitso_place_order("btc_mxn", "sell", TRADE_AMOUNT_MXN)
                    pnl_mxn, _ = _close_position(price, "stop-loss")
                    msg = f"{MODE_TAG}⚠️ STOP-LOSS activado @ {price:,.0f} — Pérdida: {pnl_mxn:.0f} MXN"
                    telegram_notify(msg)
                    log.info(msg)
                    time.sleep(60)
                    continue

            # ── Señal de venta (RSI > 70) ──
            if position and rsi is not None and rsi > RSI_SELL:
                bitso_place_order("btc_mxn", "sell", TRADE_AMOUNT_MXN)
                pnl_mxn, pnl_pct = _close_position(price)
                msg = (
                    f"{MODE_TAG}🔴 VENTA BTC {TRADE_AMOUNT_MXN:.0f} MXN "
                    f"@ {price:,.0f} — PnL {pnl_mxn:+.0f} MXN ({pnl_pct:+.1f}%)"
                )
                telegram_notify(msg)
                log.info(msg)

            # ── Señal de compra (RSI < 30) ──
            elif not position and rsi is not None and rsi < RSI_BUY:
                ok, reason = _can_trade()
                if ok:
                    bitso_place_order("btc_mxn", "buy", TRADE_AMOUNT_MXN)
                    _open_position(price)
                    msg = (
                        f"{MODE_TAG}🟢 COMPRA BTC {TRADE_AMOUNT_MXN:.0f} MXN "
                        f"@ {price:,.0f} — RSI {rsi:.0f}"
                    )
                    telegram_notify(msg)
                    log.info(msg)
                else:
                    log.info("Señal de compra ignorada: %s", reason)

        except Exception as e:
            log.error("Error en main_loop: %s", e)

        time.sleep(60)


# ── Telegram entrada (comandos) ────────────────────────────────────────────────

def _handle_command(text, chat_id):
    cmd = text.strip().lower().split()[0] if text else ""

    if cmd == "/status":
        with state_lock:
            trades = state["trades_today"]
            pnl = state["pnl_today"]
            pos = state["position"]
            running = state["running"]
        status_icon = "🧪 DRY-RUN" if IS_DRY_RUN else "💰 OPERACIONAL"
        pos_str = "Abierta" if pos else "Sin posición"
        bot_str = "✅ Activo" if running else "🛑 Detenido"
        reply = (
            f"{status_icon} — {bot_str}\n"
            f"{trades} trades hoy, PnL hoy: {pnl:+.0f} MXN\n"
            f"Posición: {pos_str}"
        )

    elif cmd == "/balance":
        if IS_DRY_RUN:
            reply = "🧪 DRY-RUN — balance real no disponible en simulación"
        else:
            try:
                data = bitso_get_balance()
                balances = {b["currency"]: b["available"] for b in data["payload"]["balances"]}
                mxn = balances.get("mxn", "?")
                btc = balances.get("btc", "?")
                reply = f"💰 Balance:\nMXN: {float(mxn):,.2f}\nBTC: {float(btc):.8f}"
            except Exception as e:
                reply = f"Error obteniendo balance: {e}"

    elif cmd == "/stop":
        with state_lock:
            state["running"] = False
        reply = "🛑 Bot detenido. Usa /start para reactivar."
        log.info("Bot detenido por comando Telegram")

    elif cmd == "/start":
        with state_lock:
            state["running"] = True
        reply = f"▶️ Bot reactivado — modo: {BOT_MODE}"
        log.info("Bot reactivado por comando Telegram")

    elif cmd == "/pnl":
        with state_lock:
            pnl_today = state["pnl_today"]
            pnl_total = state["pnl_total"]
            trades = state["trades_today"]
        reply = (
            f"📈 PnL hoy: {pnl_today:+.0f} MXN ({trades} trades)\n"
            f"PnL total (sesión): {pnl_total:+.0f} MXN"
        )

    else:
        reply = "Comandos: /status /balance /stop /start /pnl"

    try:
        send_message(chat_id, reply)
    except Exception as e:
        log.error("Error respondiendo comando: %s", e)


def telegram_listener():
    if not telegram_is_configured():
        log.warning("TELEGRAM_BOT_TOKEN no configurado — listener deshabilitado")
        return
    log.info("telegram_listener iniciado")
    while True:
        try:
            with state_lock:
                offset = state["last_update_id"] + 1
            updates = get_updates(offset)
            for upd in updates:
                with state_lock:
                    state["last_update_id"] = upd["update_id"]
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if text and chat_id:
                    log.info("Comando recibido: %s", text)
                    _handle_command(text, chat_id)
        except Exception as e:
            log.error("Error en telegram_listener: %s", e)
        time.sleep(3)


# ── Punto de entrada ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode_label = "🧪 DRY-RUN (simulación)" if IS_DRY_RUN else "💰 OPERACIONAL (capital real)"
    log.info("Bot arrancando — modo: %s", BOT_MODE)
    print(f"Bot iniciado — modo: {mode_label}")

    t1 = threading.Thread(target=main_loop, daemon=True)
    t2 = threading.Thread(target=telegram_listener, daemon=True)
    t1.start()
    t2.start()

    telegram_notify(f"🤖 Bot iniciado — modo: {mode_label}")

    t1.join()
