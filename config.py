"""Configuración compartida por el bot y el actualizador del RSI."""

import os

from dotenv import load_dotenv

load_dotenv()

BITSO_API_KEY = os.getenv("BITSO_API_KEY", "")
BITSO_API_SECRET = os.getenv("BITSO_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CDP_PORT = os.getenv("TRADINGVIEW_CDP_PORT") or "9222"

# Un valor mal escrito (p. ej. "Operational") no debe caer en silencio a dry-run.
VALID_MODES = ("dry_run", "operational")
BOT_MODE = os.getenv("BOT_MODE", "dry_run").strip()
if BOT_MODE not in VALID_MODES:
    raise ValueError(
        f"BOT_MODE inválido: {BOT_MODE!r}. Usa 'dry_run' u 'operational'."
    )
IS_DRY_RUN = BOT_MODE != "operational"
MODE_TAG = "[SIMULADO] " if IS_DRY_RUN else "[REAL] "

LOG_FILE = os.path.expanduser("~/trading-bot/bot.log")
STATE_FILE = os.path.expanduser("~/trading-bot/state.json")
CACHE_FILE = os.path.expanduser("~/trading-bot/rsi_cache.json")
CACHE_MAX_AGE_SECONDS = 120
RSI_UPDATE_INTERVAL = 60
LOOP_SECONDS = 60

TRADE_AMOUNT_MXN = 500.0
MAX_TRADES_DAY = 3
MAX_LOSSES_DAY = 2
MIN_HOURS_BETWEEN_TRADES = 1
STOP_LOSS_PCT = 0.02
RSI_BUY = 30
RSI_SELL = 70
DAILY_REPORT_HOUR = 23

# Si al arrancar hay BTC en Bitso por encima de este valor sin posición registrada, se bloquea.
RECONCILE_DUST_MXN = 10.0
