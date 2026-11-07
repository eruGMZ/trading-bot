"""Persistencia del estado del bot en un archivo JSON local."""

import json
import os
import tempfile


def default_state(mode, today):
    return {
        "running": True,
        "halt_reason": None,        # si está definido, el bot no compra ni se reactiva
        "mode": mode,
        "day": today,               # fecha (YYYY-MM-DD) a la que pertenecen los contadores
        "position": None,           # {"entry_price", "amount_btc", "entry_time"}
        "trades_today": 0,
        "losses_today": 0,
        "pnl_today": 0.0,
        "pnl_total": 0.0,
        "last_trade_time": None,    # ISO 8601
        "last_update_id": 0,
        "last_daily_report_date": None,
    }


def load_state(path, mode, today):
    """Carga el estado guardado. Si no existe, crea uno nuevo.

    Un archivo corrupto lanza excepción: es preferible no arrancar
    a operar con un estado desconocido.
    """
    try:
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
    except FileNotFoundError:
        return default_state(mode, today)
    if not isinstance(stored, dict):
        raise ValueError(f"{path} no contiene un objeto JSON")
    state = default_state(mode, today)
    state.update(stored)
    return state


def save_state(path, state):
    """Escritura atómica: primero a un archivo temporal, luego se reemplaza."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def roll_over_day(state, today):
    """Reinicia los contadores diarios si cambió la fecha. Devuelve True si los reinició."""
    if state.get("day") == today:
        return False
    state["day"] = today
    state["trades_today"] = 0
    state["losses_today"] = 0
    state["pnl_today"] = 0.0
    return True
