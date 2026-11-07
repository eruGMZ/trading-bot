"""Clase BotState: acceso thread-safe al estado del bot con persistencia en disco."""
import threading
from datetime import date, datetime

import risk
from state_store import default_state, load_state, roll_over_day, save_state


class BotState:
    """Wrapper thread-safe sobre el diccionario de estado del bot.

    Toda lectura y escritura del estado pasa por aquí.
    Los módulos externos (risk.py, commands.py) reciben un ``snapshot()``
    inmutable en lugar de manipular el dict directamente.
    """

    def __init__(self, path, mode,
                 max_trades=3, max_losses=2, min_hours=1,
                 capital_ref=5000.0, daily_loss_pct=0.03):
        self._lock = threading.Lock()
        self._path = path
        today = date.today().isoformat()
        with self._lock:
            self._s = load_state(path, mode, today)
            # Inyectar constantes de riesgo para que can_trade() las encuentre en el snapshot.
            self._s["max_trades"]    = max_trades
            self._s["max_losses"]    = max_losses
            self._s["min_hours"]     = min_hours
            self._s["capital_ref"]   = capital_ref
            self._s["daily_loss_pct"] = daily_loss_pct
            self._s["mode"]          = mode
            # peak_equity arranca en capital_ref si no hay valor guardado.
            if self._s.get("peak_equity") is None:
                self._s["peak_equity"] = capital_ref
            self._persist()

    # ── Lectura ───────────────────────────────────────────────────────────────

    def snapshot(self):
        """Copia inmutable del estado para funciones puras (risk.py)."""
        with self._lock:
            return dict(self._s)

    def get(self, key, default=None):
        with self._lock:
            return self._s.get(key, default)

    @property
    def last_update_id(self):
        with self._lock:
            return self._s.get("last_update_id", 0)

    # ── Escritura ─────────────────────────────────────────────────────────────

    def _persist(self):
        """Guarda en disco. Llamar con self._lock tomado."""
        save_state(self._path, self._s)

    def set(self, **kwargs):
        with self._lock:
            self._s.update(kwargs)
            self._persist()

    def bump_update_id(self, update_id):
        with self._lock:
            self._s["last_update_id"] = update_id
            self._persist()

    def halt(self, reason):
        """Bloquea el bot. Solo un humano puede desbloquearlo."""
        with self._lock:
            self._s["running"] = False
            self._s["halt_reason"] = reason
            self._persist()

    def roll_day(self):
        """Reinicia contadores si cambió la fecha. Devuelve True si los reinició."""
        today = date.today().isoformat()
        with self._lock:
            if roll_over_day(self._s, today):
                self._persist()
                return True
        return False

    def open_position(self, price, amount_mxn):
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._s["position"] = {
                "entry_price": price,
                "amount_btc":  amount_mxn / price,
                "entry_time":  now,
            }
            self._s["trades_today"]    += 1
            self._s["last_trade_time"]  = now
            self._persist()

    def close_position(self, sell_price, sold_btc):
        """Cierra la posición y actualiza el PnL.

        Returns:
            (pnl_mxn, pnl_pct)
        """
        with self._lock:
            pos = self._s.get("position")
            if not pos:
                return 0.0, 0.0
            pnl_mxn, pnl_pct = risk.compute_pnl(pos["entry_price"], sell_price, sold_btc)
            self._s["pnl_today"] += pnl_mxn
            self._s["pnl_total"] += pnl_mxn
            if pnl_mxn < 0:
                self._s["losses_today"] += 1
            self._s["position"] = None
            self._persist()
        return pnl_mxn, pnl_pct

    def update_peak_equity(self, current_equity):
        """Actualiza el equity máximo si el actual es mayor."""
        with self._lock:
            if current_equity > self._s.get("peak_equity", 0):
                self._s["peak_equity"] = current_equity
                self._persist()

    def mark_daily_report_sent(self, today):
        with self._lock:
            self._s["last_daily_report_date"] = today
            self._persist()
