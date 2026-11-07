"""Registro persistente de operaciones en SQLite.

Cada apertura y cierre de posición genera una fila.
No reemplaza al bot.log; lo complementa con datos estructurados
para consultar PnL histórico, R:R y auditar operaciones.

Esquema:
  id          — autoincremental
  ts          — ISO 8601 (hora local)
  event       — 'open' | 'close' | 'stop_loss' | 'kill_switch'
  book        — par de trading (p. ej. 'btc_mxn')
  price       — precio en MXN al momento del evento
  amount_btc  — cantidad de BTC involucrada
  amount_mxn  — MXN invertidos (solo en 'open')
  pnl_mxn     — ganancia/pérdida en MXN (solo en cierres)
  pnl_pct     — porcentaje de retorno (solo en cierres)
  entry_price — precio de entrada (solo en cierres, para calcular R:R)
  reason      — motivo del evento (p. ej. 'rsi_buy', 'rsi_sell')
  mode        — 'dry_run' | 'operational'
"""

import sqlite3
from datetime import datetime

_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    event       TEXT    NOT NULL,
    book        TEXT    NOT NULL,
    price       REAL    NOT NULL,
    amount_btc  REAL    NOT NULL,
    amount_mxn  REAL,
    pnl_mxn     REAL,
    pnl_pct     REAL,
    entry_price REAL,
    reason      TEXT,
    mode        TEXT    NOT NULL
)
"""


def init_db(path):
    """Crea la tabla si no existe. Seguro ejecutar más de una vez."""
    with sqlite3.connect(path) as conn:
        conn.execute(_DDL)


def _insert(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """INSERT INTO trades
               (ts, event, book, price, amount_btc, amount_mxn,
                pnl_mxn, pnl_pct, entry_price, reason, mode)
               VALUES (:ts, :event, :book, :price, :amount_btc, :amount_mxn,
                       :pnl_mxn, :pnl_pct, :entry_price, :reason, :mode)""",
            row,
        )


def log_open(path, price, amount_btc, amount_mxn, reason, mode):
    """Registra la apertura de una posición."""
    _insert(path, {
        "ts":          datetime.now().isoformat(timespec="seconds"),
        "event":       "open",
        "book":        "btc_mxn",
        "price":       price,
        "amount_btc":  amount_btc,
        "amount_mxn":  amount_mxn,
        "pnl_mxn":     None,
        "pnl_pct":     None,
        "entry_price": None,
        "reason":      reason,
        "mode":        mode,
    })


def log_close(path, event, entry_price, exit_price, amount_btc,
              pnl_mxn, pnl_pct, reason, mode):
    """Registra el cierre de una posición.

    Args:
        event: 'close' | 'stop_loss' | 'kill_switch'.
    """
    _insert(path, {
        "ts":          datetime.now().isoformat(timespec="seconds"),
        "event":       event,
        "book":        "btc_mxn",
        "price":       exit_price,
        "amount_btc":  amount_btc,
        "amount_mxn":  None,
        "pnl_mxn":     pnl_mxn,
        "pnl_pct":     pnl_pct,
        "entry_price": entry_price,
        "reason":      reason,
        "mode":        mode,
    })
